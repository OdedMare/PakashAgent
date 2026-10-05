"""The background worker that drives a range job to completion."""

import logging
import time
from threading import Event, Lock, Thread
from typing import Callable

from app.bl.schedule_service.constants import (
    GENERATION_FINISHED,
    GENERATION_HEARTBEAT_SECONDS,
    MAX_SPAN_ATTEMPTS,
    RETRY_BASE_SECONDS,
    RETRY_MAX_SECONDS,
)
from app.bl.schedule_service.context import ScheduleContext, progress_of
from app.bl.schedule_service.generation.job import GenerationJob
from app.bl.schedule_service.generation.stepper import GenerationStepper
from app.bl.schedule_service.rows import iso, now_stamp
from app.common.errors.errors import AgentError

_log = logging.getLogger("pakash.schedule")


def launch_thread(target, *args) -> None:
    # ponytail: the schedule itself checkpoints every day, but the process-
    # local runner does not survive a restart. A later POST /run resumes from
    # that checkpoint; use the existing durable worker only if unattended
    # restart recovery becomes a measured need.
    Thread(target=target, args=args, daemon=True).start()


class GenerationRunner:
    def __init__(
        self,
        context: ScheduleContext,
        stepper: GenerationStepper,
        launch: Callable = None,
        sleep: Callable = None,
    ):
        self._context = context
        self._repository = context.repository
        self._stepper = stepper
        self._launch = launch or launch_thread
        # Behind the same seam as `_launch`, and for the same reason: a test
        # exercising the retry must not pay the backoff it exists to describe.
        self._sleep = sleep or time.sleep
        self._lock = Lock()
        self._active = set()

    def queue(self, team_id: str, schedule_id: str) -> dict:
        """Start checkpointed generation and return immediately for polling.

        Safe to call repeatedly, and the browser is meant to: it is both the
        first launch and the way a job whose worker went away is picked back
        up. A job this process is already running is left alone and answered
        with its current state; anything else -- failed, cancelled, or
        "running" with nobody on it after a restart -- is relaunched from the
        first day that is not already complete.
        """
        schedule = self._repository.get_schedule(schedule_id, team_id)
        job = GenerationJob.of(schedule)
        if job.is_complete:
            return self._context.view(schedule, team_id)
        if not job.days:
            raise AgentError("לסידור הזה אין תהליך יצירה שניתן להמשיך")
        key = (team_id, schedule_id)
        if not self._claim(key):
            # Somebody is already on it. Saying so through the stored state
            # rather than starting a second worker is what keeps two browser
            # tabs polling the same job from generating every day twice.
            return self._context.view(schedule, team_id)
        # Only now that this call owns the job: a resume clears the stop flag
        # so the poller sees movement from the response itself.
        job.resume()
        try:
            schedule = self._repository.set_generation(
                schedule_id, team_id, job.to_dict()
            )
            self._launch(self._run, team_id, schedule_id)
        except Exception:
            self._release(key)
            raise
        return self._context.view(schedule, team_id)

    def progress(self, team_id: str, schedule_id: str) -> dict:
        """Just the progress of a job, for the poll that watches it.

        The full schedule carries every slot, every assignment and a fresh
        audit over both, which is a great deal of arithmetic to repeat for an
        answer that is usually "still on day three".
        """
        return progress_of(self._repository.get_schedule(schedule_id, team_id))

    # -- the worker ----------------------------------------------------------

    def _run(self, team_id: str, schedule_id: str) -> None:
        """Finish a range behind the short POST that launched it."""
        stop_beating = self._start_heartbeat(team_id, schedule_id)
        try:
            self._loop(team_id, schedule_id)
        except Exception as exc:
            # The stepper checkpoints a failed span before raising. The
            # poller reads that state and offers retry.
            _log.exception("schedule generation failed id=%s", schedule_id)
            self._record_crash(team_id, schedule_id, exc)
        finally:
            stop_beating()
            self._release((team_id, schedule_id))

    def _loop(self, team_id: str, schedule_id: str) -> None:
        while True:
            try:
                schedule = self._stepper.generate_next(
                    team_id, schedule_id, light=True
                )
            except Exception as exc:
                # A span with attempts left goes back in the queue rather
                # than taking the rest of the period down with it.
                if not self._requeue_failed_span(team_id, schedule_id, exc):
                    raise
                continue
            if GenerationJob.of(schedule).status in GENERATION_FINISHED:
                return

    def _record_crash(
        self, team_id: str, schedule_id: str, error: Exception
    ) -> None:
        try:
            schedule = self._repository.get_schedule(schedule_id, team_id)
            job = GenerationJob.of(schedule)
            if job.crash(error):
                self._repository.set_generation(
                    schedule_id, team_id, job.to_dict()
                )
        except Exception:
            _log.exception(
                "could not persist generation failure id=%s", schedule_id
            )

    def _requeue_failed_span(
        self, team_id: str, schedule_id: str, error: Exception
    ) -> bool:
        """Put a failed span back in the queue. False when it is out of tries.

        Bounded on purpose: the failures that are not transient — a model
        rejecting the schema, a profile with no shifts — repeat identically.
        A cancelled job is never requeued; the manager stopping is not
        something to recover from.
        """
        try:
            schedule = self._repository.get_schedule(schedule_id, team_id)
        except Exception:
            return False
        job = GenerationJob.of(schedule)
        target = None if job.cancel_requested else job.first_failed()
        if target is None:
            return False
        attempts = int(target.get("attempts") or 0)
        if attempts >= MAX_SPAN_ATTEMPTS:
            return False
        job.requeue(target)
        self._repository.set_generation(schedule_id, team_id, job.to_dict())
        _log.warning(
            "schedule span %s..%s failed (attempt %d/%d), retrying: %s",
            iso(target.get("date")),
            iso(target.get("through")) or iso(target.get("date")),
            attempts, MAX_SPAN_ATTEMPTS, error,
        )
        self._pause_before_retry(attempts)
        return True

    def _pause_before_retry(self, attempt: int) -> None:
        self._sleep(min(
            RETRY_BASE_SECONDS * (2 ** max(0, attempt - 1)),
            RETRY_MAX_SECONDS,
        ))

    def _start_heartbeat(self, team_id: str, schedule_id: str):
        """Say "still here" every few seconds. Returns the way to stop.

        A separate thread rather than a stamp at each checkpoint, because the
        thing worth reporting is exactly what a checkpoint cannot report: a
        day held open by a model call that may never return. A repository
        that cannot beat only means the browser sees a job that never looks
        stale.
        """
        touch = getattr(self._repository, "touch_generation", None)
        if touch is None:
            return lambda: None
        stop = Event()

        def beat() -> None:
            while not stop.wait(GENERATION_HEARTBEAT_SECONDS):
                try:
                    touch(schedule_id, team_id, now_stamp())
                except Exception:
                    # A missed beat costs one relaunch, which is recoverable.
                    # Killing the generation over it would not be.
                    _log.warning(
                        "generation heartbeat failed id=%s", schedule_id
                    )

        Thread(target=beat, daemon=True).start()
        return stop.set

    # -- ownership -----------------------------------------------------------

    def _claim(self, key: tuple) -> bool:
        with self._lock:
            if key in self._active:
                return False
            self._active.add(key)
            return True

    def _release(self, key: tuple) -> None:
        with self._lock:
            self._active.discard(key)
