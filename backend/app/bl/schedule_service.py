"""Persistence and orchestration around the schedule.

`Scheduler` decides who works; `ChangeAgent` decides what a request means;
`audit` recomputes the countable facts. This decides what to remember and in
what order to do things — which is why it, and not they, owns the repository.

Two shapes are load-bearing here:

- **Propose and apply are separate calls.** A proposal writes nothing. The
  manager confirms in between, and only then does anything land
  ([D8](../../../docs/DECISIONS.md#d8--two-reasons-both-required)). A drag on
  the calendar goes through exactly the same two steps as a sentence typed at
  the agent — the gesture is a proposal, not an edit.
- **Every response carrying a schedule carries its warnings.** They are
  advisory and never gate anything
  ([D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)):
  a schedule with warnings is still a `200` and still renders.

Every method takes the team from the caller's signed session and passes it to
the repository, which filters on it. It is never taken from a request body.
"""

import datetime
import logging
import time
from threading import Event, Lock, Thread
from typing import Any, Dict, List, Optional

from app.bl.audit import audit, fairness, shift_stats
from app.bl.briefing import (
    BriefingAgent,
    TRIGGER_OPENED,
)
from app.bl.changes import ChangeAgent, OP_ASSIGN, OP_REMOVE, OP_SWAP
from app.bl.export import as_workbook, filename
from app.bl.importer import infer, read_grids
from app.bl.learn import RuleLearner, observe, observe_corrections
from app.bl import rotation
from app.bl.placement import check as check_placement
from app.bl.profile_service import ProfileService
from app.bl.planner import PlanningAgent
from app.bl.simulate import simulate as simulate_operations
from app.bl.tools import ScheduleTools
from app.bl.scheduler import (
    MODE_DAY, MODE_WEEK, Scheduler, build_slots, effective_availability,
    plan_spans,
)
from app.common.errors import (
    AgentError, NotFoundError, ProfileIncompleteError,
)
from app.dal.repository.schedules import (
    ASSIGNED_BY_IMPORT,
    ASSIGNED_BY_MANAGER,
    PREFERENCE_ACTIVE,
    PREFERENCE_EMPLOYEE,
    PREFERENCE_GENERAL,
    PREFERENCE_SUGGESTED,
    SOURCE_AGENT,
    SOURCE_MANAGER,
    week_bounds,
)

# What the change log calls each kind of entry. Stored rather than derived so
# the history stays readable even as the code that wrote it changes.
ACTION_GENERATED = "generated"
ACTION_PUBLISHED = "published"
ACTION_MOVED = "moved"
ACTION_ASSIGNED = "assigned"
ACTION_REMOVED = "removed"
ACTION_SWAPPED = "swapped"
ACTION_CONSTRAINT = "constraint"
# A period opened empty for the manager to fill in themselves (D18). Distinct
# from `generated` on purpose: the history should say which of the two things
# in D6 happened, and both producing a schedule is exactly what makes them
# worth telling apart later.
ACTION_OPENED = "opened"
# A period read out of a file the workplace already had (D7). Distinct from
# both `generated` and `opened` for the same reason those are distinct from
# each other: the history should say where a schedule came from, and
# "imported from the manager's own spreadsheet" is a third origin.
ACTION_IMPORTED = "imported"

# How far back `learn_from_changes` reads. Generous, because a rule the
# manager keeps applying by hand shows up as a handful of corrections spread
# across months -- a short window would see one of each and find nothing. The
# rows are counted rather than sent, so the cost of a wide window is
# arithmetic, not context.
_LEARN_HISTORY = 500

_log = logging.getLogger("pakash.schedule")

# The states a persisted range job can be in. Written into the schedule's
# `generation` document and read back by the browser, so they are named here
# rather than spelled out at every comparison.
GENERATION_RUNNING = "running"
GENERATION_COMPLETE = "complete"
GENERATION_FAILED = "failed"
# The manager stopped waiting. Distinct from `failed` on purpose: nothing
# went wrong, and the difference is what the board says to them. Both resume
# the same way -- from the first day that is not already complete.
GENERATION_CANCELLED = "cancelled"
_GENERATION_RESUMABLE = (GENERATION_FAILED, GENERATION_CANCELLED)

# How often a worker says it is still there.
#
# **This is what makes polling honest.** `llm_timeout_seconds` defaults to no
# limit, so a day held open by a model that is slow and a day held open by a
# model that is hung look identical from the outside -- both are simply
# "running", and the browser used to poll one of them forever. A beat every
# few seconds separates them: a job whose heartbeat is moving is working, and
# a job whose heartbeat has stopped has lost its worker (a restarted process,
# a killed thread) and can be relaunched by the next POST /run.
#
# Deliberately short relative to the client's staleness window: a beat is one
# tiny UPDATE, and missing four of them in a row has to mean something.
GENERATION_HEARTBEAT_SECONDS = 20

# How many times one span is re-asked before the job is called failed.
#
# **This is what stops a single blip from costing the whole build.** Every
# failure here was already checkpointed and retryable — but only by a person
# noticing and pressing continue, because the worker gave up on the first
# exception and the browser stopped polling a job marked `failed`. A dropped
# connection on day twelve of thirty left twenty-nine days of work parked
# behind a button nobody was watching.
#
# Bounded, because the failures that are not transient — a model that rejects
# the schema, a profile the grid cannot be built from — repeat identically and
# retrying them only burns the model server. Three is enough for a restarted
# Ollama or a proxy hiccup and short enough that a real error still surfaces
# within a minute.
_MAX_SPAN_ATTEMPTS = 3
# Waited between attempts, geometric. The failure this is for is a model
# server that is briefly unavailable — mid-restart, or working through a
# queue — and answering the same second is how a retry hits exactly the state
# it backed off from. Capped so the pause never dwarfs the call.
_RETRY_BASE_SECONDS = 2.0
_RETRY_MAX_SECONDS = 15.0

# How long a fairness history read is reused across the spans of one build.
#
# It reads every *earlier* period, so by construction nothing inside the
# current build can change it — yet it was re-read, and re-joined, once per
# generated date. On a month at one call per day that is thirty scans of the
# team's whole history to compute a tally that was identical every time.
_HISTORY_CACHE_SECONDS = 300



def _launch_thread(target, *args) -> None:
    # ponytail: the schedule itself checkpoints every day, but the process-
    # local runner does not survive a restart. A later POST /run resumes from
    # that checkpoint; use the existing durable worker only if unattended
    # restart recovery becomes a measured need.
    Thread(target=target, args=args, daemon=True).start()

# What a manually placed row says for itself when the manager gave no
# sentence of their own. `assignments.reason` is NOT NULL and D8 is not
# relaxed here -- this states plainly that a person placed it, rather than
# manufacturing a judgment the agent never made. It is the same honesty
# `_moved_from` applies to a dragged shift.
MANUAL_REASON = "שובץ ידנית על ידי המנהל"

# What an imported row says for itself. The agent made no judgment about it
# -- it is a record of what the workplace already did -- so claiming a reason
# here would be inventing one. `assignments.reason` stays NOT NULL and D8 is
# answered the same way the manual path answers it: by a different voice
# saying plainly where the row came from.
IMPORTED_REASON = "יובא מקובץ סידור קיים"


class ScheduleService:
    def __init__(
        self, repository, llm, launch=None, settings=None, sleep=None,
    ):
        self._repository = repository
        # The live runtime-settings store, or `None`. Optional because most of
        # this class has no settings to read and every test double would
        # otherwise have to supply one; `_generation_mode` treats its absence
        # as the default rather than as an error.
        self._settings = settings
        self._scheduler = Scheduler(llm)
        self._changes = ChangeAgent(llm)
        self._briefing = BriefingAgent(llm)
        self._learner = RuleLearner(llm)
        # Read-only tools, and the loop that runs them. `PlanningAgent` is
        # handed the tools rather than the repository, so the answering path
        # has no route to a write even by accident.
        self._tools = ScheduleTools(repository)
        self._planner = PlanningAgent(llm, self._tools)
        self._profiles = ProfileService(repository)
        self._launch = launch or _launch_thread
        # Behind the same seam as `_launch`, and for the same reason: a test
        # exercising the retry must not pay the backoff it exists to describe.
        self._sleep = sleep or time.sleep
        self._generation_lock = Lock()
        self._active_generations = set()
        # (team, before) -> (expires_at, rows). See `_HISTORY_CACHE_SECONDS`.
        self._history_cache = {}
        self._history_lock = Lock()

    # -- reading -----------------------------------------------------------

    def current(self, team_id: str, role: str = "boss") -> Optional[dict]:
        """The period in play, audited, or None when there is none yet.

        A member sees only published schedules. A draft is the manager's
        working state, and publishing is the act that makes it the team's
        ([D5](../../../docs/DECISIONS.md#d5--employees-are-read-only)).
        """
        schedule = self._repository.current_schedule(
            team_id, published_only=(role != "boss")
        )
        if schedule is None:
            return None
        return self._view(schedule, team_id)

    def get(self, schedule_id: str, team_id: str) -> dict:
        return self._view(
            self._repository.get_schedule(schedule_id, team_id), team_id
        )

    def list_periods(self, team_id: str) -> List[dict]:
        return self._repository.list_schedules(team_id)

    def period_at(
        self, team_id: str, day: str, role: str = "boss"
    ) -> Optional[dict]:
        """The stored period containing `day`, or None when none does.

        What the board opens on. The manager's operational home screen shows
        the week they are actually in, and "which stored period covers today"
        is a comparison of two dates -- arithmetic, so it is answered here
        rather than by asking the client to guess from `list_periods`.

        A member gets published periods only, exactly as `current()` does:
        the board is reachable from the read-only side and a draft is still
        the manager's working state until they publish it (D5).
        """
        wanted = _iso(day)
        if not wanted:
            raise AgentError("התאריך אינו תקין")
        for period in self._repository.list_schedules(team_id):
            if role != "boss" and period.get("status") != "published":
                continue
            if _iso(period["starts_on"]) <= wanted <= _iso(period["ends_on"]):
                return self._view(
                    self._repository.get_schedule(period["id"], team_id),
                    team_id,
                )
        return None

    def check_placement(
        self,
        team_id: str,
        employee: str,
        shift_name: str,
        slot_date: str,
        schedule_id: Optional[str] = None,
        moving_assignment_id: str = "",
    ) -> dict:
        """What a placement would cost, before it is made. Writes nothing.

        **No model call.** This is `bl/placement.py` handed the stored
        schedule, and it is what makes the board work with the agent
        unavailable: a drag is validated, explained in Hebrew, and offered
        deterministic alternatives without a single token being generated.

        It does not gate the write that follows. The manager may place
        somebody this reports on, and `assign`/`move` will store it —
        the audit advises and never blocks
        ([D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).
        Checking first only moves the same information to before the click,
        where it is cheaper to act on.
        """
        schedule = self._require_schedule(team_id, schedule_id)
        profile = self._repository.team_profile(team_id) or {}
        window = _window(schedule)
        return check_placement(
            schedule,
            profile,
            employee=employee,
            shift_name=shift_name,
            slot_date=slot_date,
            availability=[
                {
                    "employee": row.get("employee"),
                    "date": _iso(row.get("constraint_date")),
                    "shift": row.get("shift_name") or "",
                    "available": row.get("available"),
                    "start_time": row.get("start_time") or "",
                    "end_time": row.get("end_time") or "",
                    "is_hard": row.get("is_hard", True),
                    "reason": row.get("reason") or "",
                }
                for row in self._repository.availability(
                    team_id, window[0], window[1]
                )
            ],
            moving_assignment_id=moving_assignment_id,
        )

    def overview(self, team_id: str, role: str = "boss") -> dict:
        """Everything the management area opens with, in one call.

        The team, the roster, the shift vocabulary, the current period and
        its warnings, the constraints, and the recent history. One request
        rather than six because they are read together and a half-loaded
        management screen is worse than a slightly slower one.
        """
        profile = self._repository.team_profile(team_id) or {}
        schedule = self.current(team_id, role)
        window = _window(schedule)
        return {
            "profile": profile,
            "employees": _employees(profile),
            "shifts": _shifts(profile),
            "schedule": schedule,
            # Dates out of SQL are `datetime.date`; the contract declares
            # strings. Normalised on the way out for the reason `_dated`
            # gives -- these three lists are read straight from the
            # repository rather than through `_view`, so they need it here.
            "periods": [_period(row) for row in
                        self._repository.list_schedules(team_id)],
            "availability": [
                dict(row, constraint_date=_iso(row.get("constraint_date")))
                for row in self._repository.availability(
                    team_id, window[0], window[1]
                )
            ],
            "changes": [
                _change(row)
                for row in self._repository.change_log(team_id, limit=40)
            ],
            # The period in numbers, for the control room's charts. Computed
            # here by `audit.py` rather than in the browser, for the same
            # reason `personal_summary` is: a chart drawn from a second
            # implementation of the hours arithmetic would eventually
            # disagree with the warning printed beside it. A report, never a
            # grade -- nothing here gates publishing (D3).
            "stats": self._stats(team_id, profile, schedule),
        }

    def _stats(
        self, team_id: str, profile: dict, schedule: Optional[dict]
    ) -> dict:
        """The current period's numbers, or empty totals when there is none.

        Reads the same assignments, slots and warnings the calendar and the
        audit already render, so the charts cannot drift from the grid they
        sit under. Availability is re-read over the period's own window,
        which is what makes the constraint figures about *this* week rather
        than about everything ever recorded.
        """
        if not schedule:
            return shift_stats([], _shifts(profile), _employees(profile))
        window = _window(schedule)
        return shift_stats(
            [
                {
                    "employee": row.get("employee"),
                    "shift": row.get("shift"),
                    "date": _iso(row.get("date")),
                }
                for row in schedule.get("assignments") or []
            ],
            _shifts(profile),
            _employees(profile),
            # Carrying `headcount`, so the coverage percentage is measured
            # against what this period's grid actually asks for rather than
            # against a requirement recomputed from the current profile.
            slots=[
                {
                    "shift_name": slot.get("shift_name"),
                    "slot_date": _iso(slot.get("slot_date")),
                    "headcount": slot.get("headcount"),
                }
                for slot in schedule.get("slots") or []
            ],
            warnings=schedule.get("warnings") or [],
            # The roster's shadow-shift flags, so a trainee does not fill a
            # seat on the chart that the warning below it still calls empty.
            profile=profile,
            availability=[
                {
                    "employee": row.get("employee"),
                    "date": _iso(row.get("constraint_date")),
                    "shift": row.get("shift_name") or "",
                    "available": row.get("available"),
                    "start_time": row.get("start_time") or "",
                    "end_time": row.get("end_time") or "",
                    "is_hard": row.get("is_hard", True),
                }
                for row in self._repository.availability(
                    team_id, window[0], window[1]
                )
            ],
        )

    # -- generating --------------------------------------------------------

    def _buildable_profile(self, team_id: str) -> dict:
        """The profile, or a refusal that says what is still missing.

        Both building paths ask this one question, so there is one answer to
        it. `generate` and `create_blank` differ in whether a model runs;
        they do not differ in what a profile has to contain before a grid
        exists, and when they each checked separately the manual path grew a
        second, vaguer definition of "not enough".

        Two distinct failures, deliberately not merged:

        - **No profile at all.** The interview was never run. There is
          nothing to resume, so this stays a plain `AgentError`.
        - **A profile that cannot carry a grid.** The interview *was* run and
          ended early through `interview_service.end`, which is allowed to
          write a partial profile and records what it still owes on
          `completeness`. That record is read back here rather than
          recomputed, so the gate and the agent's own answer to *"what are
          you missing"* can never drift apart.

        The second case used to fail identically to a broken backend: the
        profile passed a `if not profile` check, `build_slots` returned an
        empty list, and both buttons answered 502 with no way forward. It is
        a `ProfileIncompleteError` now because the manager can fix it -- the
        missing topics travel with the error and the interview is where they
        get filled in.

        Shift vocabulary is the only true stop. Missing rules or employees
        degrade the result, and refusing over them would be worse than
        building a thin week: D9 forbids inventing shift names, but nothing
        forbids scheduling a roster the agent knows little about.
        """
        profile = self._repository.team_profile(team_id)
        if not profile:
            raise AgentError(
                "צריך להשלים את ראיון ההיכרות לפני בניית סידור"
            )
        if _has_shifts(profile):
            return profile
        # Asked only once the answer is known to be a refusal. `profile_gaps`
        # is the agent's own account of what the interview never taught, and
        # it is read here to *explain* this failure rather than to detect it:
        # its confirmed-interview shortcut reports no gaps at all, which is
        # right for the question it answers and would be wrong for this one.
        gaps = self._tools.profile_gaps(team_id)
        raise ProfileIncompleteError(
            "לא ניתן לבנות סידור: לא הוגדרו סוגי משמרות בראיון ההיכרות. "
            "אפשר להשלים את החסר בשיחה עם הסוכן.",
            gaps=gaps.get("gaps") or [],
            blocks=gaps.get("blocks") or [],
        )


    def generate(
        self,
        team_id: str,
        starts_on: Optional[str] = None,
        ends_on: Optional[str] = None,
        instructions: str = "",
        required_assignments: Optional[List[dict]] = None,
    ) -> dict:
        """Build a period and store it as a draft.

        The interview must have produced a profile first: without the shift
        vocabulary there is nothing to build a grid out of, and guessing one
        would be exactly the hardcoding D9 forbids.
        """
        profile = self._buildable_profile(team_id)
        if not starts_on or not ends_on:
            starts_on, ends_on = week_bounds()

        result = self._scheduler.generate(
            profile,
            starts_on,
            ends_on,
            availability=self._repository.availability(
                team_id, starts_on, ends_on
            ),
            history=self._recent_assignments(team_id, starts_on),
            instructions=instructions,
            required_assignments=required_assignments,
            preferences=self._active_preferences(team_id),
        )

        schedule = self._repository.create_schedule(
            team_id, starts_on, ends_on
        )
        slots = self._repository.replace_slots(
            schedule["id"], team_id, result["slots"]
        )
        index = {
            (slot["shift_name"], _iso(slot["slot_date"])): slot["id"]
            for slot in slots
        }
        rows = []
        for item in result["assignments"]:
            slot_id = index.get((item["shift"], item["date"]))
            if slot_id is None:
                continue
            rows.append({
                "slot_id": slot_id,
                "employee": item["employee"],
                "reason": item["reason"],
            })
        self._repository.replace_assignments(schedule["id"], team_id, rows)
        self._repository.append_change(
            team_id, ACTION_GENERATED, schedule_id=schedule["id"],
            reason=instructions,
            agent_reason=result["summary"],
        )

        view = self._view(
            self._repository.get_schedule(schedule["id"], team_id), team_id
        )
        view["notes"] = result["notes"]
        view["summary"] = result["summary"]
        return view

    def start_generation(
        self,
        team_id: str,
        starts_on: Optional[str] = None,
        ends_on: Optional[str] = None,
        instructions: str = "",
        required_assignments: Optional[List[dict]] = None,
    ) -> dict:
        """Open a persistent range job; each later request generates one day."""
        profile = self._buildable_profile(team_id)
        if not starts_on or not ends_on:
            starts_on, ends_on = week_bounds()
        slots = build_slots(profile, starts_on, ends_on)
        if not slots:
            raise AgentError(
                "לא ניתן לבנות סידור: לא הוגדרו משמרות לתקופה הזו"
            )

        schedule = self._repository.create_schedule(
            team_id, starts_on, ends_on
        )
        stored_slots = self._repository.replace_slots(
            schedule["id"], team_id, slots
        )
        required = _generation_required_rows(
            required_assignments or [], stored_slots, profile
        )
        if required:
            self._repository.replace_assignments(
                schedule["id"], team_id, required
            )
        # The mode is read once, here, and stored on the job. A manager who
        # changes the setting while a build is running is choosing how the
        # *next* one runs — re-planning the spans of a job already half
        # checkpointed would strand the days it had finished.
        mode = self._generation_mode()
        spans = plan_spans(profile, starts_on, ends_on, mode)
        dates = sorted({_iso(slot.get("slot_date")) for slot in stored_slots})
        generation = {
            "status": GENERATION_RUNNING,
            "current_date": spans[0]["date"] if spans else "",
            # Counted in dates, never in spans. The progress bar means "days
            # of the period", and a week-wide job whose counter moved by seven
            # at a time would read as a bar that jumps rather than fills.
            "total_days": len(dates),
            "completed_days": 0,
            "failed_days": 0,
            "mode": mode,
            "instructions": _text(instructions)[:2000],
            "required_assignments": required_assignments or [],
            "notes": [],
            "summaries": [],
            # Opened as of now so the browser has something to compare
            # against before the first worker beat lands.
            "heartbeat": _now(),
            "cancel_requested": False,
            "days": [
                {
                    "date": span["date"],
                    "through": span["through"],
                    "dates": span["dates"],
                    "status": "pending",
                    "attempts": 0,
                    "error": "",
                    "metrics": {},
                }
                for span in spans
            ],
        }
        schedule = self._repository.set_generation(
            schedule["id"], team_id, generation
        )
        return self._view(schedule, team_id)

    def start_day_generation(
        self, team_id: str, schedule_id: str, day: str,
        instructions: str = "",
    ) -> dict:
        """Prepare one existing draft day for regeneration.

        Manager-placed rows on that date are pins, not suggestions: the agent
        fills around them. Generated/imported rows are replaced for that day,
        while every other date stays untouched.
        """
        schedule = self._repository.get_schedule(schedule_id, team_id)
        if schedule.get("status") != "draft":
            raise AgentError("יש להחזיר את הסידור לטיוטה לפני שיבוץ יום")
        target = _iso(day)
        if not target or not any(
            _iso(slot.get("slot_date")) == target
            for slot in schedule.get("slots") or []
        ):
            raise AgentError("היום שנבחר אינו קיים בסידור הזה")

        required = [
            {
                "employee": row.get("employee"),
                "shift": row.get("shift"),
                "date": target,
            }
            for row in schedule.get("assignments") or []
            if _iso(row.get("date")) == target
            and row.get("source") == ASSIGNED_BY_MANAGER
        ]
        generation = {
            "status": GENERATION_RUNNING,
            "current_date": target,
            "total_days": 1,
            "completed_days": 0,
            "failed_days": 0,
            "instructions": _text(instructions)[:2000],
            "required_assignments": required,
            "notes": [],
            "summaries": [],
            "heartbeat": _now(),
            "cancel_requested": False,
            # One date, whatever the mode: a manager rebuilding Tuesday asked
            # for Tuesday, and widening that to its week would silently
            # re-answer days they did not select.
            "mode": MODE_DAY,
            "days": [{
                "date": target,
                "through": target,
                "dates": [target],
                "status": "pending",
                "attempts": 0,
                "error": "",
                "metrics": {},
            }],
        }
        return self._view(
            self._repository.set_generation(
                schedule_id, team_id, generation
            ),
            team_id,
        )

    def queue_generation(self, team_id: str, schedule_id: str) -> dict:
        """Start checkpointed generation and return immediately for polling.

        Safe to call repeatedly, and the browser is meant to: it is both the
        first launch and the way a job whose worker went away is picked back
        up. A job this process is already running is left alone and answered
        with its current state; anything else -- failed, cancelled, or
        "running" with nobody on it after a restart -- is relaunched from the
        first day that is not already complete.
        """
        schedule = self._repository.get_schedule(schedule_id, team_id)
        generation = dict(schedule.get("generation") or {})
        if generation.get("status") == GENERATION_COMPLETE:
            return self._view(schedule, team_id)
        if not generation.get("days"):
            raise AgentError("לסידור הזה אין תהליך יצירה שניתן להמשיך")

        key = (team_id, schedule_id)
        should_launch = False
        with self._generation_lock:
            if key not in self._active_generations:
                self._active_generations.add(key)
                should_launch = True
        if not should_launch:
            # Somebody is already on it. Saying so through the stored state
            # rather than starting a second worker is what keeps two browser
            # tabs polling the same job from generating every day twice.
            return self._view(schedule, team_id)

        # Only now that this call owns the job: a resume clears the stop flag
        # and puts the status back to running, so the poller sees movement
        # from the response rather than from the first checkpoint.
        generation.update({
            "status": GENERATION_RUNNING,
            "cancel_requested": False,
            "heartbeat": _now(),
        })
        try:
            schedule = self._repository.set_generation(
                schedule_id, team_id, generation
            )
            self._launch(self._generate_safely, team_id, schedule_id)
        except Exception:
            with self._generation_lock:
                self._active_generations.discard(key)
            raise
        return self._view(schedule, team_id)

    def cancel_generation(self, team_id: str, schedule_id: str) -> dict:
        """Stop waiting on a running job. **Keeps every finished day.**

        The manager's way out of a build that is going nowhere, and the
        reason the browser is allowed to stop polling at all. It is
        cooperative rather than forceful: a model call already in flight is
        not interruptible from here, so this records the decision and the
        worker stops at the next day boundary. What is already checkpointed
        stays -- the period is an ordinary draft the moment this returns, and
        `POST /run` picks the rest up later if the manager wants it.
        """
        schedule = self._repository.get_schedule(schedule_id, team_id)
        generation = dict(schedule.get("generation") or {})
        if not generation.get("days"):
            raise AgentError("לסידור הזה אין תהליך יצירה שניתן לעצור")
        if generation.get("status") == GENERATION_COMPLETE:
            return self._view(schedule, team_id)

        for day in generation.get("days") or []:
            if day.get("status") == GENERATION_RUNNING:
                day["status"] = "pending"
        generation.update({
            "status": GENERATION_CANCELLED,
            "cancel_requested": True,
            "heartbeat": _now(),
        })
        return self._view(
            self._repository.set_generation(
                schedule_id, team_id, generation
            ),
            team_id,
        )

    def generation_progress(self, team_id: str, schedule_id: str) -> dict:
        """Just the progress of a job, for the poll that watches it.

        The browser asks this once a second while a period is being built;
        the full schedule carries every slot, every assignment and a fresh
        audit over both, which is a great deal of arithmetic to repeat for an
        answer that is usually "still on day three". This reads the row and
        returns the counter.
        """
        schedule = self._repository.get_schedule(schedule_id, team_id)
        generation = dict(schedule.get("generation") or {})
        return {
            "id": schedule.get("id"),
            "status": schedule.get("status"),
            "generation": generation,
        }

    def _generate_safely(self, team_id: str, schedule_id: str) -> None:
        """Finish a range behind the short POST that launched it."""
        key = (team_id, schedule_id)
        stop_beating = self._start_heartbeat(team_id, schedule_id)
        try:
            while True:
                try:
                    schedule = self.generate_next(
                        team_id, schedule_id, light=True
                    )
                except Exception as exc:
                    # A span with attempts left goes back in the queue rather
                    # than taking the rest of the period down with it. This
                    # is the whole difference between a dropped connection on
                    # day twelve costing a pause and costing eighteen days
                    # parked behind a button nobody is watching.
                    if not self._requeue_failed_span(
                        team_id, schedule_id, exc
                    ):
                        raise
                    continue
                if (schedule.get("generation") or {}).get("status") in (
                    GENERATION_COMPLETE,
                    GENERATION_FAILED,
                    GENERATION_CANCELLED,
                ):
                    return
        except Exception as exc:
            # `generate_next` checkpoints the failed day before raising. The
            # poller reads that state and offers retry; the severed browser
            # connection is no longer part of the model call.
            _log.exception("schedule generation failed id=%s", schedule_id)
            try:
                schedule = self._repository.get_schedule(schedule_id, team_id)
                generation = dict(schedule.get("generation") or {})
                if generation.get("status") not in (
                    GENERATION_FAILED, GENERATION_CANCELLED,
                ):
                    generation["status"] = GENERATION_FAILED
                    generation["heartbeat"] = _now()
                    generation["failed_days"] = max(
                        1, int(generation.get("failed_days") or 0)
                    )
                    for day in generation.get("days") or []:
                        if day.get("status") == GENERATION_RUNNING:
                            day.update({
                                "status": GENERATION_FAILED,
                                "error": str(exc)[:1000],
                            })
                            break
                    self._repository.set_generation(
                        schedule_id, team_id, generation
                    )
            except Exception:
                _log.exception(
                    "could not persist generation failure id=%s", schedule_id
                )
        finally:
            stop_beating()
            with self._generation_lock:
                self._active_generations.discard(key)

    def _start_heartbeat(self, team_id: str, schedule_id: str):
        """Say "still here" every few seconds. Returns the way to stop.

        A separate thread rather than a stamp at each checkpoint, because the
        thing worth reporting is exactly what a checkpoint cannot report: a
        day held open by a model call that may never return. The beat runs
        beside that call and stops with the job.

        A repository that cannot beat -- an older one, a test double -- is
        not an error. It only means the browser sees a job that never looks
        stale, which is the behaviour that existed before this.
        """
        touch = getattr(self._repository, "touch_generation", None)
        if touch is None:
            return lambda: None

        stop = Event()

        def beat() -> None:
            while not stop.wait(GENERATION_HEARTBEAT_SECONDS):
                try:
                    touch(schedule_id, team_id, _now())
                except Exception:
                    # A missed beat reads as a stalled job and costs one
                    # relaunch, which is recoverable. Killing the generation
                    # over it would not be.
                    _log.warning(
                        "generation heartbeat failed id=%s", schedule_id
                    )

        Thread(target=beat, daemon=True).start()
        return stop.set

    def generate_next(
        self, team_id: str, schedule_id: str, light: bool = False
    ) -> dict:
        """Generate the next pending/failed span and checkpoint the result.

        `light` returns the progress counter instead of the audited period.
        The background loop is the caller that wants it: it reads one field —
        whether the job is still running — and `_view` re-audits every slot
        and assignment in the period to produce it. On a month that was a
        full audit per generated day, thrown away every time. The HTTP route
        still asks for the whole schedule, because its caller renders it.
        """
        schedule = self._repository.get_schedule(schedule_id, team_id)
        generation = dict(schedule.get("generation") or {})
        days = [dict(item) for item in generation.get("days") or []]
        if not days:
            raise AgentError("לסידור הזה אין תהליך יצירה שניתן להמשיך")
        if generation.get("status") == GENERATION_COMPLETE:
            return self._result(schedule, team_id, light)
        # Checked before the span is chosen, not after the model answers: a
        # manager who stopped waiting must not pay for one more call.
        if generation.get("cancel_requested"):
            return self._stop_generation(
                schedule, team_id, generation, days, light
            )

        target = next(
            (
                item for item in days
                if item.get("status") in (
                    GENERATION_FAILED, GENERATION_RUNNING, "pending",
                )
            ),
            None,
        )
        if target is None:
            generation["status"] = GENERATION_COMPLETE
            self._repository.set_generation(schedule_id, team_id, generation)
            return self._result(
                self._repository.get_schedule(schedule_id, team_id),
                team_id, light,
            )

        day = _iso(target.get("date"))
        span_dates = _span_dates(target)
        attempt = int(target.get("attempts") or 0) + 1
        target.update({
            "status": GENERATION_RUNNING,
            "attempts": attempt,
            "error": "",
        })
        generation.update({
            "status": GENERATION_RUNNING,
            "current_date": day,
            "heartbeat": _now(),
        })
        generation["days"] = days
        self._repository.set_generation(schedule_id, team_id, generation)

        profile = self._buildable_profile(team_id)
        # What the manager pinned when the job was opened, plus anything they
        # have placed by hand on these dates since. The board stays writable
        # while a period is being built, so a cell filled in at 10:04 must
        # survive the span that gets generated at 10:05 -- as a pin the agent
        # fills around, exactly as a single-day rebuild treats one.
        required = _merged_required_rows(
            [
                row for row in generation.get("required_assignments") or []
                if _iso(row.get("date")) in span_dates
            ],
            _manager_rows_in(schedule, span_dates),
        )
        through = _iso(target.get("through")) or day
        try:
            # The model assigns; `generate_span` bounds and verifies what it
            # returns (D3). The deterministic engine is the outage path only:
            # a build already half checkpointed must not strand on a model
            # that went away mid-period.
            try:
                result = self._scheduler.generate_span(
                    profile,
                    day,
                    through,
                    availability=self._repository.availability(
                        team_id, day, through
                    ),
                    history=self._recent_assignments(
                        team_id, _iso(schedule.get("starts_on"))
                    ),
                    instructions=generation.get("instructions") or "",
                    required_assignments=required,
                    already_scheduled=[
                        _model_assignment(row)
                        for row in schedule.get("assignments") or []
                    ],
                    preferences=self._active_preferences(team_id),
                )
            except AgentError:
                result = self._assign_span_deterministically(
                    team_id, schedule, profile, day, through,
                    span_dates, required,
                )
            fresh = self._repository.get_schedule(schedule_id, team_id)
            rows = _persisted_generation_rows(
                fresh, result.get("assignments") or [], span_dates
            )
            self._write_span(schedule_id, team_id, span_dates, rows)
            target.update({
                "status": GENERATION_COMPLETE,
                "error": "",
                "metrics": result.get("metrics") or {},
            })
            generation.setdefault("notes", []).extend(result.get("notes") or [])
            summary = _text(result.get("summary"))
            if summary:
                generation.setdefault("summaries", []).append(summary)
        except Exception as exc:
            # Checkpointed as failed and re-raised, exactly as before. One
            # step is one step: the caller of `/next` asked for a date and
            # deserves the error. Deciding to *try again* belongs to the
            # durable loop — see `_requeue_failed_span`.
            target.update({
                "status": GENERATION_FAILED, "error": str(exc)[:1000],
            })
            generation.update({
                "status": GENERATION_FAILED,
                "current_date": day,
                "heartbeat": _now(),
                "completed_days": _completed_dates(days),
                "failed_days": sum(
                    item.get("status") == GENERATION_FAILED for item in days
                ),
                "days": days,
            })
            self._repository.set_generation(schedule_id, team_id, generation)
            raise

        generation.update({
            "heartbeat": _now(),
            "completed_days": _completed_dates(days),
            "failed_days": sum(
                item.get("status") == GENERATION_FAILED for item in days
            ),
            "days": days,
        })
        # A stop asked for while the model was answering. The day that just
        # finished is kept -- it is paid for and correct -- and the job ends
        # here rather than taking the next one.
        if self._cancel_requested(schedule_id, team_id):
            return self._stop_generation(
                self._repository.get_schedule(schedule_id, team_id),
                team_id, generation, days, light,
            )
        remaining = next(
            (
                item for item in days
                if item.get("status") != GENERATION_COMPLETE
            ),
            None,
        )
        if remaining is None:
            generation.update({
                "status": GENERATION_COMPLETE, "current_date": "",
            })
            if not generation.get("logged"):
                self._repository.append_change(
                    team_id,
                    ACTION_GENERATED,
                    schedule_id=schedule_id,
                    reason=generation.get("instructions") or "",
                    agent_reason=_text(" ".join(
                        generation.get("summaries") or []
                    ))[:4000],
                )
                generation["logged"] = True
        else:
            generation.update({
                "status": GENERATION_RUNNING,
                "current_date": _iso(remaining.get("date")),
            })
        schedule = self._repository.set_generation(
            schedule_id, team_id, generation
        )
        view = self._result(schedule, team_id, light)
        view["notes"] = generation.get("notes") or []
        view["summary"] = _text(" ".join(
            generation.get("summaries") or []
        ))[:4000]
        return view

    def _assign_span_deterministically(
        self, team_id: str, schedule: dict, profile: dict, day: str,
        through: str, span_dates, required: List[dict],
    ) -> dict:
        """Fill a span in code when the model is unreachable.

        Not a second opinion on the model's answer -- only what runs when
        there is no answer at all. One pass per date, each seeing the ones
        before it through `already_scheduled`, so rest, hours and fairness
        hold across the span exactly as the model path keeps them.
        """
        _log.warning(
            "schedule span=%s..%s falling back to the deterministic engine",
            day, through,
        )
        availability = self._repository.availability(team_id, day, through)
        history = self._recent_assignments(
            team_id, _iso(schedule.get("starts_on"))
        )
        committed = [
            _model_assignment(row)
            for row in schedule.get("assignments") or []
        ]
        assignments, notes, summaries = [], [], []
        metrics: dict = {}
        for date in sorted(span_dates):
            step = assign_day(
                profile,
                date,
                availability=[
                    row for row in availability
                    if _iso(row.get("date")) == date
                ],
                history=history,
                required_assignments=[
                    row for row in required
                    if _iso(row.get("date")) == date
                ],
                already_scheduled=committed + assignments,
            )
            assignments.extend(step.get("assignments") or [])
            notes.extend(step.get("notes") or [])
            if step.get("summary"):
                summaries.append(step["summary"])
            metrics = step.get("metrics") or metrics
        return {
            "assignments": assignments,
            "notes": notes,
            "summary": _text(" ".join(summaries))[:4000],
            "metrics": metrics,
        }

    def _requeue_failed_span(
        self, team_id: str, schedule_id: str, error: Exception
    ) -> bool:
        """Put a failed span back in the queue. False when it is out of tries.

        Bounded on purpose: the failures that are not transient — a model
        rejecting the schema, a profile with no shifts — repeat identically,
        and retrying those only burns the model server while the manager
        waits for an error that was already decided. A cancelled job is never
        requeued; the manager stopping is not something to recover from.
        """
        try:
            schedule = self._repository.get_schedule(schedule_id, team_id)
        except Exception:
            return False
        generation = dict(schedule.get("generation") or {})
        if generation.get("cancel_requested"):
            return False
        days = [dict(item) for item in generation.get("days") or []]
        target = next(
            (
                item for item in days
                if item.get("status") == GENERATION_FAILED
            ),
            None,
        )
        if target is None:
            return False
        attempts = int(target.get("attempts") or 0)
        if attempts >= _MAX_SPAN_ATTEMPTS:
            return False

        target.update({"status": "pending"})
        generation.update({
            "status": GENERATION_RUNNING,
            "heartbeat": _now(),
            "failed_days": sum(
                item.get("status") == GENERATION_FAILED for item in days
            ),
            "days": days,
        })
        self._repository.set_generation(schedule_id, team_id, generation)
        _log.warning(
            "schedule span %s..%s failed (attempt %d/%d), retrying: %s",
            _iso(target.get("date")),
            _iso(target.get("through")) or _iso(target.get("date")),
            attempts, _MAX_SPAN_ATTEMPTS, error,
        )
        self._pause_before_retry(attempts)
        return True

    def _cancel_requested(self, schedule_id: str, team_id: str) -> bool:
        """Whether a stop was asked for while a day was being generated.

        Re-read rather than remembered: the request arrives on a different
        thread, through the database, after this method took its copy.
        """
        try:
            schedule = self._repository.get_schedule(schedule_id, team_id)
        except Exception:
            return False
        return bool((schedule.get("generation") or {}).get("cancel_requested"))

    def _stop_generation(
        self, schedule: dict, team_id: str, generation: dict,
        days: List[dict], light: bool = False,
    ) -> dict:
        """Park a job the manager stopped, keeping every finished day."""
        for day in days:
            if day.get("status") == GENERATION_RUNNING:
                day["status"] = "pending"
        generation.update({
            "status": GENERATION_CANCELLED,
            "cancel_requested": True,
            "heartbeat": _now(),
            "completed_days": _completed_dates(days),
            "failed_days": sum(
                item.get("status") == GENERATION_FAILED for item in days
            ),
            "days": days,
        })
        return self._result(
            self._repository.set_generation(
                schedule.get("id"), team_id, generation
            ),
            team_id, light,
        )

    def create_blank(
        self,
        team_id: str,
        starts_on: Optional[str] = None,
        ends_on: Optional[str] = None,
    ) -> dict:
        """An empty period the manager fills in themselves (D18).

        The other half of [D6](../../../docs/DECISIONS.md#d6--the-boss-can-author-or-generate) —
        the boss authoring rather than generating. No model is called: which
        dates fall in a period and which shifts run on them is arithmetic,
        and `build_slots` has always been pure Python. The grid arrives
        staffed by nobody and the manager places people into it.

        The profile is still required. Without the shift vocabulary there is
        no grid to build, and inventing one would be exactly the hardcoding
        [D9](../../../docs/DECISIONS.md#d9--shift-vocabulary-is-per-workplace)
        forbids — the manual path skips the agent, not the interview.
        """
        profile = self._buildable_profile(team_id)
        if not starts_on or not ends_on:
            starts_on, ends_on = week_bounds()

        slots = build_slots(profile, starts_on, ends_on)
        if not slots:
            # The vocabulary exists but none of it runs in this window --
            # every shift is restricted to weekdays the period misses. A
            # different failure from an empty vocabulary, and a different
            # sentence: the interview is finished and re-opening it would
            # teach nothing, so this points at the dates instead.
            raise AgentError(
                "לא ניתן לבנות סידור: אף משמרת מוגדרת לא חלה בתאריכים האלה"
            )
        schedule = self._repository.create_schedule(
            team_id, starts_on, ends_on
        )
        self._repository.replace_slots(schedule["id"], team_id, slots)
        self._repository.append_change(
            team_id, ACTION_OPENED, schedule_id=schedule["id"],
            agent_reason="הסידור נפתח ריק לשיבוץ ידני",
        )
        return self._view(
            self._repository.get_schedule(schedule["id"], team_id), team_id
        )

    # -- import (D7) -------------------------------------------------------

    def preview_import(
        self, team_id: str, files: List[dict], learn_rules: bool = True
    ) -> dict:
        """Read uploaded schedule files and say what they contain. Writes nothing.

        This is the whole of [D7](../../../docs/DECISIONS.md#d7--import-infers-layout-boss-confirms)
        on the service side: inference runs, the manager reads an
        interpretation, and **nothing reaches the database until
        `commit_import`**. The absence of a repository write in this method
        is the decision, not an implementation detail.

        `files` is every sheet the manager uploaded at once — a year of them
        is the normal case, not an edge one. Each is inferred separately,
        because they were written at different times and may not share a
        layout, and then read *together* for patterns: a rule about how
        somebody works is only visible across periods.

        One unreadable file does not sink the batch. Its error is reported
        beside the others' results, because a manager uploading a year of
        spreadsheets will have one that is a summary tab or a stray
        document, and refusing everything over it would be useless.
        """
        profile = self._repository.team_profile(team_id) or {}
        if not files:
            raise AgentError("לא נבחרו קבצים לייבוא")

        periods, failures = [], []
        assignments, unavailability = [], []
        for item in files or []:
            name = (item or {}).get("filename") or ""
            try:
                grids = read_grids(
                    (item or {}).get("content") or b"", name
                )
            except AgentError as error:
                failures.append({"filename": name, "error": str(error)})
                continue
            many_sheets = len(grids) > 1
            for sheet_name, grid in grids:
                label = name
                if many_sheets and sheet_name:
                    label = "%s — %s" % (name, sheet_name)
                try:
                    found = infer(grid, profile)
                except AgentError as error:
                    failures.append({"filename": label, "error": str(error)})
                    continue
                periods.append(dict(found.to_dict(), filename=label))
                assignments.extend(found.assignments)
                unavailability.extend(found.unavailability)

        if not periods:
            raise AgentError(
                "לא הצלחתי לקרוא אף אחד מהקבצים. "
                "ודא שהם מכילים טבלת סידור עם תאריכים ושמות משמרות"
            )

        # Counted over every file together. A pattern is by definition
        # something one period cannot show.
        observations = observe(assignments, unavailability, profile)

        rules = {"rules": [], "notes": []}
        if learn_rules:
            try:
                rules = self._learner.propose(observations, profile)
            except AgentError as error:
                # The schedules were read successfully; only the rule
                # suggestions failed. Losing the import over an unavailable
                # model would throw away the expensive half of the work.
                rules = {"rules": [], "notes": [str(error)]}

        return {
            "periods": periods,
            "failures": failures,
            "observations": observations,
            "candidate_rules": rules["rules"],
            "notes": rules["notes"],
        }

    def commit_import(
        self,
        team_id: str,
        assignments: List[dict],
        unavailability: Optional[List[dict]] = None,
        starts_on: Optional[str] = None,
        ends_on: Optional[str] = None,
    ) -> dict:
        """Store an interpretation the manager has approved (D7).

        Takes the rows back from the caller rather than re-reading the file:
        what is stored must be exactly what was shown and approved, and
        re-inferring here would open a gap between the two — the manager
        could correct a name on the confirm screen and have the correction
        silently discarded.

        The slot grid is built from the imported rows, not from
        `build_slots`. A past schedule ran the shifts it actually ran, and
        regenerating the grid from today's vocabulary would quietly reshape
        history to match a profile that may have changed since
        ([D9](../../../docs/DECISIONS.md#d9--shift-vocabulary-is-per-workplace)) —
        which is the same reason `shift_slots` are stored rows rather than
        derived on read.

        Every row lands with `source='imported'`, so the history can always
        say which assignments the product decided and which it merely
        recorded.
        """
        rows = [row for row in (assignments or []) if isinstance(row, dict)]
        if not rows:
            raise AgentError("אין שיבוצים לשמור")

        dates = sorted({
            _iso(row.get("date")) for row in rows if _iso(row.get("date"))
        })
        if not dates:
            raise AgentError("לשיבוצים המיובאים אין תאריכים תקינים")
        starts_on = starts_on or dates[0]
        ends_on = ends_on or dates[-1]

        # The grid the file describes: one slot per (shift, date) actually
        # seen. Deduplicated because several people on one shift is one slot
        # with two assignments, not two slots.
        slots = []
        seen = set()
        for row in rows:
            key = (_text(row.get("shift")), _iso(row.get("date")))
            if not key[0] or not key[1] or key in seen:
                continue
            seen.add(key)
            slots.append({"shift_name": key[0], "slot_date": key[1]})
        if not slots:
            raise AgentError("לא ניתן לבנות את מבנה הסידור מהקובץ")

        schedule = self._repository.create_schedule(
            team_id, starts_on, ends_on
        )
        stored = self._repository.replace_slots(
            schedule["id"], team_id, slots
        )
        index = {
            (slot["shift_name"], _iso(slot["slot_date"])): slot["id"]
            for slot in stored
        }
        placements = []
        for row in rows:
            slot_id = index.get((_text(row.get("shift")), _iso(row.get("date"))))
            employee = _text(row.get("employee"))
            if slot_id is None or not employee:
                continue
            placements.append({
                "slot_id": slot_id,
                "employee": employee,
                "reason": _text(row.get("reason")) or IMPORTED_REASON,
                "source": ASSIGNED_BY_IMPORT,
            })
        self._repository.replace_assignments(
            schedule["id"], team_id, placements
        )

        # Constraints the sheet stated outright travel with the schedule.
        # `source='employee_reported'` would be a lie -- nobody submitted
        # these -- so they are the manager's, which is what a sheet they
        # maintained actually makes them.
        recorded = 0
        for row in unavailability or []:
            if not isinstance(row, dict):
                continue
            employee = _text(row.get("employee"))
            date = _iso(row.get("date"))
            if not employee or not date:
                continue
            self._repository.set_availability(
                team_id, employee, date,
                shift_name=_text(row.get("shift")),
                available=False,
                reason=_text(row.get("reason")),
                source=SOURCE_MANAGER,
            )
            recorded += 1

        self._repository.append_change(
            team_id, ACTION_IMPORTED, schedule_id=schedule["id"],
            agent_reason=(
                "יובאו %d שיבוצים ו-%d אילוצים מקובץ קיים"
                % (len(placements), recorded)
            ),
        )
        return self._view(
            self._repository.get_schedule(schedule["id"], team_id), team_id
        )

    def assign(
        self,
        team_id: str,
        shift_name: str,
        slot_date: str,
        employee: str,
        reason: str = "",
        schedule_id: Optional[str] = None,
    ) -> dict:
        """Place one person on one slot, by hand. No model call (D18).

        This writes immediately rather than proposing. It is not a reversal
        of [D12](../../../docs/DECISIONS.md#d12--dragging-a-shift-is-a-proposal-not-an-edit):
        a drag *moves someone who is already placed*, which changes a
        person's week and is what the confirmation exists to account for.
        Filling an empty cell takes nothing away from anybody — it is
        authoring, and asking for a justification of every cell would make
        building a week by hand cost twenty dialogs.

        `reason` is the manager's own sentence when they gave one. When they
        did not, the row still carries a true statement of where it came
        from rather than a judgment the agent never made — the same honesty
        `move()` applies to a dragged shift.
        """
        employee = (employee or "").strip()
        if not employee:
            raise AgentError("צריך לבחור עובד לשיבוץ")
        schedule = self._require_schedule(team_id, schedule_id)
        slot = self._repository.find_slot(
            schedule["id"], team_id, shift_name, slot_date
        )
        if slot is None:
            raise NotFoundError("המשמרת לא נמצאה בסידור")

        stated = (reason or "").strip()
        row = self._repository.add_assignment(
            schedule["id"], team_id, slot["id"], employee,
            stated or MANUAL_REASON,
            source=ASSIGNED_BY_MANAGER,
        )
        self._repository.append_change(
            team_id, ACTION_ASSIGNED, schedule_id=schedule["id"],
            employee=employee, slot_date=slot_date, shift_name=shift_name,
            reason=stated,
            agent_reason=MANUAL_REASON,
        )
        view = self._view(
            self._repository.get_schedule(schedule["id"], team_id), team_id
        )
        # `add_assignment` conflicts silently on (slot, employee), so a
        # double click returns the row that was already there. Saying so
        # lets the UI stay quiet instead of reporting a change it did not
        # make.
        view["assigned"] = (row or {}).get("id", "")
        return view

    def unassign(
        self,
        team_id: str,
        assignment_id: str,
        reason: str = "",
        schedule_id: Optional[str] = None,
    ) -> dict:
        """Take one person off a slot, by hand (D18).

        Removing somebody *does* take a shift away from a person, so unlike
        `assign` this is a change in the sense D8 means. The manager's reason
        is asked for by the UI and recorded when given; it is not enforced
        here, because a cell cleared seconds after being filled by mistake is
        a correction rather than a decision, and refusing it would strand the
        manual path halfway through.
        """
        schedule = self._require_schedule(team_id, schedule_id)
        existing = _find_assignment(schedule, assignment_id)
        if existing is None:
            raise NotFoundError("השיבוץ לא נמצא")
        self._repository.remove_assignment(assignment_id, team_id)
        self._repository.append_change(
            team_id, ACTION_REMOVED, schedule_id=schedule["id"],
            employee=existing.get("employee") or "",
            slot_date=_iso(existing.get("date")),
            shift_name=existing.get("shift") or "",
            reason=(reason or "").strip(),
            agent_reason=MANUAL_REASON,
        )
        return self._view(
            self._repository.get_schedule(schedule["id"], team_id), team_id
        )

    def publish(self, schedule_id: str, team_id: str) -> dict:
        """Make a draft the team's. Members read only published periods."""
        schedule = self._repository.set_schedule_status(
            schedule_id, team_id, "published"
        )
        self._repository.append_change(
            team_id, ACTION_PUBLISHED, schedule_id=schedule_id,
            agent_reason="הסידור פורסם לצוות",
        )
        return self._view(schedule, team_id)

    def unpublish(self, schedule_id: str, team_id: str) -> dict:
        return self._view(
            self._repository.set_schedule_status(
                schedule_id, team_id, "draft"
            ),
            team_id,
        )

    def delete(self, schedule_id: str, team_id: str) -> None:
        self._repository.delete_schedule(schedule_id, team_id)

    def clear(
        self,
        team_id: str,
        schedule_id: str,
        slot_date: str = "",
        reason: str = "",
    ) -> dict:
        """Empty a day's shifts, or the whole period's. Keeps the grid.

        The counterpart to building a week: a manager who does not like what
        came out needs to be able to take it back without deleting the period
        and rebuilding its slots. `slot_date` narrows it to one day; empty
        clears every assignment in the period.

        **The slots stay.** They are the shape of the week — which shifts run
        on which dates — and they come from the vocabulary rather than from
        any decision made here. Clearing them too would leave a period that
        renders as no shifts at all rather than as unstaffed ones, which is
        the same conflation `bl/export.py` documents between an empty cell
        and `UNFILLED`.

        Every removed row is logged individually, exactly as `unassign` logs
        one. A day cleared in one gesture is still N people taken off N
        shifts, and the log is the only history there is
        ([D4](../../../docs/DECISIONS.md#d4--living-schedule-not-versioned)):
        collapsing it into a single "the day was cleared" entry would lose
        which shifts those were, on the day somebody asks.

        No model call, like every other manual write (D18).
        """
        schedule = self._require_schedule(team_id, schedule_id)
        wanted = _iso(slot_date)
        rows = [
            row for row in schedule.get("assignments") or []
            if not wanted or _iso(row.get("date")) == wanted
        ]
        stated = (reason or "").strip()
        for row in rows:
            self._repository.remove_assignment(row["id"], team_id)
            self._repository.append_change(
                team_id, ACTION_REMOVED, schedule_id=schedule["id"],
                employee=row.get("employee") or "",
                slot_date=_iso(row.get("date")),
                shift_name=row.get("shift") or "",
                reason=stated,
                agent_reason=(
                    "נמחק בניקוי היום על ידי המנהל" if wanted
                    else "נמחק בניקוי הסידור על ידי המנהל"
                ),
            )
        view = self._view(
            self._repository.get_schedule(schedule["id"], team_id), team_id
        )
        # How many rows actually went. A day that was already empty is not a
        # failure -- the manager asked for it to be empty and it is -- but
        # the UI should be able to say "nothing to clear" rather than report
        # a change it did not make, the same way `assign` echoes `assigned`.
        view["cleared"] = len(rows)
        return view

    # -- changing ----------------------------------------------------------

    def propose(
        self,
        team_id: str,
        request: str,
        schedule_id: Optional[str] = None,
        stated_reason: str = "",
        pending_request: str = "",
    ) -> dict:
        """What the agent would do about a request. Writes nothing.

        The manager confirms this before it lands. Returned with the warnings
        the change *would* produce, so a proposal that breaks something is
        visible before it is accepted rather than after.
        """
        schedule = self._repository.get_schedule(schedule_id, team_id) \
            if schedule_id else self._repository.current_schedule(team_id)
        schedule = schedule or {}
        profile = self._repository.team_profile(team_id) or {}
        window = _window(schedule)
        proposal = self._changes.propose(
            profile,
            schedule,
            request,
            stated_reason=stated_reason,
            availability=self._repository.availability(
                team_id, window[0], window[1]
            ),
            history=self._repository.change_log(team_id, limit=40),
            pending_request=pending_request,
        )
        proposal["schedule_id"] = schedule.get("id", "")
        # The audit runs against the schedule as the proposal would leave it,
        # so the manager sees the consequence rather than the current state.
        proposal["warnings"] = self._audit_rows(
            team_id,
            _applied(schedule, proposal["operations"]),
            schedule,
        ) if schedule else []
        return proposal

    def apply(
        self,
        team_id: str,
        schedule_id: str,
        operations: List[dict],
        reason: str,
        agent_reason: str = "",
        profile_operations: Optional[List[dict]] = None,
    ) -> dict:
        """Apply a proposal the manager confirmed, and log it.

        The manager's reason is required here rather than merely requested:
        by this point they have been asked, and a change landing in the
        append-only log without one is a hole in the only history there is
        ([D8](../../../docs/DECISIONS.md#d8--two-reasons-both-required)).
        """
        profile_operations = profile_operations or []
        if operations and not (reason or "").strip():
            raise AgentError("צריך לציין סיבה לשינוי")
        if operations and profile_operations:
            raise AgentError("יש לאשר שינויי צוות ושינויי סידור בנפרד")
        if profile_operations:
            profile = self._profiles.apply_operations(
                team_id, profile_operations
            )
            schedule = self._repository.current_schedule(team_id)
            if schedule:
                return self._view(schedule, team_id)
            return {"status": "ok", "profile": profile}
        schedule = self._repository.get_schedule(schedule_id, team_id)
        applied = 0
        for operation in operations or []:
            applied += self._apply_one(
                team_id, schedule, operation, reason, agent_reason
            )
        if not applied:
            # Which operation found nothing, rather than only that nothing
            # happened. "לא היה שינוי להחיל" in front of a proposal the
            # manager just read and approved reads as the product refusing
            # them; naming the row that was not there is the difference
            # between a dead end and something they can correct.
            raise AgentError(_nothing_applied(operations or []))
        return self._view(
            self._repository.get_schedule(schedule_id, team_id), team_id
        )

    def move(
        self,
        team_id: str,
        assignment_id: str,
        shift_name: str,
        slot_date: str,
        reason: str,
        agent_reason: str = "",
        schedule_id: Optional[str] = None,
    ) -> dict:
        """Move one assignment — what a confirmed drag resolves to.

        The gesture happens on the calendar, but it arrives here only after
        the manager has supplied a reason in the confirmation dialog, so a
        dragged shift carries exactly what a spoken one does: their reason
        and the agent's ([D8](../../../docs/DECISIONS.md#d8--two-reasons-both-required)).
        Dragging is a way of *proposing* a change, not a way around the
        decision that changes are explained.

        `schedule_id` is the period the drag happened on. It used to be
        hardcoded to `None` here, which resolved to whichever period covers
        today: a drag on any other week then looked for its target slot in
        the wrong period and came back "המשמרת לא נמצאה בסידור", while the
        placement check beside it — the one call that always passed the id —
        had just said the move was fine.
        """
        if not (reason or "").strip():
            raise AgentError("צריך לציין סיבה להעברת המשמרת")
        schedule = self._require_schedule(team_id, schedule_id)
        slot = self._repository.find_slot(
            schedule["id"], team_id, shift_name, slot_date
        )
        if slot is None:
            raise NotFoundError("המשמרת לא נמצאה בסידור")
        previous = _find_assignment(schedule, assignment_id)
        moved = self._repository.move_assignment(
            assignment_id, team_id, slot["id"],
            reason=agent_reason or reason,
        )
        self._repository.append_change(
            team_id, ACTION_MOVED, schedule_id=schedule["id"],
            employee=moved["employee"],
            slot_date=slot_date, shift_name=shift_name,
            reason=reason,
            agent_reason=agent_reason or _moved_from(previous),
        )
        return self._view(
            self._repository.get_schedule(schedule["id"], team_id), team_id
        )

    def _apply_one(
        self,
        team_id: str,
        schedule: dict,
        operation: dict,
        reason: str,
        agent_reason: str,
    ) -> int:
        """One operation against the stored schedule. Returns rows changed."""
        action = (operation or {}).get("action")
        employee = (operation.get("employee") or "").strip()
        shift = (operation.get("shift") or "").strip()
        date = _iso(operation.get("date"))
        if not action or not employee or not date:
            return 0
        own_reason = (operation.get("reason") or "").strip() or agent_reason

        if action == OP_REMOVE:
            existing = _match(schedule, employee, shift, date)
            if existing is None:
                return 0
            self._repository.remove_assignment(existing["id"], team_id)
            self._repository.append_change(
                team_id, ACTION_REMOVED, schedule_id=schedule["id"],
                employee=employee, slot_date=date, shift_name=shift,
                reason=reason, agent_reason=own_reason,
            )
            return 1

        if action == OP_ASSIGN:
            slot = self._repository.find_slot(
                schedule["id"], team_id, shift, date
            )
            if slot is None:
                return 0
            self._repository.add_assignment(
                schedule["id"], team_id, slot["id"], employee,
                own_reason or reason,
            )
            self._repository.append_change(
                team_id, ACTION_ASSIGNED, schedule_id=schedule["id"],
                employee=employee, slot_date=date, shift_name=shift,
                reason=reason, agent_reason=own_reason,
            )
            return 1

        if action == OP_SWAP:
            other = (operation.get("with_employee") or "").strip()
            other_shift = (operation.get("with_shift") or "").strip() or shift
            other_date = _iso(operation.get("with_date")) or date
            first = _match(schedule, employee, shift, date)
            second = _match(schedule, other, other_shift, other_date)
            if first is None or second is None:
                return 0
            self._repository.move_assignment(
                first["id"], team_id, second["slot_id"],
                reason=own_reason or reason,
            )
            self._repository.move_assignment(
                second["id"], team_id, first["slot_id"],
                reason=own_reason or reason,
            )
            self._repository.append_change(
                team_id, ACTION_SWAPPED, schedule_id=schedule["id"],
                employee=employee, replaced_employee=other,
                slot_date=date, shift_name=shift,
                reason=reason, agent_reason=own_reason,
            )
            return 1

        return 0

    # -- constraints -------------------------------------------------------

    def set_constraint(
        self,
        team_id: str,
        employee: str,
        constraint_date: str,
        shift_name: str = "",
        available: bool = False,
        start_time: str = "",
        end_time: str = "",
        is_hard: bool = True,
        reason: str = "",
        source: str = SOURCE_MANAGER,
    ) -> dict:
        """Record a constraint for an employee.

        Written by the manager or by the agent during a conversation, never
        by the employee — they have no account at all
        ([D10](../../../docs/DECISIONS.md#d10--one-workspace-per-team-the-boss-holds-a-password-members-hold-a-link)),
        so `source` records where the information came from rather than who
        typed it. `employee_reported` is the manager writing down what
        someone told them.
        """
        if not (employee or "").strip():
            raise AgentError("צריך לציין עובד")
        if not (constraint_date or "").strip():
            raise AgentError("צריך לציין תאריך")
        start_time = _constraint_time(start_time)
        end_time = _constraint_time(end_time)
        row = self._repository.set_availability(
            team_id, employee.strip(), constraint_date,
            shift_name=(shift_name or "").strip(),
            available=available, start_time=start_time, end_time=end_time,
            is_hard=is_hard, reason=(reason or "").strip(), source=source,
        )
        self._repository.append_change(
            team_id, ACTION_CONSTRAINT,
            employee=employee.strip(), slot_date=constraint_date,
            shift_name=(shift_name or "").strip(),
            reason=(reason or "").strip(),
            agent_reason=(
                "העדפת זמינות נרשמה" if not is_hard
                else "זמין" if available else "אילוץ נרשם"
            ),
        )
        return row

    def constraints(
        self,
        team_id: str,
        starts_on: Optional[str] = None,
        ends_on: Optional[str] = None,
        employee: Optional[str] = None,
    ) -> List[dict]:
        return self._repository.availability(
            team_id, starts_on, ends_on, employee
        )

    def delete_constraint(self, row_id: str, team_id: str) -> None:
        self._repository.delete_availability(row_id, team_id)

    def history(
        self, team_id: str, schedule_id: Optional[str] = None
    ) -> List[dict]:
        return self._repository.change_log(team_id, schedule_id)

    def learn_from_changes(self, team_id: str) -> dict:
        """Candidate rules from what the manager kept correcting by hand.

        The other end of `preview_import`'s learning: that one reads what the
        workplace *did* out of old files, this one reads what the manager
        **decided** out of the change log. Every row it counts is a moment
        somebody overrode the schedule and stated why, which
        [D8](../../../docs/DECISIONS.md#d8--two-reasons-both-required)
        guaranteed would be there.

        Counting first, and returning early when nothing repeats: the tally
        is arithmetic (D3) and the common case — a workspace whose manager
        has corrected a handful of things once each — is answerable without a
        model call at all.

        **Nothing is stored.** Like every other learned candidate, these are
        proposals the manager approves one at a time
        ([D7](../../../docs/DECISIONS.md#d7--import-infers-layout-boss-confirms)),
        and this method is handed no path to the rules on the profile.

        A model failure degrades to the counts alone rather than raising: the
        panel this feeds sits beside the calendar, and losing the screen over
        an unavailable model would be the wrong trade — the same reasoning
        `preview_import` applies to its own learning step.
        """
        profile = self._repository.team_profile(team_id) or {}
        corrections = observe_corrections(
            self._repository.change_log(team_id, limit=_LEARN_HISTORY)
        )
        if not corrections["repeated"]:
            return {
                "corrections": corrections,
                "candidate_rules": [],
                "notes": [],
                "remembered": [],
            }
        try:
            proposed = self._learner.propose_from_corrections(
                corrections, profile
            )
        except AgentError as error:
            proposed = {"rules": [], "notes": [str(error)]}
        return {
            "corrections": corrections,
            "candidate_rules": proposed["rules"],
            "notes": proposed["notes"],
            # What was written down as a suggestion, so the caller can say
            # "the agent noticed something" without re-reading the table.
            "remembered": self._remember_patterns(
                team_id, corrections, proposed["rules"]
            ),
        }

    def observe_quietly(self, team_id: str) -> List[dict]:
        """Count the corrections and record what repeats. No model call.

        The background half of `learn_from_changes`: the manager never asks
        for this and never waits on it. It runs off the back of an ordinary
        read, counts the change log, and writes anything that has repeated
        as a `suggested` preference.

        **No model is called here on purpose.** Wording a candidate rule is
        a model's job and that is what `learn_from_changes` is for, but the
        *pattern* is arithmetic (D3) and arithmetic is what may run
        unattended. A background path that called a model would put a
        latency and a failure mode behind a screen nobody asked to wait for,
        and would put the model's sentences into the table without anybody
        having read them.

        Everything it writes is inert and visible: `suggested` rows are not
        read by `ask()` and the manager approves, rewords or deletes each one
        ([D21](../../../docs/DECISIONS.md#d21--the-agent-remembers-preferences-and-every-one-of-them-is-visible)).
        Learning in the background changes when the agent notices, never what
        noticing is allowed to do.

        Never raises. It is a side effect of a screen that must render
        regardless, exactly as `brief()` is.
        """
        try:
            corrections = observe_corrections(
                self._repository.change_log(team_id, limit=_LEARN_HISTORY)
            )
            return self._remember_patterns(team_id, corrections, [])
        except Exception:
            return []

    def _remember_patterns(
        self, team_id: str, corrections: dict, rules: List[dict]
    ) -> List[dict]:
        """Write repeated corrections down as suggestions, once each.

        The gap this closes: `observe_corrections` has always counted what
        the manager keeps fixing, and `agent_preferences` has always been
        able to hold a `suggested` row, but nothing joined them -- the agent
        noticed patterns and then forgot them the moment the response was
        rendered.

        **Deduplicated on the pattern, not on the wording.** The key is the
        same triple the tally is keyed on -- this person, this shift, this
        weekday -- because the same pattern observed again is the same
        observation, and a second row for it would be the agent nagging. A
        pattern the manager already archived stays archived for the same
        reason: `preferences()` with no status filter returns every state,
        and a dismissed suggestion that came back would be a decision
        overruled by a cron.

        The `evidence` is the count and the manager's own stated reasons,
        never a paraphrase. It is what makes the suggestion checkable at a
        glance, which is the whole of why D21 requires one.
        """
        repeated = (corrections or {}).get("repeated") or []
        if not repeated:
            return []

        # Every state, so an archived suggestion is not proposed again.
        seen = {
            _text(row.get("subject"))
            for row in self._repository.preferences(team_id)
            if _text(row.get("source")) == SOURCE_AGENT
        }
        # The model's wording where there is one for this pattern, the
        # counted sentence otherwise. Either way the manager reads it and
        # decides -- the sentence is a proposal, not a rule.
        worded = _worded_by_subject(rules, repeated)

        remembered = []
        for entry in repeated:
            subject = _pattern_key(entry)
            if not subject or subject in seen:
                continue
            seen.add(subject)
            remembered.append(self._repository.create_preference(
                team_id,
                text=worded.get(subject) or _pattern_sentence(entry),
                kind=PREFERENCE_EMPLOYEE if entry.get("employee")
                else PREFERENCE_GENERAL,
                subject=subject,
                evidence=_pattern_evidence(entry),
                status=PREFERENCE_SUGGESTED,
                source=SOURCE_AGENT,
            ))
        return remembered

    # -- answering ---------------------------------------------------------

    def ask(
        self,
        team_id: str,
        request: str,
        schedule_id: Optional[str] = None,
        pending_request: str = "",
    ) -> dict:
        """Answer a question about the schedule by running read-only tools.

        The multi-step half of the agent: *"מי יכול להחליף את יוסי בסופ״ש"*
        needs several countable things worked out in order, and
        `bl/planner.py` runs them through `bl/tools.py` rather than asking a
        model to do arithmetic over a wall of JSON (D3).

        **Nothing here writes.** The planner holds the tools, not the
        repository, and its response schema contains no operation — there is
        nothing an `apply()` could read out of an answer. A question that
        turns out to want a change is answered with what the agent *would*
        propose, and the manager sends it through `propose()` and confirms
        it with their reason, exactly as before
        ([D8](../../../docs/DECISIONS.md#d8--two-reasons-both-required)).

        **It works with no model configured.** The planner falls back to
        `bl/intent.py` and the same tools, which is what makes this feature
        part of the product rather than a feature of the deployment
        (`README.md`).
        """
        schedule = self._repository.get_schedule(schedule_id, team_id) \
            if schedule_id else self._repository.current_schedule(team_id)
        answer = self._planner.answer(
            team_id,
            request,
            profile=self._repository.team_profile(team_id) or {},
            period=schedule,
            preferences=self._repository.preferences(
                team_id, status=PREFERENCE_ACTIVE
            ) if hasattr(self._repository, "preferences") else [],
            pending_request=pending_request,
        )
        answer["schedule_id"] = _text((schedule or {}).get("id"))
        return answer

    def run_tool(
        self, team_id: str, name: str, arguments: Optional[dict] = None
    ) -> dict:
        """One named tool, run directly. Reads only.

        Exposed so the board can ask the same questions the agent asks —
        "who could take this slot" is a useful button whether or not anybody
        is having a conversation, and routing it through the same tool is
        what keeps the button and the agent from ever giving different
        answers.
        """
        return self._tools.run(team_id, name, arguments)

    # -- simulating --------------------------------------------------------

    def simulate(
        self,
        team_id: str,
        operations: List[dict],
        schedule_id: Optional[str] = None,
    ) -> dict:
        """What a set of changes would do. **Persists nothing.**

        The safe way to ask *"מה יקרה אם אעביר את דנה לחמישי בערב"*. It is
        deliberately not `propose()`: a proposal is an answer with a confirm
        button attached, and a manager thinking out loud has not asked for
        one. This returns an impact report — what would break, what would
        clear, how coverage and hours would move, and who is touched.

        `bl/simulate.py` is handed no repository at all, so "the simulation
        did not persist" is a property of the wiring rather than a rule
        somebody has to remember — the same shape `bl/changes.py` and
        `bl/importer.py` have.

        Approving a simulation is an ordinary `apply()` with the manager's
        reason. There is no shortcut from here to a write, and adding one
        would make simulation the way around the confirmation step (D8/D12).
        """
        schedule = self._require_schedule(team_id, schedule_id)
        profile = self._repository.team_profile(team_id) or {}
        window = _window(schedule)
        result = simulate_operations(
            schedule,
            profile,
            operations or [],
            availability=[
                {
                    "employee": row.get("employee"),
                    "date": _iso(row.get("constraint_date")),
                    "shift": row.get("shift_name") or "",
                    "available": row.get("available"),
                    "start_time": row.get("start_time") or "",
                    "end_time": row.get("end_time") or "",
                    "is_hard": row.get("is_hard", True),
                    "reason": row.get("reason") or "",
                }
                for row in self._repository.availability(
                    team_id, window[0], window[1]
                )
            ],
        )
        result["schedule_id"] = schedule["id"]
        return result

    # -- preferences -------------------------------------------------------

    def preferences(
        self, team_id: str, status: Optional[str] = None
    ) -> List[dict]:
        """What this workplace has taught the agent, beyond one-off decisions."""
        return self._repository.preferences(team_id, status=status)

    def add_preference(
        self,
        team_id: str,
        text: str,
        kind: str = PREFERENCE_GENERAL,
        subject: str = "",
        evidence: str = "",
        suggested: bool = False,
        source: str = SOURCE_MANAGER,
    ) -> dict:
        """Remember an operational preference for this team.

        `suggested` is what separates the agent noticing something from the
        manager deciding it. A suggested row is inert: `ask()` reads only
        `active` ones, so a proposal changes nothing until it is approved.
        One decision is a decision — it becomes a standing preference when
        the manager says it is one, which is the same line
        [D14](../../../docs/DECISIONS.md#d14--employees-get-real-identities-and-may-submit-constraints-️-reverses-d5-amends-d10)
        draws between a request and a constraint.
        """
        if not (text or "").strip():
            raise AgentError("צריך לכתוב את ההעדפה")
        return self._repository.create_preference(
            team_id,
            text=text,
            kind=kind,
            subject=subject,
            evidence=evidence,
            status=PREFERENCE_SUGGESTED if suggested else PREFERENCE_ACTIVE,
            source=source,
        )

    def update_preference(
        self,
        team_id: str,
        row_id: str,
        text: Optional[str] = None,
        status: Optional[str] = None,
    ) -> dict:
        """Reword a preference, approve a suggested one, or archive it.

        Editable because a stored preference the manager cannot change is a
        rule they never agreed to. Approving is this call with
        `status='active'`, which is why approval needs no separate method.
        """
        return self._repository.update_preference(
            row_id, team_id, text=text, status=status
        )

    def delete_preference(self, team_id: str, row_id: str) -> None:
        self._repository.delete_preference(row_id, team_id)

    # -- leaving the app ---------------------------------------------------

    def workbook(
        self, team_id: str, schedule_id: Optional[str] = None
    ) -> tuple:
        """One period as `.xlsx`, plus the filename to serve it under.

        Exported in the layout `FILE_FORMATS.md` calls Sample A, which is the
        shape the importer is being built to read — so a week can leave, be
        edited in Excel, and come back
        ([D17](../../../docs/DECISIONS.md#d17--a-schedule-leaves-as-a-file-a-message-is-something-the-agent-writes)).

        The unaudited stored schedule is passed deliberately: an export is a
        picture of what was decided, and warnings are advice to the manager
        about it, not part of the roster people read.
        """
        schedule = self._require_schedule(team_id, schedule_id)
        profile = self._repository.team_profile(team_id) or {}
        workplace = profile.get("workplace")
        title = ""
        if isinstance(workplace, dict) and isinstance(
            workplace.get("name"), str
        ):
            title = workplace["name"].strip()
        return as_workbook(schedule, title=title), filename(schedule, "xlsx")

    # -- speaking first ----------------------------------------------------

    def brief(
        self, team_id: str, trigger: str = TRIGGER_OPENED,
        last_said: Optional[List[str]] = None,
    ) -> dict:
        """What the agent has to say, unprompted. Writes nothing.

        The one call in this service the manager did not ask for. It gathers
        the same state the management screen already shows -- the period, the
        audit's warnings, the fairness totals, the pending requests -- and
        lets the agent say what it makes of them
        ([D15](../../../docs/DECISIONS.md#d15--the-agent-speaks-first-but-still-never-writes)).

        The warnings and the fairness totals are computed here, by
        `audit.py`, and handed over as facts. The model is never asked to
        count anything: that division is the whole of
        [D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)
        and speaking first does not change which side of it does arithmetic.

        A failure is not raised. This is decoration on a screen that must
        render regardless, so a model that is down or slow costs the manager
        their briefing, never their calendar.
        """
        profile = self._repository.team_profile(team_id) or {}
        if not profile:
            # Nothing to brief on before the interview: the agent knows
            # neither the shifts nor the people, and a briefing built on that
            # would be invented rather than observed.
            return _quiet()

        # Learning happens off the back of the agent's own unprompted read,
        # which is the only moment in the product that is already not the
        # manager waiting on something. Counted, never modelled, and every
        # row it writes is `suggested` and inert -- see `observe_quietly`.
        # Before the briefing rather than after, so a pattern noticed now is
        # in the table the briefing is about to describe.
        self.observe_quietly(team_id)

        schedule = self.current(team_id)
        window = _window(schedule)
        warnings = (schedule or {}).get("warnings") or []
        # Publishing state and the unstaffed slots, counted by the same
        # read-only tools the answering path uses (D19). Read here rather
        # than left for the model to ask about: a briefing gets one call and
        # no tool loop, so anything it is to reason about has to be in front
        # of it. Both are arithmetic, so this moves no part of the D3 line.
        readiness, gaps = self._publishing_state(team_id, schedule)
        try:
            return self._briefing.brief(
                trigger,
                profile,
                schedule=schedule,
                warnings=warnings,
                fairness=fairness(
                    [
                        {
                            "employee": row.get("employee"),
                            "shift": row.get("shift"),
                            "date": _iso(row.get("date")),
                        }
                        for row in (schedule or {}).get("assignments") or []
                    ],
                    _shifts(profile),
                    _employees(profile),
                ),
                requests=self._repository.list_requests(
                    team_id, status="pending"
                ),
                availability=self._repository.availability(
                    team_id, window[0], window[1]
                ),
                changes=self._repository.change_log(team_id, limit=40),
                last_said=last_said,
                readiness=readiness,
                gaps=gaps,
            )
        except Exception:
            return _quiet()

    def _publishing_state(
        self, team_id: str, schedule: Optional[dict]
    ) -> tuple:
        """What publishing is waiting on, and which slots are short.

        Both come from `bl/tools.py`, which is the same arithmetic the
        manager gets when they ask outright -- so the briefing and the answer
        to *"מה חסר לפני פרסום"* can never disagree. Reusing the tool is the
        point; a second implementation of "what is missing" is how two
        screens start telling the manager different things.

        Returns empties rather than raising when there is no period: the
        briefing is decoration on a screen that must render, and a workspace
        before its first schedule is the most ordinary case there is.
        """
        if not schedule:
            return {}, []
        schedule_id = _text(schedule.get("id"))
        try:
            readiness = self._tools.publish_readiness(
                team_id, schedule_id=schedule_id
            )
            return readiness, readiness.get("gaps") or []
        except Exception:
            return {}, []

    # -- helpers -----------------------------------------------------------

    def _result(self, schedule: dict, team_id: str, light: bool) -> dict:
        """The audited period, or just its progress. See `generate_next`."""
        if not light:
            return self._view(schedule, team_id)
        return {
            "id": schedule.get("id"),
            "status": schedule.get("status"),
            "generation": dict(schedule.get("generation") or {}),
        }

    def _write_span(
        self, schedule_id: str, team_id: str, dates: List[str],
        rows: List[dict],
    ) -> None:
        """Persist one span's checkpoint, touching only that span's dates.

        Falls back to rewriting the period on a repository that predates
        `replace_span_assignments` — an older deployment, a test double —
        because a checkpoint that raises loses the model answer it was
        holding, which is the one outcome worse than writing too much.
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

    def _generation_mode(self) -> str:
        """How wide one model call is for the next build the manager opens.

        Read live from the settings store, so a mode saved in the panel
        applies to the next period without a restart — the same property the
        model settings have. No store (a test double, an older composition
        root) reads as the default: a missing setting is not a reason to run
        at a width nobody chose.
        """
        settings = getattr(self._settings, "get", None)
        if settings is None:
            return MODE_DAY
        mode = getattr(settings(), "schedule_generation_mode", MODE_DAY)
        return mode if mode in (MODE_DAY, MODE_WEEK) else MODE_DAY

    def _pause_before_retry(self, attempt: int) -> None:
        """Back off before re-asking. See `_RETRY_BASE_SECONDS`."""
        self._sleep(min(
            _RETRY_BASE_SECONDS * (2 ** max(0, attempt - 1)),
            _RETRY_MAX_SECONDS,
        ))

    def _view(self, schedule: dict, team_id: str) -> dict:
        """A schedule with its warnings attached.

        Warnings ride along on every response carrying a schedule, and a
        response with warnings is still a success — they are advisory
        ([D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).
        """
        schedule = dict(schedule)
        schedule["warnings"] = self._audit_rows(
            team_id, schedule.get("assignments") or [], schedule
        )
        schedule["closures"] = self._closures(team_id, schedule)
        return _dated(schedule)

    def _closures(self, team_id: str, schedule: dict) -> List[dict]:
        """Which of this period's dates belong to a closure, and to whom.

        Rides along with the schedule for the same reason the warnings do:
        the board has to render the week either way, and whose weekend a
        Thursday is cannot be worked out from the grid. It is read-only
        arithmetic from `bl/rotation.py` — there is no field here anything
        could act on, so a closure shown on a column stays a description of
        the cycle rather than a second way to change it.
        """
        window = _window(schedule)
        try:
            start = datetime.date.fromisoformat(_iso(window[0]))
            end = datetime.date.fromisoformat(_iso(window[1]))
        except (TypeError, ValueError):
            return []
        profile = self._repository.team_profile(team_id) or {}
        days = rotation.by_date(profile, start, end)
        return [days[date] for date in sorted(days)]

    def _active_preferences(self, team_id: str) -> List[dict]:
        """Confirmed standing context for every scheduling model call."""
        if not hasattr(self._repository, "preferences"):
            return []
        return self._repository.preferences(team_id, status=PREFERENCE_ACTIVE)

    def _audit_rows(
        self, team_id: str, assignments: List[dict], schedule: dict
    ) -> List[dict]:
        profile = self._repository.team_profile(team_id) or {}
        window = _window(schedule)
        return audit(
            [
                {
                    "employee": row.get("employee"),
                    "shift": row.get("shift"),
                    "date": _iso(row.get("date")),
                }
                for row in assignments
            ],
            _shifts(profile),
            _employees(profile),
            availability=effective_availability(
                profile,
                self._repository.availability(team_id, window[0], window[1]),
                window[0], window[1],
            ),
            profile=profile,
            # The grid, so a slot with nobody on it is still checked. Without
            # it an entirely unstaffed shift leaves no row to notice and the
            # unfilled warning never fires -- the case most worth reporting.
            #
            # `headcount` travels with it because the grid is what the number
            # was worked out into. Projecting it away left the audit to
            # recompute the requirement from today's profile, which is a
            # different number on any shift whose standard changes across the
            # week and on any period imported from a file.
            slots=[
                {
                    "shift_name": slot.get("shift_name"),
                    "slot_date": _iso(slot.get("slot_date")),
                    "required_roles": slot.get("required_roles") or [],
                    "headcount": slot.get("headcount"),
                    "requires_shift_manager": slot.get(
                        "requires_shift_manager"
                    ),
                }
                for slot in schedule.get("slots") or []
            ],
        )

    def _require_schedule(
        self, team_id: str, schedule_id: Optional[str]
    ) -> dict:
        if schedule_id:
            return self._repository.get_schedule(schedule_id, team_id)
        schedule = self._repository.current_schedule(team_id)
        if schedule is None:
            raise NotFoundError("אין סידור פעיל")
        return schedule

    def _recent_assignments(
        self, team_id: str, before: str
    ) -> List[dict]:
        """Assignments from earlier periods, for fairness.

        The scheduler needs to know who has been carrying the nights, and
        that is not visible inside the period being built.

        **Briefly cached, because nothing a build does can change it.** It
        reads only periods starting *before* the one being generated, so the
        answer is identical for every span of a run — and it was recomputed
        for each one, scanning and joining the team's whole schedule history
        per generated date. The window is short enough that a period imported
        or edited alongside a build is picked up on the next read.
        """
        key = (team_id, before)
        now = time.monotonic()
        with self._history_lock:
            cached = self._history_cache.get(key)
            if cached and cached[0] > now:
                return list(cached[1])

        rows: List[dict] = []
        for period in self._repository.list_schedules(team_id):
            if _iso(period["starts_on"]) >= before:
                continue
            rows.extend(
                {
                    "employee": row["employee"],
                    "shift": row["shift"],
                    "date": _iso(row["date"]),
                }
                for row in self._repository.assignments(period["id"], team_id)
            )
            if len(rows) > 300:
                break
        with self._history_lock:
            # Bounded so a long-lived process serving many teams cannot grow
            # this without limit; the entries are cheap and short-lived, and
            # dropping the oldest costs one re-read.
            if len(self._history_cache) > 64:
                self._history_cache.clear()
            self._history_cache[key] = (now + _HISTORY_CACHE_SECONDS, rows)
        return list(rows)


def _quiet() -> dict:
    """A briefing with nothing to say.

    The shape a caller gets when the agent cannot speak -- no profile yet, or
    the model failed. Identical to the shape it returns when it genuinely has
    nothing to report, so the UI has one case to render and a briefing that
    could not be produced never surfaces as an error beside the calendar.
    """
    return {"headline": "", "items": [], "quiet": True}


def _period(row: dict) -> dict:
    """One row of the period list, with its dates as strings."""
    return dict(
        row,
        starts_on=_iso(row.get("starts_on")),
        ends_on=_iso(row.get("ends_on")),
    )


def _change(row: dict) -> dict:
    """One change-log row, with its date and timestamp as strings.

    `created_at` is a `datetime`, not a `date`, and `_iso` handles both --
    anything carrying `isoformat` comes back as text.
    """
    return dict(
        row,
        slot_date=_iso(row.get("slot_date")) or None,
        created_at=_iso(row.get("created_at")) or None,
    )


def _dated(schedule: dict) -> dict:
    """Every date in a schedule as an ISO string.

    The repository returns real `DATE` columns, so a schedule read straight
    back out carries `datetime.date` objects while the HTTP contract declares
    strings. Pydantic refuses those on the way out, which turns an otherwise
    successful write into a 500 -- and only on the routes that re-read what
    they just stored, which is why the fake-repository tests (storing strings
    throughout) never saw it.

    Normalised here rather than at each route because `_view` is the one
    place every schedule-carrying response passes through: a route added
    later gets this for free instead of rediscovering the bug.
    """
    schedule["starts_on"] = _iso(schedule.get("starts_on"))
    schedule["ends_on"] = _iso(schedule.get("ends_on"))
    schedule["slots"] = [
        dict(slot, slot_date=_iso(slot.get("slot_date")))
        for slot in schedule.get("slots") or []
    ]
    schedule["assignments"] = [
        dict(row, date=_iso(row.get("date")))
        for row in schedule.get("assignments") or []
    ]
    return schedule


def _has_shifts(profile: dict) -> bool:
    """Whether this profile can produce a grid at all.

    Deliberately the same test `build_slots` applies -- a dict with a usable
    name -- rather than merely `profile["shifts"]` being non-empty. A shift
    the builder silently skips is, for the manager pressing the button,
    identical to one that was never declared, and a gate that disagreed with
    the builder would let exactly that case through to an empty grid and a
    502 with nothing to act on. That was the original bug.
    """
    return any(
        isinstance(shift, dict) and (shift.get("name") or "").strip()
        for shift in (profile or {}).get("shifts") or []
    )


def _window(schedule: Optional[dict]) -> tuple:
    """The date range a schedule covers, as ISO strings."""
    if not schedule:
        return None, None
    return _iso(schedule.get("starts_on")), _iso(schedule.get("ends_on"))


def _employees(profile: dict) -> List[dict]:
    people = (profile or {}).get("employees")
    return [row for row in people or [] if isinstance(row, dict)]


def _shifts(profile: dict) -> List[dict]:
    shifts = (profile or {}).get("shifts")
    return [row for row in shifts or [] if isinstance(row, dict)]


def _generation_required_rows(
    required: List[dict], slots: List[dict], profile: dict
) -> List[dict]:
    """Validate and persist manager-pinned rows before generation starts."""
    people = {
        _text(row.get("name")) for row in _employees(profile)
        if _text(row.get("name"))
    }
    slot_index = {
        (_text(row.get("shift_name")), _iso(row.get("slot_date"))): row
        for row in slots
    }
    rows, seen = [], set()
    for item in required:
        employee = _text(item.get("employee"))
        shift = _text(item.get("shift"))
        date = _iso(item.get("date"))
        if employee not in people:
            raise AgentError("העובד שנבחר לשיבוץ החובה אינו קיים בצוות")
        slot = slot_index.get((shift, date))
        if slot is None:
            raise AgentError("המשמרת שנבחרה לשיבוץ החובה אינה קיימת בטווח הזה")
        key = (employee, shift, date)
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "slot_id": slot["id"],
            "employee": employee,
            "reason": "שיבוץ חובה שנבחר על ידי המנהל בעת בניית הסידור",
            "source": ASSIGNED_BY_MANAGER,
        })
    return rows


def _model_assignment(row: dict) -> dict:
    return {
        "employee": _text(row.get("employee")),
        "shift": _text(row.get("shift")),
        "date": _iso(row.get("date")),
        "reason": _text(row.get("reason")) or "שיבוץ קיים בסידור",
    }


def _now() -> str:
    """This instant, UTC, as the browser will parse it.

    A `Z` suffix rather than `+00:00` because the value is read by
    `Date.parse` in the poller, and a bare naive string there is read as
    *local* time -- which would make a fresh heartbeat look hours stale to a
    manager in Israel and stall a job that is working perfectly.
    """
    stamp = datetime.datetime.now(datetime.timezone.utc)
    return stamp.replace(microsecond=0, tzinfo=None).isoformat() + "Z"


def _span_dates(entry: dict) -> List[str]:
    """The dates one checkpoint entry covers.

    Derived from `date`/`through` when `dates` is absent, so a job opened
    before spans existed — one already checkpointed and half finished when
    the code was deployed — resumes as the run of single days it is, rather
    than failing on a field its stored state never had.
    """
    stored = entry.get("dates")
    if isinstance(stored, list) and stored:
        return [_iso(item) for item in stored if _iso(item)]
    first = _iso(entry.get("date"))
    last = _iso(entry.get("through")) or first
    try:
        start = datetime.date.fromisoformat(first)
        end = datetime.date.fromisoformat(last)
    except (TypeError, ValueError):
        return [first] if first else []
    dates = []
    while start <= end:
        dates.append(start.isoformat())
        start += datetime.timedelta(days=1)
    return dates


def _completed_dates(days: List[dict]) -> int:
    """Progress in dates, not in model calls. See `start_generation`."""
    return sum(
        len(_span_dates(item)) for item in days
        if item.get("status") == GENERATION_COMPLETE
    )


def _manager_rows_in(schedule: dict, dates) -> List[dict]:
    """What the manager placed by hand anywhere in a span of a running job.

    These become the span's pins: the agent fills around them and
    `_persisted_generation_rows` keeps them whether or not the model repeats
    them, which is what lets the board stay writable while a build runs.
    """
    wanted = set(dates)
    return [
        {
            "employee": _text(row.get("employee")),
            "shift": _text(row.get("shift")),
            "date": _iso(row.get("date")),
        }
        for row in schedule.get("assignments") or []
        if _iso(row.get("date")) in wanted
        and row.get("source") == ASSIGNED_BY_MANAGER
        and _text(row.get("employee")) and _text(row.get("shift"))
    ]


def _manager_rows_on(schedule: dict, day: str) -> List[dict]:
    """What the manager placed by hand on one date of a running job."""
    return _manager_rows_in(schedule, {day})


def _merged_required_rows(
    pinned: List[dict], manual: List[dict]
) -> List[dict]:
    """The pins for one date, without repeating a row named by both."""
    rows, seen = [], set()
    for row in list(pinned) + list(manual):
        key = (
            _text(row.get("employee")),
            _text(row.get("shift")),
            _iso(row.get("date")),
        )
        if not key[0] or key in seen:
            continue
        seen.add(key)
        rows.append(row)
    return rows


def _persisted_generation_rows(
    schedule: dict, generated: List[dict], dates,
    shift_names: Optional[List[str]] = None,
) -> List[dict]:
    """Replace the generated dates while preserving every other checkpoint.

    Manager-placed rows on those dates are kept rather than replaced. They
    went in as pins the model was told to work around, so dropping the ones
    it failed to repeat would silently undo a manager's own click -- and the
    board is writable while the job runs, so that click can land between the
    moment the span was read and the moment it was answered.

    Returns the **whole period's** rows, each carrying its date. Both writers
    read what they need: `replace_span_assignments` filters to the span it is
    deleting, and the whole-period fallback takes the list as it stands. The
    extra `date` key is ignored by the insert either way.
    """
    # `dates` is the span being rebuilt -- one date for a single-day
    # rebuild, several for a background span. `shift_names`, when given,
    # narrows that to named shifts so rebuilding one shift leaves the rest
    # of its date alone.
    wanted = {dates} if isinstance(dates, str) else set(dates)
    shifts = {_text(name) for name in shift_names or [] if _text(name)}
    rows = [
        {
            "slot_id": row["slot_id"],
            "employee": row["employee"],
            "reason": row["reason"],
            "source": row.get("source") or "agent",
            "date": _iso(row.get("date")),
        }
        for row in schedule.get("assignments") or []
        if _iso(row.get("date")) not in wanted
        or (shifts and _text(row.get("shift")) not in shifts)
        or row.get("source") == ASSIGNED_BY_MANAGER
    ]
    kept = {
        (row.get("employee"), _text(row.get("shift")), _iso(row.get("date")))
        for row in schedule.get("assignments") or []
        if _iso(row.get("date")) in wanted
        and (not shifts or _text(row.get("shift")) in shifts)
        and row.get("source") == ASSIGNED_BY_MANAGER
    }
    existing_sources = {
        (row.get("employee"), row.get("shift"), _iso(row.get("date"))):
            row.get("source") or "agent"
        for row in schedule.get("assignments") or []
    }
    slot_index = {
        (_text(slot.get("shift_name")), _iso(slot.get("slot_date"))): slot["id"]
        for slot in schedule.get("slots") or []
    }
    for item in generated:
        slot_id = slot_index.get((item.get("shift"), _iso(item.get("date"))))
        if slot_id is None:
            continue
        key = (item.get("employee"), item.get("shift"), _iso(item.get("date")))
        if key in kept:
            # Already carried over above, with the manager's own source and
            # reason. Adding it again would be a duplicate row for one slot.
            continue
        rows.append({
            "slot_id": slot_id,
            "employee": item["employee"],
            "reason": item["reason"],
            "source": existing_sources.get(key, "agent"),
            "date": _iso(item.get("date")),
        })
    return rows


def _nothing_applied(operations: List[dict]) -> str:
    """Why a confirmed proposal changed nothing, as the manager reads it.

    One operation named, not all of them: a manager handed a list of four
    targets that were not found reads none of them, and the first is what
    the request was mostly about.
    """
    first = next(
        (row for row in operations if isinstance(row, dict)), None
    )
    if first is None:
        return "לא היה שינוי להחיל"
    employee = (first.get("employee") or "").strip()
    shift = (first.get("shift") or "").strip()
    date = _iso(first.get("date"))
    if first.get("action") == OP_ASSIGN:
        return (
            "לא ניתן לשבץ את %s: אין משמרת %s בתאריך %s בסידור הזה."
            % (employee, shift or "המבוקשת", date)
        )
    return (
        "לא נמצא שיבוץ של %s ל%s בתאריך %s, אז לא בוצע שינוי."
        % (employee, shift or "אותו יום", date)
    )


def _match(
    schedule: dict, employee: str, shift: str, date: str
) -> Optional[dict]:
    """The stored assignment an operation names, if it is there."""
    for row in schedule.get("assignments") or []:
        if (
            row.get("employee") == employee
            and _iso(row.get("date")) == date
            and (not shift or row.get("shift") == shift)
        ):
            return row
    return None


def _find_assignment(schedule: dict, assignment_id: str) -> Optional[dict]:
    for row in schedule.get("assignments") or []:
        if row.get("id") == assignment_id:
            return row
    return None


def _moved_from(previous: Optional[dict]) -> str:
    """A default agent reason for a drag the manager did not annotate.

    Says what happened rather than pretending to a judgment the agent did not
    make — the manager moved this, and the log should read that way.
    """
    if not previous:
        return "הועבר על ידי המנהל"
    return "הועבר על ידי המנהל מ%s ב-%s" % (
        previous.get("shift") or "", _iso(previous.get("date")),
    )


def _applied(schedule: dict, operations: List[dict]) -> List[dict]:
    """The assignment list as a proposal would leave it.

    Computed in memory and never written: this exists so the audit can report
    on a change the manager has not accepted yet.
    """
    rows = [
        {
            "employee": row.get("employee"),
            "shift": row.get("shift"),
            "date": _iso(row.get("date")),
        }
        for row in schedule.get("assignments") or []
    ]
    for operation in operations or []:
        action = operation.get("action")
        employee = operation.get("employee")
        shift = operation.get("shift")
        date = _iso(operation.get("date"))
        if action == OP_REMOVE:
            rows = [
                row for row in rows
                if not (row["employee"] == employee
                        and row["date"] == date
                        and (not shift or row["shift"] == shift))
            ]
        elif action == OP_ASSIGN:
            rows.append(
                {"employee": employee, "shift": shift, "date": date}
            )
        elif action == OP_SWAP:
            other = operation.get("with_employee")
            other_shift = operation.get("with_shift") or shift
            other_date = _iso(operation.get("with_date")) or date
            for row in rows:
                if (row["employee"] == employee and row["date"] == date
                        and row["shift"] == shift):
                    row["employee"] = other
                elif (row["employee"] == other and row["date"] == other_date
                        and row["shift"] == other_shift):
                    row["employee"] = employee
    return rows


def _iso(value: Any) -> str:
    """Dates arrive as `datetime.date` from SQL and as strings from the model."""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value.strip() if isinstance(value, str) else ""


def _constraint_time(value: Any) -> str:
    """Validate an optional wall-clock bound at the API/service boundary."""
    text = _text(value)
    if not text:
        return ""
    try:
        parsed = datetime.time.fromisoformat(text)
    except ValueError:
        raise AgentError("שעת האילוץ אינה תקינה")
    return parsed.strftime("%H:%M")


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _pattern_key(entry: dict) -> str:
    """The identity of a counted pattern: this person, shift and weekday.

    Stored in `subject` and used to deduplicate, so the same pattern seen
    again is recognised as the same observation however it ends up worded.
    The tally is keyed on exactly this triple, which is what makes it a
    stable name rather than a hash of a sentence that may change.
    """
    parts = [
        _text(entry.get("employee")),
        _text(entry.get("shift")),
        _text(entry.get("weekday")),
    ]
    if not parts[0]:
        return ""
    return "|".join(parts)


def _pattern_sentence(entry: dict) -> str:
    """The counted pattern as a sentence, with no model involved.

    Deliberately flat and slightly clumsy: it describes what was counted and
    claims nothing beyond it. The background path has no model (see
    `observe_quietly`), and a template that tried to sound like the manager
    would be putting words in their mouth that nobody wrote. When
    `learn_from_changes` does run, the model's wording replaces this.
    """
    employee = _text(entry.get("employee"))
    shift = _text(entry.get("shift"))
    weekday = _text(entry.get("weekday"))
    where = " ".join(part for part in (shift, weekday) if part)
    if where:
        return "נראה ש%s לא משובץ/ת ל%s" % (employee, where)
    return "נראה שיש תיקונים חוזרים בשיבוץ של %s" % employee


def _pattern_evidence(entry: dict) -> str:
    """The count and the manager's own reasons, verbatim.

    Never a paraphrase: "הועבר/ה 3 פעמים, מהנימוקים: לימודים" is a claim the
    manager can check in a second, and a checkable claim is what makes a
    suggestion something they can meaningfully approve (D21). A summary of
    their reasons would be the agent asking them to trust its reading of
    what they wrote.
    """
    count = entry.get("count") or 0
    said = [_text(reason) for reason in entry.get("reasons") or []]
    said = [reason for reason in said if reason]
    evidence = "תוקן %d פעמים" % count
    window = " ".join(
        part for part in (
            _text(entry.get("first_seen")), _text(entry.get("last_seen"))
        ) if part
    )
    if window:
        evidence += " (%s)" % window.replace(" ", " – ")
    if said:
        evidence += ", מהנימוקים שנרשמו: " + "; ".join(said[:3])
    return evidence


def _worded_by_subject(
    rules: List[dict], repeated: List[dict]
) -> Dict[str, str]:
    """Match the model's candidate sentences back onto counted patterns.

    Matched by the person's name appearing in the rule's text, which is
    loose on purpose. A miss costs nothing -- the pattern is still recorded
    with its counted sentence -- while a strict join would need the model to
    echo a key back, and a model asked to carry an identifier around is a
    model given a way to get one wrong.
    """
    worded: Dict[str, str] = {}
    for entry in repeated:
        employee = _text(entry.get("employee"))
        subject = _pattern_key(entry)
        if not subject:
            continue
        for rule in rules or []:
            text = _text(rule.get("text"))
            if text and employee and employee in text:
                worded[subject] = text
                break
    return worded


__all__ = ["ScheduleService"]
