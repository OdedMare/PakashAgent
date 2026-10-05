"""Opening a period: generated whole, opened blank, or opened as a range job."""

from typing import List, Optional

from app.bl.scheduler import MODE_DAY, MODE_WEEK, build_slots, plan_spans
from app.bl.schedule_service.constants import ACTION_GENERATED, ACTION_OPENED
from app.bl.schedule_service.context import ScheduleContext
from app.bl.schedule_service.generation.history import AssignmentHistory
from app.bl.schedule_service.generation.job import GenerationJob
from app.bl.schedule_service.generation.pins import required_rows
from app.bl.schedule_service.profile_gate import ProfileGate
from app.bl.schedule_service.rows import iso, slot_index
from app.common.errors.errors import AgentError
from app.dal.repository.schedules import ASSIGNED_BY_MANAGER, week_bounds


class PeriodBuilder:
    def __init__(
        self,
        context: ScheduleContext,
        scheduler,
        gate: ProfileGate,
        history: AssignmentHistory,
        settings=None,
    ):
        self._context = context
        self._repository = context.repository
        self._scheduler = scheduler
        self._gate = gate
        self._history = history
        # The live runtime-settings store, or `None`. Optional because every
        # test double would otherwise have to supply one; its absence reads
        # as the default rather than as an error.
        self._settings = settings

    def generate(
        self,
        team_id: str,
        starts_on: Optional[str] = None,
        ends_on: Optional[str] = None,
        instructions: str = "",
        required_assignments: Optional[List[dict]] = None,
    ) -> dict:
        """Build a period in one call and store it as a draft.

        The interview must have produced a profile first: without the shift
        vocabulary there is nothing to build a grid out of, and guessing one
        would be exactly the hardcoding D9 forbids.
        """
        profile = self._gate.buildable_profile(team_id)
        starts_on, ends_on = _bounds(starts_on, ends_on)
        result = self._scheduler.generate(
            profile,
            starts_on,
            ends_on,
            availability=self._repository.availability(
                team_id, starts_on, ends_on
            ),
            history=self._history.before(team_id, starts_on),
            instructions=instructions,
            required_assignments=required_assignments,
            preferences=self._context.active_preferences(team_id),
        )
        schedule_id = self._store(team_id, starts_on, ends_on, result)
        self._repository.append_change(
            team_id, ACTION_GENERATED, schedule_id=schedule_id,
            reason=instructions, agent_reason=result["summary"],
        )
        view = self._context.fresh_view(schedule_id, team_id)
        view["notes"] = result["notes"]
        view["summary"] = result["summary"]
        return view

    def create_blank(
        self,
        team_id: str,
        starts_on: Optional[str] = None,
        ends_on: Optional[str] = None,
    ) -> dict:
        """An empty period the manager fills in themselves (D18).

        The boss authoring rather than generating (D6). No model is called:
        which dates fall in a period and which shifts run on them is
        arithmetic. The profile is still required — the manual path skips
        the agent, not the interview (D9).
        """
        profile = self._gate.buildable_profile(team_id)
        starts_on, ends_on = _bounds(starts_on, ends_on)
        slots = build_slots(profile, starts_on, ends_on)
        if not slots:
            # The vocabulary exists but none of it runs in this window. The
            # interview is finished, so this points at the dates instead.
            raise AgentError(
                "לא ניתן לבנות סידור: אף משמרת מוגדרת לא חלה בתאריכים האלה"
            )
        schedule = self._repository.create_schedule(team_id, starts_on, ends_on)
        self._repository.replace_slots(schedule["id"], team_id, slots)
        self._repository.append_change(
            team_id, ACTION_OPENED, schedule_id=schedule["id"],
            agent_reason="הסידור נפתח ריק לשיבוץ ידני",
        )
        return self._context.fresh_view(schedule["id"], team_id)

    def start_generation(
        self,
        team_id: str,
        starts_on: Optional[str] = None,
        ends_on: Optional[str] = None,
        instructions: str = "",
        required_assignments: Optional[List[dict]] = None,
    ) -> dict:
        """Open a persistent range job; each later request generates one span."""
        profile = self._gate.buildable_profile(team_id)
        starts_on, ends_on = _bounds(starts_on, ends_on)
        slots = build_slots(profile, starts_on, ends_on)
        if not slots:
            raise AgentError(
                "לא ניתן לבנות סידור: לא הוגדרו משמרות לתקופה הזו"
            )
        schedule = self._repository.create_schedule(team_id, starts_on, ends_on)
        stored = self._repository.replace_slots(schedule["id"], team_id, slots)
        pinned = required_rows(required_assignments or [], stored, profile)
        if pinned:
            self._repository.replace_assignments(schedule["id"], team_id, pinned)
        # The mode is read once, here, and stored on the job. A manager who
        # changes the setting while a build is running is choosing how the
        # *next* one runs.
        mode = self._generation_mode()
        job = GenerationJob.open(
            plan_spans(profile, starts_on, ends_on, mode),
            total_days=len({iso(slot.get("slot_date")) for slot in stored}),
            mode=mode,
            instructions=instructions,
            required=required_assignments or [],
        )
        schedule = self._repository.set_generation(
            schedule["id"], team_id, job.to_dict()
        )
        return self._context.view(schedule, team_id)

    def start_day_generation(
        self, team_id: str, schedule_id: str, day: str, instructions: str = "",
    ) -> dict:
        """Prepare one existing draft day for regeneration.

        Manager-placed rows on that date are pins, not suggestions: the agent
        fills around them. Generated/imported rows are replaced for that day,
        while every other date stays untouched. One date whatever the mode: a
        manager rebuilding Tuesday asked for Tuesday.
        """
        schedule = self._repository.get_schedule(schedule_id, team_id)
        if schedule.get("status") != "draft":
            raise AgentError("יש להחזיר את הסידור לטיוטה לפני שיבוץ יום")
        target = iso(day)
        if not target or not any(
            iso(slot.get("slot_date")) == target
            for slot in schedule.get("slots") or []
        ):
            raise AgentError("היום שנבחר אינו קיים בסידור הזה")
        job = GenerationJob.open(
            [{"date": target, "through": target, "dates": [target]}],
            total_days=1,
            mode=MODE_DAY,
            instructions=instructions,
            required=_manager_pins_on(schedule, target),
        )
        return self._context.view(
            self._repository.set_generation(schedule_id, team_id, job.to_dict()),
            team_id,
        )

    def _store(
        self, team_id: str, starts_on: str, ends_on: str, result: dict
    ) -> str:
        schedule = self._repository.create_schedule(team_id, starts_on, ends_on)
        slots = self._repository.replace_slots(
            schedule["id"], team_id, result["slots"]
        )
        index = slot_index(slots)
        rows = [
            {
                "slot_id": index[(item["shift"], item["date"])],
                "employee": item["employee"],
                "reason": item["reason"],
            }
            for item in result["assignments"]
            if (item["shift"], item["date"]) in index
        ]
        self._repository.replace_assignments(schedule["id"], team_id, rows)
        return schedule["id"]

    def _generation_mode(self) -> str:
        """How wide one model call is for the next build the manager opens.

        Read live from the settings store, so a mode saved in the panel
        applies to the next period without a restart. No store reads as the
        default: a missing setting is not a reason to run at a width nobody
        chose.
        """
        settings = getattr(self._settings, "get", None)
        if settings is None:
            return MODE_DAY
        mode = getattr(settings(), "schedule_generation_mode", MODE_DAY)
        return mode if mode in (MODE_DAY, MODE_WEEK) else MODE_DAY


def _bounds(starts_on: Optional[str], ends_on: Optional[str]) -> tuple:
    if not starts_on or not ends_on:
        return week_bounds()
    return starts_on, ends_on


def _manager_pins_on(schedule: dict, target: str) -> List[dict]:
    return [
        {
            "employee": row.get("employee"),
            "shift": row.get("shift"),
            "date": target,
        }
        for row in schedule.get("assignments") or []
        if iso(row.get("date")) == target
        and row.get("source") == ASSIGNED_BY_MANAGER
    ]
