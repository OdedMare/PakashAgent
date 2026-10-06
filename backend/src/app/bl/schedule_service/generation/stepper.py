"""One step of a range job: generate the next span and checkpoint it."""

from typing import List

from app.bl.schedule_service.constants import ACTION_GENERATED
from app.bl.schedule_service.context import ScheduleContext
from app.bl.schedule_service.generation.history import AssignmentHistory
from app.bl.schedule_service.generation.job import GenerationJob, span_dates
from app.bl.schedule_service.generation.pins import (
    model_assignment,
    persisted_rows,
    span_pins,
)
from app.bl.schedule_service.profile_gate import ProfileGate
from app.bl.schedule_service.rows import iso
from app.common.errors.errors import AgentError, ModelOutputError


class GenerationStepper:
    def __init__(
        self,
        context: ScheduleContext,
        scheduler,
        gate: ProfileGate,
        history: AssignmentHistory,
    ):
        self._context = context
        self._repository = context.repository
        self._scheduler = scheduler
        self._gate = gate
        self._history = history

    def generate_next(
        self, team_id: str, schedule_id: str, light: bool = False
    ) -> dict:
        """Generate the next pending/failed span and checkpoint the result.

        `light` returns the progress counter instead of the audited period.
        The background loop is the caller that wants it: it reads one field —
        whether the job is still running — and a full audit per generated day
        thrown away every time was the cost of not having it. The HTTP route
        still asks for the whole schedule, because its caller renders it.
        """
        schedule = self._repository.get_schedule(schedule_id, team_id)
        job = GenerationJob.of(schedule)
        if not job.days:
            raise AgentError("לסידור הזה אין תהליך יצירה שניתן להמשיך")
        if job.is_complete:
            return self._context.result(schedule, team_id, light)
        # Checked before the span is chosen, not after the model answers: a
        # manager who stopped waiting must not pay for one more call.
        if job.cancel_requested:
            return self._stop(schedule_id, team_id, job, light)

        target = job.next_target()
        if target is None:
            job.mark_complete()
            self._repository.set_generation(schedule_id, team_id, job.to_dict())
            return self._context.result(
                self._repository.get_schedule(schedule_id, team_id),
                team_id, light,
            )

        job.start_span(target)
        self._repository.set_generation(schedule_id, team_id, job.to_dict())
        profile = self._gate.buildable_profile(team_id)
        self._run_span(team_id, schedule, profile, job, target)

        # A stop asked for while the model was answering. The day that just
        # finished is kept -- it is paid for and correct -- and the job ends
        # here rather than taking the next one.
        if self._cancel_requested(schedule_id, team_id):
            return self._stop(schedule_id, team_id, job, light)
        if job.advance():
            self._log_completion(team_id, schedule_id, job)
        schedule = self._repository.set_generation(
            schedule_id, team_id, job.to_dict()
        )
        view = self._context.result(schedule, team_id, light)
        view["notes"] = job.notes()
        view["summary"] = job.summary()
        return view

    def stop(self, team_id: str, schedule_id: str) -> dict:
        """Stop waiting on a running job. **Keeps every finished day.**

        Cooperative rather than forceful: a model call already in flight is
        not interruptible from here, so this records the decision and the
        worker stops at the next day boundary. The period is an ordinary
        draft the moment this returns, and `POST /run` picks the rest up.
        """
        schedule = self._repository.get_schedule(schedule_id, team_id)
        job = GenerationJob.of(schedule)
        if not job.days:
            raise AgentError("לסידור הזה אין תהליך יצירה שניתן לעצור")
        if job.is_complete:
            return self._context.view(schedule, team_id)
        return self._stop(schedule_id, team_id, job, light=False)

    def _run_span(
        self,
        team_id: str,
        schedule: dict,
        profile: dict,
        job: GenerationJob,
        target: dict,
    ) -> None:
        """Ask the model for one span and checkpoint either outcome.

        A failure is checkpointed as failed and re-raised: the caller of
        `/next` asked for a date and deserves the error. Deciding to *try
        again* belongs to the durable loop in `GenerationRunner`.
        """
        schedule_id = schedule["id"]
        dates = span_dates(target)
        try:
            result = self._ask_model(
                team_id, schedule, profile, job, target, dates
            )
            fresh = self._repository.get_schedule(schedule_id, team_id)
            rows = persisted_rows(fresh, result.get("assignments") or [], dates)
            self._write_span(schedule_id, team_id, dates, rows)
            job.complete_span(target, result)
        except Exception as exc:
            job.fail_span(target, exc)
            if isinstance(exc, ModelOutputError) and job.split(target):
                self._repository.set_generation(schedule_id, team_id, job.to_dict())
                return
            self._repository.set_generation(schedule_id, team_id, job.to_dict())
            raise

    def _ask_model(
        self,
        team_id: str,
        schedule: dict,
        profile: dict,
        job: GenerationJob,
        target: dict,
        dates: List[str],
    ) -> dict:
        day = iso(target.get("date"))
        through = iso(target.get("through")) or day
        return self._scheduler.generate_span(
            profile,
            day,
            through,
            availability=self._repository.availability(
                team_id, iso(schedule.get("starts_on")), iso(schedule.get("ends_on"))),
            history=self._history.before(team_id, iso(schedule.get("starts_on"))),
            instructions=job.get("instructions") or "",
            # What the manager pinned when the job was opened, plus anything
            # placed by hand on these dates since -- the board stays writable
            # while a period is being built.
            required_assignments=span_pins(
                schedule, job.get("required_assignments") or [], dates
            ),
            already_scheduled=[
                model_assignment(row) for row in schedule.get("assignments") or []
            ],
            preferences=self._context.active_preferences(team_id),
            split_on_failure=False,  # The job checkpoints each smaller span separately.
        )

    def _write_span(
        self, schedule_id: str, team_id: str, dates: List[str], rows: List[dict],
    ) -> None:
        """Persist one span's checkpoint, touching only that span's dates.

        Falls back to rewriting the period on a repository that predates
        `replace_span_assignments`, because a checkpoint that raises loses the
        model answer it was holding — the one outcome worse than writing too
        much.
        """
        scoped = getattr(self._repository, "replace_span_assignments", None)
        if scoped is None:
            self._repository.replace_assignments(schedule_id, team_id, rows)
            return
        wanted = set(dates)
        scoped(
            schedule_id, team_id, sorted(wanted),
            [row for row in rows if row.get("date") in wanted],
        )

    def _log_completion(
        self, team_id: str, schedule_id: str, job: GenerationJob
    ) -> None:
        if not job.mark_logged():
            return
        self._repository.append_change(
            team_id,
            ACTION_GENERATED,
            schedule_id=schedule_id,
            reason=job.get("instructions") or "",
            agent_reason=job.summary(),
        )

    def _cancel_requested(self, schedule_id: str, team_id: str) -> bool:
        """Whether a stop was asked for while a span was being generated.

        Re-read rather than remembered: the request arrives on a different
        thread, through the database, after this method took its copy.
        """
        try:
            schedule = self._repository.get_schedule(schedule_id, team_id)
        except Exception:
            return False
        return GenerationJob.of(schedule).cancel_requested

    def _stop(
        self, schedule_id: str, team_id: str, job: GenerationJob, light: bool,
    ) -> dict:
        job.stop()
        return self._context.result(
            self._repository.set_generation(schedule_id, team_id, job.to_dict()),
            team_id, light,
        )
