"""The named questions the agent may ask about a schedule, answered in code.

**Pure Python. No LLM call anywhere in this file.** Every function here is
arithmetic or a filter over state the board already renders, and that is the
whole point: the model chooses *which* question to ask and how to say the
answer in Hebrew, while what the answer *is* comes from here
([D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).

## Why a tool layer rather than a bigger prompt

`ChangeAgent` already hands the model the entire period, the roster and the
constraints in one payload and asks it to produce operations. That works for
*"דנה חולה ביום חמישי"* and stops working for everything multi-step: asking
"who can replace יוסי this weekend" that way means the model must find the
weekend, find יוסי's rows in it, work out who is free, and rank them — four
countable things, in one turn, from a wall of JSON. Each is something a model
gets subtly wrong in the way `audit.py`'s own docstring describes: wrong in a
way that reads exactly like right.

So the questions are named, and each one is answered by code:

- `read_period` — the schedule for a date or a period id, with its warnings.
- `employee_state` — one person's shifts, hours, constraints and warnings.
- `coverage_gaps` — slots short of their headcount, worst first.
- `validate_placement` — what one placement would cost (`bl/placement.py`).
- `find_replacements` — who could take a slot, ranked, each with its reason.
- `publish_readiness` — what stands between this period and the team seeing it.

**None of them writes.** This module is handed a repository and uses it for
reads only; the write path stays `schedule_service.apply()` behind the
manager's confirmation, exactly as it was. A tool layer that could write
would be a second way to change a schedule, and the product deliberately has
one ([D8](../../../docs/DECISIONS.md#d8--two-reasons-both-required),
[D12](../../../docs/DECISIONS.md#d12--dragging-a-shift-is-a-proposal-not-an-edit)).

**Every tool takes `team_id` as its first argument** and passes it to the
repository, which filters on it. It comes from the caller's signed session
and never from a request body or from the model's own output
([D10](../../../docs/DECISIONS.md#d10--one-workspace-per-team-the-boss-holds-a-password-members-hold-a-link)).
A model that names a team is naming a string; it is not reaching one.

**Errors are values, not exceptions.** A tool asked about an employee the
roster does not carry returns `found: False` and says so in Hebrew, rather
than raising. The caller is a planning loop that has to be able to say "אין
עובד בשם הזה" and carry on — an exception there would end a turn that still
had something useful to report. `AgentError` is reserved for input that is
malformed rather than merely absent.
"""

import datetime
from typing import Any, Dict, List, Optional

from app.bl.audit import audit, fairness
from app.bl.placement import check as check_placement
from app.bl.placement import suggest_alternatives
from app.common.errors import AgentError

# Every tool the agent may call, by name. The planner picks from this list
# and nothing else -- a name outside it is a tool that does not exist, and
# answering it with an error rather than an improvisation is what keeps the
# model from describing capabilities the product does not have.
TOOL_READ_PERIOD = "read_period"
TOOL_EMPLOYEE_STATE = "employee_state"
TOOL_COVERAGE_GAPS = "coverage_gaps"
TOOL_VALIDATE_PLACEMENT = "validate_placement"
TOOL_FIND_REPLACEMENTS = "find_replacements"
TOOL_PUBLISH_READINESS = "publish_readiness"

TOOL_NAMES = (
    TOOL_READ_PERIOD,
    TOOL_EMPLOYEE_STATE,
    TOOL_COVERAGE_GAPS,
    TOOL_VALIDATE_PLACEMENT,
    TOOL_FIND_REPLACEMENTS,
    TOOL_PUBLISH_READINESS,
)

# What each tool is for, in the manager's language rather than the code's.
# Handed to the model as its menu and rendered in the UI as what the agent
# did, so the two can never describe the tools differently.
TOOL_DESCRIPTIONS = {
    TOOL_READ_PERIOD: "קריאת הסידור של תקופה או של תאריך מסוים",
    TOOL_EMPLOYEE_STATE: "המשמרות, השעות והאילוצים של עובד אחד",
    TOOL_COVERAGE_GAPS: "משמרות שחסרים בהן אנשים",
    TOOL_VALIDATE_PLACEMENT: "בדיקה מה יקרה אם משבצים מישהו למשמרת",
    TOOL_FIND_REPLACEMENTS: "מי יכול לקחת משמרת במקום מישהו אחר",
    TOOL_PUBLISH_READINESS: "מה חסר לפני פרסום התקופה לצוות",
}

# How many candidates a replacement search returns. The same bound
# `placement._MAX_ALTERNATIVES` uses and for the same reason: past a handful
# the list stops being an answer and becomes a second grid to read.
_MAX_CANDIDATES = 5

# How many gaps are worth naming in one answer. A period missing thirty
# people is missing a schedule, not a shift, and listing all thirty buries
# the one the manager asked about.
_MAX_GAPS = 12


class ScheduleTools:
    """The read-only operations the agent runs against one workspace.

    Constructed per call from `schedule_service`, which owns the repository.
    Holds no state of its own beyond that handle: two managers asking the
    same question at the same moment share nothing.
    """

    def __init__(self, repository):
        self._repository = repository

    # -- the menu ----------------------------------------------------------

    def run(self, team_id: str, name: str, arguments: Optional[dict] = None) -> dict:
        """Dispatch one named tool call. The planner's only entry point.

        Returns `{"tool", "ok", ...}` whatever happens, including for a name
        that does not exist. The planning loop feeds this straight back to
        the model, so a failure has to be describable rather than thrown —
        "there is no tool called that" is information the next turn can act
        on, and an exception is not.
        """
        arguments = arguments if isinstance(arguments, dict) else {}
        handler = {
            TOOL_READ_PERIOD: self.read_period,
            TOOL_EMPLOYEE_STATE: self.employee_state,
            TOOL_COVERAGE_GAPS: self.coverage_gaps,
            TOOL_VALIDATE_PLACEMENT: self.validate_placement,
            TOOL_FIND_REPLACEMENTS: self.find_replacements,
            TOOL_PUBLISH_READINESS: self.publish_readiness,
        }.get(_text(name))
        if handler is None:
            return {
                "tool": _text(name),
                "ok": False,
                "error": "אין כלי בשם הזה",
            }
        try:
            result = handler(team_id, **_arguments_for(handler, arguments))
        except AgentError as failure:
            # A tool refusing malformed input is still an answer the turn can
            # use. Surfaced in Hebrew because everything leaving the backend
            # is (`bl/CLAUDE.md`).
            return {"tool": _text(name), "ok": False, "error": str(failure)}
        return dict(result, tool=_text(name), ok=result.get("ok", True))

    # -- reading -----------------------------------------------------------

    def read_period(
        self,
        team_id: str,
        day: str = "",
        schedule_id: str = "",
    ) -> dict:
        """The schedule the manager means, with its warnings attached.

        `day` finds the stored period containing that date; `schedule_id`
        names one outright. Neither given means the current period — which
        is what a manager asking "what does this week look like" means, and
        making them say so would be asking a question the board already
        answers by being open.

        Returns `found: False` rather than raising when there is no period.
        A workspace whose first week has not been built yet is an ordinary
        state, not an error, and the agent's answer to it is a sentence
        rather than a stack trace.
        """
        schedule = self._schedule(team_id, day=day, schedule_id=schedule_id)
        if schedule is None:
            return {
                "found": False,
                "reason": "אין סידור מאוחסן לתאריך הזה",
                "schedule": None,
            }
        profile = self._profile(team_id)
        return {
            "found": True,
            "schedule": _period_view(schedule),
            "warnings": self._warnings(team_id, schedule, profile),
            "fairness": fairness(
                _audit_assignments(schedule), _shifts(profile),
                _employees(profile),
            ),
        }

    def employee_state(
        self,
        team_id: str,
        employee: str,
        day: str = "",
        schedule_id: str = "",
    ) -> dict:
        """One person's week: their shifts, hours, constraints and warnings.

        The question behind *"can we give מאיה Monday off"* and *"who can
        replace יוסי this weekend"* both start here. It reads the roster for
        the person's declared role and eligible shifts, the stored period for
        what they are actually on, and the availability table for what they
        have said they cannot do.

        An unknown name returns `found: False` with the roster attached, so
        the agent can ask *"התכוונת ל…"* against real names instead of
        inventing a person. Fabricating an employee is the specific failure
        this shape exists to make impossible.
        """
        name = _text(employee)
        if not name:
            raise AgentError("צריך לציין שם עובד")

        profile = self._profile(team_id)
        person = _find_person(profile, name)
        if person is None:
            return {
                "found": False,
                "employee": name,
                "reason": "אין עובד/ת בשם הזה ברשימת הצוות",
                "roster": [_text(row.get("name")) for row in _employees(profile)],
            }

        schedule = self._schedule(team_id, day=day, schedule_id=schedule_id)
        window = _window(schedule)
        constraints = [
            row for row in self._availability(team_id, window)
            if _text(row.get("employee")) == name
        ]

        if schedule is None:
            return {
                "found": True,
                "employee": name,
                "role": _text(person.get("role")),
                "eligible_shifts": _eligible(person),
                "shifts": [],
                "hours": 0.0,
                "constraints": constraints,
                "warnings": [],
                "schedule": None,
            }

        warnings = self._warnings(team_id, schedule, profile)
        shifts = [
            {
                "assignment_id": _text(row.get("id")),
                "shift": _text(row.get("shift")),
                "date": _iso(row.get("date")),
                "reason": _text(row.get("reason")),
            }
            for row in schedule.get("assignments") or []
            if _text(row.get("employee")) == name
        ]
        shifts.sort(key=lambda row: (row["date"], row["shift"]))

        return {
            "found": True,
            "employee": name,
            "role": _text(person.get("role")),
            "eligible_shifts": _eligible(person),
            "shifts": shifts,
            "hours": _hours_for(name, schedule, profile),
            "constraints": constraints,
            "warnings": [
                row for row in warnings
                if _text(row.get("employee")) == name
            ],
            "schedule": _period_view(schedule),
        }

    def coverage_gaps(
        self,
        team_id: str,
        day: str = "",
        schedule_id: str = "",
        starts_on: str = "",
        ends_on: str = "",
    ) -> dict:
        """Slots carrying fewer people than they ask for, worst first.

        Derived from the stored grid rather than from the assignments, which
        is the only way an *entirely* unstaffed shift is visible at all: a
        slot with nobody on it leaves no assignment row, so a walk over the
        assignments cannot see it. That is the same reason `audit.audit()`
        takes `slots`.

        `starts_on`/`ends_on` narrow the answer to a stretch of the period —
        what *"find coverage for tomorrow evening"* needs, and what keeps a
        weekend question from returning the whole week.
        """
        schedule = self._schedule(team_id, day=day, schedule_id=schedule_id)
        if schedule is None:
            return {"found": False, "gaps": [], "reason": "אין סידור מאוחסן"}

        profile = self._profile(team_id)
        first = _iso(starts_on)
        last = _iso(ends_on)

        counts: Dict[tuple, int] = {}
        for row in schedule.get("assignments") or []:
            key = (_text(row.get("shift")), _iso(row.get("date")))
            counts[key] = counts.get(key, 0) + 1

        gaps = []
        for slot in schedule.get("slots") or []:
            shift_name = _text(slot.get("shift_name"))
            date = _iso(slot.get("slot_date"))
            if first and date < first:
                continue
            if last and date > last:
                continue
            headcount = _number(slot.get("headcount"), 1)
            assigned = counts.get((shift_name, date), 0)
            if assigned >= headcount:
                continue
            gaps.append({
                "shift": shift_name,
                "date": date,
                "headcount": int(headcount),
                "assigned": assigned,
                "missing": int(headcount) - assigned,
                "why": "חסרים %d ב%s בתאריך %s." % (
                    int(headcount) - assigned, shift_name, date,
                ),
            })

        # Worst first, then chronological. A manager reading this list is
        # deciding what to fix now, and the emptiest slot is the one that
        # leaves nobody on the floor.
        gaps.sort(key=lambda row: (-row["missing"], row["date"], row["shift"]))
        return {
            "found": True,
            "schedule": _period_view(schedule),
            "gaps": gaps[:_MAX_GAPS],
            "total_gaps": len(gaps),
            "people_short": sum(row["missing"] for row in gaps),
            # Only meaningful against the profile's own vocabulary (D9); the
            # names come from the stored grid, never from a literal here.
            "shift_names": [
                _text(row.get("name")) for row in _shifts(profile)
            ],
        }

    # -- validating --------------------------------------------------------

    def validate_placement(
        self,
        team_id: str,
        employee: str,
        shift_name: str,
        slot_date: str,
        schedule_id: str = "",
        moving_assignment_id: str = "",
    ) -> dict:
        """What placing this person on this slot would cost. Writes nothing.

        `bl/placement.py` verbatim — the same call `POST /api/schedule/check`
        makes for a drag on the board. Exposed as a tool so the *agent* is
        held to the same answer the board is: an option is valid because this
        said so, never because a sentence read as though it were.

        **It does not gate.** `blocking` comes back false however bad the
        news, because the audit advises and the manager decides (D3). What
        this buys is that the agent cannot claim a placement is clean when
        the arithmetic says otherwise.
        """
        if not _text(employee):
            raise AgentError("צריך לציין שם עובד")
        if not _text(slot_date):
            raise AgentError("צריך לציין תאריך")

        schedule = self._schedule(team_id, schedule_id=schedule_id, day=slot_date)
        if schedule is None:
            return {
                "found": False,
                "reason": "אין סידור מאוחסן לתאריך הזה",
            }
        profile = self._profile(team_id)
        verdict = check_placement(
            schedule,
            profile,
            employee=_text(employee),
            shift_name=_text(shift_name),
            slot_date=_iso(slot_date),
            availability=self._availability(team_id, _window(schedule)),
            moving_assignment_id=_text(moving_assignment_id),
        )
        return dict(verdict, found=True, schedule_id=_text(schedule.get("id")))

    def find_replacements(
        self,
        team_id: str,
        shift_name: str,
        slot_date: str,
        employee: str = "",
        schedule_id: str = "",
    ) -> dict:
        """Who could take this slot, ranked, each carrying its own reason.

        The answer to *"who can replace יוסי this weekend"* for one slot of
        it. `employee` is the person coming *off* — their row is taken out of
        the hypothetical before the candidates go in, so a colleague is not
        rejected for a double-booking the replacement itself resolves.

        **Every candidate is re-validated.** `placement.suggest_alternatives`
        keeps only options that introduce no warning of their own, so an
        option that would break something is never offered as the way out of
        something else. That is what makes it honest to present these as
        valid: the same code that would warn about them was asked first.

        Ranking is `placement.py`'s — lightest week first, which is
        `audit.fairness()`'s arithmetic applied to a choice. Transparent by
        construction: `why` says the hours the ordering used.
        """
        if not _text(slot_date):
            raise AgentError("צריך לציין תאריך")

        schedule = self._schedule(team_id, schedule_id=schedule_id, day=slot_date)
        if schedule is None:
            return {
                "found": False,
                "candidates": [],
                "reason": "אין סידור מאוחסן לתאריך הזה",
            }

        profile = self._profile(team_id)
        leaving = _text(employee)
        moving = _assignment_id(schedule, leaving, _text(shift_name), _iso(slot_date))

        alternatives = suggest_alternatives(
            schedule,
            profile,
            employee=leaving,
            shift_name=_text(shift_name),
            slot_date=_iso(slot_date),
            availability=self._availability(team_id, _window(schedule)),
            moving_assignment_id=moving,
        )
        candidates = alternatives.get("employees") or []

        return {
            "found": True,
            "schedule_id": _text(schedule.get("id")),
            "shift": _text(shift_name),
            "date": _iso(slot_date),
            "replacing": leaving,
            "candidates": candidates[:_MAX_CANDIDATES],
            # Where this person could go instead, when the question turns out
            # to be "move them" rather than "replace them".
            "other_slots": alternatives.get("slots") or [],
            "ranked_by": (
                "לפי שעות מצטברות בתקופה — הקל/ה ביותר ראשון/ה, "
                "אחרי סינון של כל מי שהשיבוץ היה יוצר אצלו/ה אזהרה."
            ),
        }

    # -- publishing --------------------------------------------------------

    def publish_readiness(
        self,
        team_id: str,
        day: str = "",
        schedule_id: str = "",
    ) -> dict:
        """What stands between this period and the team seeing it.

        The answer to *"what is still missing before we publish next week"*.
        Gathers the gaps, the warnings and the pending employee requests into
        one list, because those are the three things a manager checks by hand
        before pressing publish and checking them by hand is what this
        replaces.

        **`ready` is a description, not a gate.** A period with warnings
        publishes exactly as one without them does — the publish button is
        live regardless (D3), and this only says what the manager would be
        publishing. Returning `False` here has never stopped anything and
        must not start.
        """
        schedule = self._schedule(team_id, day=day, schedule_id=schedule_id)
        if schedule is None:
            return {
                "found": False,
                "ready": False,
                "reason": "אין סידור מאוחסן לתאריך הזה",
            }

        profile = self._profile(team_id)
        warnings = self._warnings(team_id, schedule, profile)
        gaps = self.coverage_gaps(team_id, schedule_id=_text(schedule.get("id")))
        pending = self._pending_requests(team_id)

        blockers = []
        if gaps.get("people_short"):
            blockers.append(
                "חסרים %d שיבוצים ב-%d משמרות."
                % (gaps["people_short"], gaps.get("total_gaps", 0))
            )
        serious = [
            row for row in warnings
            if _text(row.get("severity")) == "warning"
        ]
        if serious:
            blockers.append("יש %d אזהרות פתוחות בסידור." % len(serious))
        if pending:
            blockers.append(
                "יש %d בקשות אילוץ שממתינות להחלטה." % len(pending)
            )

        return {
            "found": True,
            "schedule": _period_view(schedule),
            "status": _text(schedule.get("status")),
            "published": _text(schedule.get("status")) == "published",
            # Descriptive only. Nothing branches on this before a publish.
            "ready": not blockers,
            "blockers": blockers,
            "gaps": gaps.get("gaps") or [],
            "warnings": warnings,
            "pending_requests": pending,
        }

    # -- shared reads ------------------------------------------------------

    def _schedule(
        self, team_id: str, day: str = "", schedule_id: str = ""
    ) -> Optional[dict]:
        """The period a tool call is about, by id, by date, or the current one.

        Every path goes through the repository with `team_id`, so a
        `schedule_id` the model produced out of thin air reads as missing
        rather than as another workspace's week (D10).
        """
        wanted = _text(schedule_id)
        if wanted:
            try:
                return self._repository.get_schedule(wanted, team_id)
            except Exception:
                # Including NotFoundError: a period that is not this team's is
                # indistinguishable from one that does not exist, which is the
                # same answer the HTTP layer gives.
                return None

        target = _iso(day)
        if target:
            for period in self._repository.list_schedules(team_id):
                if _iso(period["starts_on"]) <= target <= _iso(period["ends_on"]):
                    return self._repository.get_schedule(period["id"], team_id)
            return None

        return self._repository.current_schedule(team_id)

    def _profile(self, team_id: str) -> dict:
        return self._repository.team_profile(team_id) or {}

    def _availability(self, team_id: str, window: tuple) -> List[dict]:
        """Constraints over a period, in the shape `audit.py` reads."""
        return [
            {
                "employee": _text(row.get("employee")),
                "date": _iso(row.get("constraint_date")),
                "shift": _text(row.get("shift_name")),
                "available": row.get("available"),
                "reason": _text(row.get("reason")),
                "source": _text(row.get("source")),
            }
            for row in self._repository.availability(team_id, window[0], window[1])
        ]

    def _warnings(
        self, team_id: str, schedule: dict, profile: dict
    ) -> List[dict]:
        """The audit over a stored period. The same call the overview makes."""
        return audit(
            _audit_assignments(schedule),
            _shifts(profile),
            _employees(profile),
            self._availability(team_id, _window(schedule)),
            profile,
            [
                dict(slot, slot_date=_iso(slot.get("slot_date")))
                for slot in schedule.get("slots") or []
            ],
        )

    def _pending_requests(self, team_id: str) -> List[dict]:
        """Employee constraint submissions awaiting a ruling (D14).

        Read through `getattr` because not every repository handed to this
        class owns the identities table — the tests' fakes do not, and a
        publish-readiness check that crashed on a repository without employee
        identities would make the tool unusable for a workspace that never
        turned them on.
        """
        reader = getattr(self._repository, "pending_constraint_requests", None)
        if reader is None:
            return []
        try:
            return list(reader(team_id) or [])
        except Exception:
            return []


# -- helpers ---------------------------------------------------------------


def _arguments_for(handler, arguments: dict) -> dict:
    """The subset of `arguments` this handler actually accepts.

    The model produces argument names; a name the tool does not take would be
    a `TypeError` deep in a dispatch, which is a crash rather than an answer.
    Dropping the unknown ones turns a slightly-wrong call into a call, and
    the tool's own required-argument check is what still refuses a call that
    is missing something it needs.
    """
    accepted = handler.__code__.co_varnames[:handler.__code__.co_argcount]
    return {
        key: value for key, value in arguments.items()
        if key in accepted and key not in ("self", "team_id")
    }


def _period_view(schedule: dict) -> dict:
    """A period as a tool answer carries it: identity and bounds, no rows.

    The assignments are not repeated here because every tool that needs them
    returns the slice it is about. A tool answer that carried the whole grid
    would put the same wall of JSON back in front of the model that having
    tools was meant to take away.
    """
    return {
        "id": _text(schedule.get("id")),
        "starts_on": _iso(schedule.get("starts_on")),
        "ends_on": _iso(schedule.get("ends_on")),
        "status": _text(schedule.get("status")),
        "slot_count": len(schedule.get("slots") or []),
        "assignment_count": len(schedule.get("assignments") or []),
    }


def _audit_assignments(schedule: dict) -> List[dict]:
    return [
        {
            "employee": _text(row.get("employee")),
            "shift": _text(row.get("shift")),
            "date": _iso(row.get("date")),
        }
        for row in (schedule or {}).get("assignments") or []
    ]


def _assignment_id(
    schedule: dict, employee: str, shift_name: str, slot_date: str
) -> str:
    """The row this person holds on this slot, if they hold one."""
    for row in (schedule or {}).get("assignments") or []:
        if (_text(row.get("employee")) == employee
                and _text(row.get("shift")) == shift_name
                and _iso(row.get("date")) == slot_date):
            return _text(row.get("id"))
    return ""


def _hours_for(employee: str, schedule: dict, profile: dict) -> float:
    """One person's assigned hours in this period, weighted as the audit does."""
    totals = fairness(
        _audit_assignments(schedule), _shifts(profile), _employees(profile)
    )
    for row in totals.get("people") or []:
        if _text(row.get("employee")) == employee:
            return float(row.get("hours") or 0.0)
    return 0.0


def _find_person(profile: dict, name: str) -> Optional[dict]:
    for person in _employees(profile):
        if _text(person.get("name")) == name:
            return person
    return None


def _eligible(person: dict) -> List[str]:
    """The shifts this person works, or empty for "no restriction stated".

    Empty means unrestricted, matching `placement._is_eligible`: the
    interview does not force the field, and reading silence as a restriction
    would report every placement in a workplace that never answered.
    """
    rows = person.get("eligible_shifts")
    return [_text(row) for row in rows] if isinstance(rows, list) else []


def _employees(profile: dict) -> List[dict]:
    rows = (profile or {}).get("employees")
    return [row for row in rows or [] if isinstance(row, dict)]


def _shifts(profile: dict) -> List[dict]:
    rows = (profile or {}).get("shifts")
    return [row for row in rows or [] if isinstance(row, dict)]


def _window(schedule: Optional[dict]) -> tuple:
    """The date range a period covers, for reading constraints over it."""
    if not schedule:
        today = datetime.date.today()
        return (today.isoformat(), today.isoformat())
    return (_iso(schedule.get("starts_on")), _iso(schedule.get("ends_on")))


def _number(value: Any, fallback: float) -> float:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, (int, float)):
        return float(value)
    return fallback


def _iso(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return _text(value)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


__all__ = [
    "ScheduleTools",
    "TOOL_NAMES",
    "TOOL_DESCRIPTIONS",
    "TOOL_READ_PERIOD",
    "TOOL_EMPLOYEE_STATE",
    "TOOL_COVERAGE_GAPS",
    "TOOL_VALIDATE_PLACEMENT",
    "TOOL_FIND_REPLACEMENTS",
    "TOOL_PUBLISH_READINESS",
]
