"""Always-running durable copilot worker.

Run with ``python -m app.worker``. PostgreSQL owns claiming and deduplication,
so restarting this process or running two copies cannot execute one job twice.
"""

import logging
import os
import signal
import threading
import time

from app.bl.copilot import CopilotService
from app.bl.interview_service import InterviewService
from app.bl.schedule_service import ScheduleService
from app.common.config.settings import Settings
from app.common.logging_setup import configure_logging
from app.common.runtime_settings.runtime_settings_store import RuntimeSettingsStore
from app.dal.llm.openai_client import OpenAIJsonClient
from app.dal.repository import Repository

_log = logging.getLogger("pakash.copilot.worker")
_SCAN_SECONDS = max(60, int(os.getenv("PAKASH_COPILOT_SCAN_SECONDS", "1800")))
_POLL_SECONDS = max(1, int(os.getenv("PAKASH_COPILOT_POLL_SECONDS", "15")))


class CopilotWorker:
    def __init__(self, repository, service, scan_seconds: int = _SCAN_SECONDS):
        self._repository = repository
        self._service = service
        self._scan_seconds = scan_seconds

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
        self._repository.recover_copilot_jobs()
        self.enqueue_due()
        processed = 0
        while True:
            job = self._repository.claim_copilot_job()
            if not job:
                return processed
            try:
                self._service.scan(job["team_id"], job["id"])
                self._repository.finish_copilot_job(job["id"])
            except Exception as exc:
                _log.exception("copilot job failed id=%s", job["id"])
                retry = int(job.get("attempts") or 0) < 3
                self._repository.finish_copilot_job(
                    job["id"], str(exc), retry=retry
                )
                if not retry:
                    self._repository.create_copilot_item(
                        job["team_id"], "failure:%s" % job["id"],
                        "failure", "system_health",
                        "משימת הקופיילוט נכשלה",
                        "המערכת ניסתה שלוש פעמים ולא הצליחה: %s" % str(exc),
                        {"job_id": job["id"]}, job["id"],
                    )
            processed += 1


def _build():
    env = Settings()
    store = RuntimeSettingsStore(env)
    repository = Repository(store)
    llm = OpenAIJsonClient(store)
    schedules = ScheduleService(repository, llm)
    interviews = InterviewService(repository, llm)
    return repository, CopilotWorker(
        repository, CopilotService(repository, schedules, interviews)
    )


def main() -> None:
    configure_logging()
    repository, worker = _build()
    repository.initialize()
    repository.recover_copilot_jobs()
    stopped = threading.Event()

    def stop(*_args) -> None:
        stopped.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    _log.info("copilot worker started")
    while not stopped.is_set():
        worker.run_once()
        stopped.wait(_POLL_SECONDS)
    _log.info("copilot worker stopped")


if __name__ == "__main__":
    main()
