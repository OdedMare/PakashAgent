"""Always-running durable job worker: chat turns, builds, translations.

Run with ``python -m app.worker``. PostgreSQL owns claiming and deduplication,
so restarting this process or running two copies cannot execute one job twice.
"""

import logging
import os
import signal
import threading
import time

from app.bl.compiled_sources import SourceCompiler
from app.bl.compiled_sources.compiler import JOB_KIND as COMPILE_SOURCES
from app.bl.schedule_service import ScheduleService
from app.bl.chat.service import ManagerChatService
from app.common.events import TeamEvents
from app.dal.notify import PostgresSignals
from app.common.activity import track_activity
from app.common.actor import acting_as
from app.common.errors import NotFoundError
from app.common.config import Settings
from app.common.logging_setup import configure_logging
from app.common.runtime_settings.runtime_settings_store import RuntimeSettingsStore
from app.dal.llm.openai_client import OpenAIJsonClient
from app.dal.llm.team_context import model_team
from app.dal.repository import Repository

_log = logging.getLogger("pakash.worker")
_POLL_SECONDS = max(1, int(os.getenv("PAKASH_COPILOT_POLL_SECONDS", "1")))
# Chat turns get their own lanes so a build never delays an answer; several
# of them so one slow (or stuck) turn does not hold every other manager's.
_WORKER_CONCURRENCY = max(1, int(os.getenv("PAKASH_WORKER_CONCURRENCY", "6")))
_CHAT_WORKERS = max(1, int(os.getenv("PAKASH_CHAT_WORKERS", "3")))
# Finished jobs are deleted after this many days, checked once an hour.
_RETENTION_DAYS = max(1, int(os.getenv("PAKASH_JOB_RETENTION_DAYS", "30")))
_PURGE_SECONDS = 3600


class JobWorker:
    def __init__(self, repository, schedules=None, chat=None, compiler=None):
        self._repository = repository
        self._schedules, self._chat = schedules, chat
        self._compiler = compiler

    def purge_finished_jobs(self, older_than_days) -> int:
        purge = getattr(self._repository, "purge_finished_jobs", None)
        return purge(older_than_days) if purge else 0

    def run_once(self, lane="any") -> int:
        processed = 0
        while True:
            with self._repository.claim_copilot_job(lane=lane) as job:
                if not job:
                    return processed
                self._process(job)
            processed += 1

    def _process(self, job):
        started = time.monotonic()
        _log.info("job started id=%s kind=%s team=%s attempt=%s",
                  job["id"], job["kind"], job["team_id"], job.get("attempts"))
        try:
            with model_team(job["team_id"]), \
                    acting_as((job.get("payload") or {}).get("actor", "")):
                self._execute(job)
            self._repository.finish_copilot_job(job["id"])
            _log.info("job finished id=%s kind=%s seconds=%.1f",
                      job["id"], job["kind"], time.monotonic() - started)
        except NotFoundError:
            # A manager may delete a conversation or period while it waits.
            self._repository.finish_copilot_job(job["id"])
        except Exception as exc:
            _log.exception("job failed id=%s", job["id"])
            retry = int(job.get("attempts") or 0) < 3
            self._repository.finish_copilot_job(job["id"], str(exc), retry=retry)
            if not retry:
                self._fail(job)

    def _execute(self, job):
        team_id, payload = job["team_id"], job["payload"]
        if job["kind"] == "manager_chat":
            def progress(activity):
                self._repository.chat_activity(payload["chat_id"], payload["message_id"], activity)
            with track_activity(progress):
                progress("קורא את הבקשה ואת הסידור…")
                self._chat.reply(team_id, payload["manager_id"], payload["chat_id"], payload["message_id"])
        elif job["kind"] == "generation":
            with track_activity(lambda activity: self._repository.generation_activity(
                    payload["schedule_id"], team_id, activity)):
                self._schedules.run_generation(
                    team_id, payload["schedule_id"],
                    payload.get("date", ""), payload.get("through", ""),
                )
                # Adaptive splitting can create new spans while this job is
                # running. Reconcile the durable queue after every checkpoint.
                self._repository.queue_generation_job(team_id, payload["schedule_id"])
        elif job["kind"] == "scan":
            # The copilot that queued these is gone; one still waiting in an
            # existing database is finished without doing anything.
            pass
        elif job["kind"] == COMPILE_SOURCES:
            # Setup was saved: translate its rules, policies and notes for
            # the code scheduler now, so the first build need not (D32).
            self._compiler.compile(team_id)
        else:
            raise ValueError("Unknown job kind: %s" % job["kind"])

    def _fail(self, job):
        # A build's failure is on its span, where the banner reads it, and a
        # translation's next build retries what is missing. Only a chat turn
        # would otherwise be left "working" forever.
        if job["kind"] == "manager_chat":
            payload = job["payload"]
            self._repository.finish_chat_turn(payload["chat_id"], payload["message_id"],
                "לא הצלחנו להשלים את הבקשה. אפשר לשלוח אותה שוב", "error", {})


def _build():
    env = Settings()
    store = RuntimeSettingsStore(env)
    repository = Repository(store)
    # Panel saves made on any replica apply here too (D39), from the first
    # job on: a database not ready yet is simply asked again by `get()`.
    store.share_through(repository)
    store.pull_shared()
    llm = OpenAIJsonClient(store)
    schedules = ScheduleService(repository, llm, settings=store)
    return repository, JobWorker(
        repository, schedules=schedules, chat=ManagerChatService(
            repository, llm, schedules,
            # A turn answered here wakes the manager's screen in the API.
            events=TeamEvents(bus=PostgresSignals(store)),
            settings=store,
        ),
        compiler=SourceCompiler(repository, llm),
    )


def start(worker, stopped: threading.Event) -> list:
    """The lane threads, started; each runs jobs until `stopped` is set.

    Shared by `main()` and by the API when it runs the worker in its own
    process (`PAKASH_EMBEDDED_WORKER`).
    """
    count = _WORKER_CONCURRENCY
    chat_count = min(_CHAT_WORKERS, count - 1) if count > 1 else 0

    def work(lane):
        while not stopped.is_set():
            try:
                worker.run_once(lane)
            except Exception:
                _log.exception("worker connection failed; retrying lane=%s", lane)
            stopped.wait(_POLL_SECONDS)

    lanes = ["interactive"] * chat_count + ["background"] * (count - chat_count)
    if count == 1:
        lanes = ["any"]
    threads = [
        threading.Thread(target=work, args=(lane,), name="worker-%s" % lane,
                         daemon=True)
        for lane in lanes
    ] + [threading.Thread(target=_purge, args=(worker, stopped),
                          name="worker-purge", daemon=True)]
    for thread in threads:
        thread.start()
    _log.info("job worker started threads=%d chat_threads=%d", count, chat_count)
    return threads


def _purge(worker, stopped: threading.Event) -> None:
    """Delete old finished jobs now and then. Every process does it; the
    DELETE is idempotent, so a second copy only finds nothing left."""
    while not stopped.is_set():
        try:
            deleted = worker.purge_finished_jobs(_RETENTION_DAYS)
            if deleted:
                _log.info("purged finished jobs count=%d", deleted)
        except Exception:
            _log.exception("purging finished jobs failed")
        stopped.wait(_PURGE_SECONDS)


def stop(threads: list, stopped: threading.Event) -> None:
    stopped.set()
    for thread in threads:
        thread.join(timeout=_POLL_SECONDS * 2)


def main() -> None:
    configure_logging()
    repository, worker = _build()
    repository.initialize()
    stopped = threading.Event()

    def on_signal(*_args) -> None:
        stopped.set()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    threads = start(worker, stopped)
    while not stopped.wait(_POLL_SECONDS):
        pass
    stop(threads, stopped)
    _log.info("job worker stopped")


if __name__ == "__main__":
    main()
