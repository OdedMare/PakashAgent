"""Always-running durable copilot worker.

Run with ``python -m app.worker``. PostgreSQL owns claiming and deduplication,
so restarting this process or running two copies cannot execute one job twice.
"""

import logging
import os
import signal
import threading
import time

from app.bl.copilot.copilot import CopilotService
from app.bl.interview_service import InterviewService
from app.bl.schedule_service import ScheduleService
from app.bl.manager_chat import ManagerChatService
from app.common.activity import track_activity
from app.common.errors.errors import NotFoundError
from app.common.config.settings import Settings
from app.common.logging_setup.logging_setup import configure_logging
from app.common.runtime_settings.runtime_settings_store import RuntimeSettingsStore
from app.dal.llm import tracing
from app.dal.llm.openai_client import OpenAIJsonClient
from app.dal.repository import Repository

_log = logging.getLogger("pakash.copilot.worker")
_SCAN_SECONDS = max(60, int(os.getenv("PAKASH_COPILOT_SCAN_SECONDS", "1800")))
_POLL_SECONDS = max(1, int(os.getenv("PAKASH_COPILOT_POLL_SECONDS", "1")))


class CopilotWorker:
    def __init__(self, repository, service, scan_seconds: int = _SCAN_SECONDS,
                 schedules=None, chat=None):
        self._repository = repository
        self._service = service
        self._scan_seconds = scan_seconds
        self._schedules, self._chat = schedules, chat

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

    def run_once(self) -> int:
        self.enqueue_due()
        processed = 0
        while True:
            with self._repository.claim_copilot_job() as job:
                if not job:
                    return processed
                self._process(job)
            processed += 1

    def _process(self, job):
        try:
            self._execute(job)
            self._repository.finish_copilot_job(job["id"])
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
                self._schedules.run_generation(team_id, payload["schedule_id"])
        elif job["kind"] == "scan":
            self._service.scan(team_id, job["id"])
        else:
            raise ValueError("Unknown job kind: %s" % job["kind"])

    def _fail(self, job):
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
    tracing.init(env)
    store = RuntimeSettingsStore(env)
    repository = Repository(store)
    llm = OpenAIJsonClient(store)
    schedules = ScheduleService(repository, llm, settings=store)
    interviews = InterviewService(repository, llm)
    return repository, CopilotWorker(
        repository, CopilotService(repository, schedules, interviews),
        schedules=schedules, chat=ManagerChatService(repository, llm, schedules),
    )


def main() -> None:
    configure_logging()
    repository, worker = _build()
    repository.initialize()
    stopped = threading.Event()

    def stop(*_args) -> None:
        stopped.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    _log.info("copilot worker started")
    while not stopped.is_set():
        try:
            worker.run_once()
        except Exception:
            _log.exception("worker connection failed; retrying")
        stopped.wait(_POLL_SECONDS)
    tracing.flush()
    _log.info("copilot worker stopped")


if __name__ == "__main__":
    main()
