"""Where are builds and chat turns stuck? Run in the backend pod:

    python -m app.diagnose

Prints, without changing anything: the model settings and proxy variables
this process sees, the job queue and the model slots in PostgreSQL,
whether the model server answers (with its certificate checked, as the
model client does), and one real completion. Short to type on purpose -- it is
meant for a terminal on a closed network, where nothing can be pasted in.
"""

import os
import time
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.common.config import Settings
from app.common.runtime_settings.runtime_settings_store import RuntimeSettingsStore
from app.dal.database import connect
from app.dal.llm.model_roles import (
    ADVANCED, DEFAULT, FAST, resolve_base_url, resolve_model,
)
from app.dal.llm.openai_client import OpenAIJsonClient

_PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")


def _section(title: str) -> None:
    print("\n== %s ==" % title)


def _settings(settings) -> None:
    _section("settings")
    for role in (FAST, DEFAULT, ADVANCED):
        print("%-8s model=%s url=%s" % (
            role, resolve_model(settings, role) or "-",
            resolve_base_url(settings, role) or "(openai default)",
        ))
    print("timeout=%ss max_concurrency=%s queue=%ss solver=%ss/%s workers" % (
        getattr(settings, "llm_timeout_seconds", "?"),
        getattr(settings, "llm_max_concurrency", "?"),
        getattr(settings, "llm_queue_seconds", "?"),
        getattr(settings, "solver_time_limit_seconds", "?"),
        getattr(settings, "solver_workers", "?"),
    ))
    print("embedded_worker=%s" % (os.getenv("PAKASH_EMBEDDED_WORKER") or "default(on)"))
    _section("proxy variables (the model client follows these)")
    found = False
    for name in _PROXY_VARS:
        for spelled in (name, name.lower()):
            if os.getenv(spelled):
                found = True
                print("%s=%s" % (spelled, _mask_url(os.getenv(spelled))))
    if not found:
        print("none")


def _jobs(store) -> None:
    _section("job queue (PostgreSQL)")
    try:
        with connect(store) as connection:
            rows = connection.execute("""
                SELECT status, kind, COUNT(*) AS n,
                    ROUND(EXTRACT(EPOCH FROM NOW() - MIN(created_at))) AS oldest_s
                FROM copilot_jobs
                WHERE status IN ('queued','running')
                GROUP BY status, kind ORDER BY status, kind
            """).fetchall()
            for row in rows:
                print("%-8s %-16s count=%s oldest=%ss" % (
                    row["status"], row["kind"], row["n"], row["oldest_s"]))
            if not rows:
                print("empty: nothing queued or running")
            running = connection.execute("""
                SELECT id, kind, attempts,
                    ROUND(EXTRACT(EPOCH FROM NOW() - started_at)) AS age_s
                FROM copilot_jobs WHERE status='running'
                ORDER BY started_at LIMIT 10
            """).fetchall()
            for row in running:
                print("running %s %s attempt=%s for=%ss" % (
                    row["id"], row["kind"], row["attempts"], row["age_s"]))
            failed = connection.execute("""
                SELECT kind, LEFT(error, 200) AS error FROM copilot_jobs
                WHERE error <> '' ORDER BY COALESCE(finished_at, started_at) DESC
                LIMIT 5
            """).fetchall()
            for row in failed:
                print("last error %s: %s" % (row["kind"], row["error"]))
            connection.rollback()
    except Exception as exc:  # noqa: BLE001 -- report and go on
        print("FAILED: %s" % exc)


def _model_queue(store) -> None:
    """Model calls in flight: the advisory locks `PostgresModelSlots` holds."""
    _section("model slots (PostgreSQL advisory locks)")
    try:
        with connect(store) as connection:
            held = connection.execute(
                "SELECT COUNT(*) AS held FROM pg_locks "
                "WHERE locktype = 'advisory' AND granted").fetchone()["held"]
            connection.rollback()
        print("advisory locks held=%s (one per call in flight, one per team calling)" % held)
    except Exception as exc:  # noqa: BLE001 -- report and go on
        print("FAILED: %s" % exc)


def _mask_url(url: str) -> str:
    """The URL with any password in it replaced, fit to print."""
    try:
        parts = urlsplit(url or "")
    except ValueError:
        return "…"
    if parts.password is None:
        return url or ""
    host = parts.hostname or ""
    if parts.port:
        host = "%s:%s" % (host, parts.port)
    netloc = "%s:********@%s" % (parts.username or "", host)
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _model_server(settings) -> None:
    _section("model server")
    print("SSL_CERT_FILE=%s verify_ssl=%s" % (
        os.getenv("SSL_CERT_FILE") or "-",
        getattr(settings, "llm_verify_ssl", True)))
    seen = set()
    for role in (FAST, DEFAULT, ADVANCED):
        url = resolve_base_url(settings, role)
        if not url or url in seen:
            continue
        seen.add(url)
        target = url.rstrip("/") + "/models"
        # Certificate checked first: the model client checks it, and a
        # probe that skips it reports a server it cannot actually use.
        for label, verify in (("cert checked", True), ("cert NOT checked", False)):
            started = time.monotonic()
            try:
                response = httpx.get(target, timeout=10, verify=verify)
                print("%s %s -> HTTP %s in %.1fs" % (
                    target, label, response.status_code,
                    time.monotonic() - started))
            except Exception as exc:  # noqa: BLE001
                print("%s %s -> FAILED after %.1fs: %s" % (
                    target, label, time.monotonic() - started,
                    type(exc).__name__ + ": " + str(exc)[:200]))


def _completion(store) -> None:
    """One real call through the app's own client and settings."""
    _section("one real completion (fast role)")
    started = time.monotonic()
    try:
        reply = OpenAIJsonClient(store).complete_json(
            'Answer with JSON only.', 'Reply with {"ok": true}', flow="briefing",
        )
        print("OK in %.1fs: %s" % (time.monotonic() - started, str(reply)[:200]))
    except Exception as exc:  # noqa: BLE001
        print("FAILED after %.1fs: %s" % (time.monotonic() - started, exc))


def main() -> None:
    store = RuntimeSettingsStore(Settings())
    settings = store.get()
    _settings(settings)
    _jobs(store)
    _model_queue(store)
    _model_server(settings)
    _completion(store)


if __name__ == "__main__":
    main()
