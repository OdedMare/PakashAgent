"""Where are builds and chat turns stuck? Run in the backend pod:

    python -m app.diagnose

Prints, without changing anything: the model settings and proxy variables
this process sees, the job queue in PostgreSQL, the model queue in Redis,
and whether the model server answers. Short to type on purpose -- it is
meant for a terminal on a closed network, where nothing can be pasted in.
"""

import os
import time

import httpx

from app.common.config import Settings
from app.common.redis_hub import RedisHub, mask_url, url_of
from app.common.runtime_settings.runtime_settings_store import RuntimeSettingsStore
from app.dal.database import connect
from app.dal.llm.model_roles import (
    ADVANCED, DEFAULT, FAST, resolve_base_url, resolve_model,
)
from app.dal.llm.redis_slots import slot_keys

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
    print("timeout=%ss max_concurrency=%s queue=%ss engine=%s" % (
        getattr(settings, "llm_timeout_seconds", "?"),
        getattr(settings, "llm_max_concurrency", "?"),
        getattr(settings, "llm_queue_seconds", "?"),
        getattr(settings, "schedule_generation_engine", "?"),
    ))
    print("embedded_worker=%s" % (os.getenv("PAKASH_EMBEDDED_WORKER") or "default(on)"))
    print("redis=%s" % (mask_url(url_of(settings)) or "off"))
    _section("proxy variables (the model client follows these)")
    found = False
    for name in _PROXY_VARS:
        for spelled in (name, name.lower()):
            if os.getenv(spelled):
                found = True
                print("%s=%s" % (spelled, mask_url(os.getenv(spelled))))
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
    _section("model queue (Redis)")
    hub = RedisHub(store)
    client = hub.client()
    if client is None:
        print("not used (%s)" % (hub.status().get("error") or "not configured"))
        return
    try:
        queue, _alive, holders, _teams = slot_keys(hub)
        now_ms = int(time.time() * 1000)
        print("holding=%s waiting=%s" % (
            client.zcount(holders, "(%d" % now_ms, "+inf"), client.zcard(queue)))
    except Exception as exc:  # noqa: BLE001
        print("FAILED: %s" % exc)


def _model_server(settings) -> None:
    _section("model server")
    seen = set()
    for role in (FAST, DEFAULT, ADVANCED):
        url = resolve_base_url(settings, role)
        if not url or url in seen:
            continue
        seen.add(url)
        target = url.rstrip("/") + "/models"
        for trust_env in (True, False):
            label = "with proxy vars" if trust_env else "direct"
            started = time.monotonic()
            try:
                response = httpx.get(
                    target, timeout=10, verify=False, trust_env=trust_env,
                )
                print("%s %s -> HTTP %s in %.1fs" % (
                    target, label, response.status_code,
                    time.monotonic() - started))
            except Exception as exc:  # noqa: BLE001
                print("%s %s -> FAILED after %.1fs: %s" % (
                    target, label, time.monotonic() - started,
                    type(exc).__name__ + ": " + str(exc)[:150]))


def main() -> None:
    store = RuntimeSettingsStore(Settings())
    settings = store.get()
    _settings(settings)
    _jobs(store)
    _model_queue(store)
    _model_server(settings)


if __name__ == "__main__":
    main()
