"""Always-running durable copilot worker.

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
from app.bl.copilot import CopilotService
from app.bl.schedule_service import ScheduleService
from app.bl.manager_chat import ManagerChatService
from app.common.activity import track_activity
from app.common.errors import NotFoundError
from app.common.config import Settings
from app.common.logging_setup import configure_logging
from app.common.redis_hub import RedisHub
from app.common.runtime_settings.runtime_settings_store import RuntimeSettingsStore
from app.dal.llm.budgets import share_slots
from app.dal.llm.openai_client import OpenAIJsonClient
from app.dal.llm.team_context import model_team
from app.dal.repository import Repository

_log = logging.getLogger("pakash.copilot.worker")
_SCAN_SECONDS = max(60, int(os.getenv("PAKASH_COPILOT_SCAN_SECONDS", "1800")))
_POLL_SECONDS = max(1, int(os.getenv("PAKASH_COPILOT_POLL_SECONDS", "1")))
_WORKER_CONCURRENCY = max(1, int(os.getenv("PAKASH_WORKER_CONCURRENCY", "4")))
_CHAT_WORKERS = max(1, int(os.getenv("PAKASH_CHAT_WORKERS", "1")))


class CopilotWorker:
    def __init__(self, repository, service, scan_seconds: int = _SCAN_SECONDS,
                 schedules=None, chat=None, compiler=None):
        self._repository = repository
        self._service = service
        self._scan_seconds = scan_seconds
        self._schedules, self._chat = schedules, chat
        self._compiler = compiler

    def enqueue_due(self, now: float = None) -> int:
        stamp = int(now if now is not None else time.time())
        bucket = stamp // self._scan_seconds
        count = 0
        for team in self._repository.list_teams():
            if self._repository.enqueue_copilot_job(
                team["id"], "scan:%s" % bucket
            ):
                count += 1
        return count

    def run_once(self, lane="any") -> int:
        self.enqueue_due()
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
            with model_team(job["team_id"]):
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
            self._service.scan(team_id, job["id"])
        elif job["kind"] == COMPILE_SOURCES:
            # Setup was saved: translate its rules, policies and notes for
            # the code scheduler now, so the first build need not (D32).
            self._compiler.compile(team_id)
        else:
            raise ValueError("Unknown job kind: %s" % job["kind"])

    def _fail(self, job):
        if job["kind"] == COMPILE_SOURCES:
            return  # Nothing is lost: the next build translates what is missing.
        if job["kind"] == "manager_chat":
            payload = job["payload"]
            self._repository.finish_chat_turn(payload["chat_id"], payload["message_id"],
                "לא הצלחנו להשלים את הבקשה. אפשר לשלוח אותה שוב", "error", {})
        else:
            self._repository.create_copilot_item(
                job["team_id"], "failure:%s" % job["id"], "failure", "system_health",
                "העבודה לא הושלמה", "אפשר לנסות שוב. ההתקדמות שנשמרה נשארה במערכת.",
                {"job_id": job["id"]}, job["id"],
            )


def _build():
    env = Settings()
    store = RuntimeSettingsStore(env)
    # Waits in the same model queue as the API when Redis is configured.
    share_slots(RedisHub(store))
    repository = Repository(store)
    llm = OpenAIJsonClient(store)
    schedules = ScheduleService(repository, llm, settings=store)
    return repository, CopilotWorker(
        repository, CopilotService(repository, schedules),
        schedules=schedules, chat=ManagerChatService(repository, llm, schedules),
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
        threading.Thread(target=work, args=(lane,), name="copilot-%s" % lane,
                         daemon=True)
        for lane in lanes
    ]
    for thread in threads:
        thread.start()
    _log.info("copilot worker started threads=%d chat_threads=%d", count, chat_count)
    return threads


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
    _log.info("copilot worker stopped")


if __name__ == "__main__":
    main()
