"""Conversational edits to a live schedule, and the change log behind them.

The step-4 loop: *"דנה חולה ביום חמישי."*

1. Parse the request.
2. **If the manager gave no reason, ask for one.** Required
   ([D8](../../../docs/DECISIONS.md#d8--two-reasons-both-required)) — and
   asked for rather than rejected, because a manager who omitted a reason
   made an omission, not an error.
3. Propose a replacement **with the agent's justification**.
4. On confirmation: apply in place, append to the log.

Proposing and applying are deliberately two calls. The manager confirms in
between, and that gap is the whole point: under D3 the agent's judgment is
final, so seeing *why* it picked this person is the manager's one cheap
chance to catch a bad call.

This module proposes. It does not write — `schedule_service.py` applies a
proposal the manager has confirmed, which is what keeps "the agent decided"
and "the manager agreed" as two separate, auditable events.
"""

import datetime
import json
from typing import Any, Dict, List, Optional

from app.bl import rotation
from app.bl.prompts import load
from app.bl.tools import resolve_employee
from app.common.errors import AgentError

_MAX_TEXT_CHARS = 4000
_MAX_OPERATIONS = 40

# What a proposal may ask for. Deliberately small: these three cover every
# change the product handles, and an operation vocabulary that grows past
# what the schedule can actually express is a way for a proposal to describe
# something no code can apply.
OP_ASSIGN = "assign"
OP_REMOVE = "remove"
OP_SWAP = "swap"
_OPERATIONS = (OP_ASSIGN, OP_REMOVE, OP_SWAP)
PROFILE_ADD_EMPLOYEE = "add_employee"
PROFILE_UPDATE_EMPLOYEE = "update_employee"
PROFILE_ADD_SHIFT = "add_shift"
PROFILE_UPDATE_SHIFT = "update_shift"
_PROFILE_OPERATIONS = (
    PROFILE_ADD_EMPLOYEE, PROFILE_UPDATE_EMPLOYEE,
    PROFILE_ADD_SHIFT, PROFILE_UPDATE_SHIFT,
)

_OPERATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["action", "employee", "shift", "date", "reason"],
    "properties": {
        "action": {"type": "string", "enum": list(_OPERATIONS)},
        "employee": {"type": "string"},
        "shift": {"type": "string"},
        "date": {"type": "string"},
        # The other half of a swap. Empty on assign and remove.
        "with_employee": {"type": "string"},
        "with_shift": {"type": "string"},
        "with_date": {"type": "string"},
        "reason": {"type": "string"},
    },
}

_CONSTRAINT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["employee", "date", "shift", "reason"],
    "properties": {
        "employee": {"type": "string"},
        "date": {"type": "string"},
        # Empty means the whole day, the same convention the interview and
        # `audit.py` use.
        "shift": {"type": "string"},
        "reason": {"type": "string"},
    },
}

_PROFILE_ITEM_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "name", "role", "eligible_shifts", "start_time", "end_time",
        "headcount", "is_on_call",
    ],
    "properties": {
        "name": {"type": "string"},
        "role": {"type": "string"},
        "eligible_shifts": {"type": "array", "items": {"type": "string"}},
        "start_time": {"type": "string"},
        "end_time": {"type": "string"},
        "headcount": {"type": "integer"},
        "is_on_call": {"type": "boolean"},
    },
}

_PROFILE_OPERATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["action", "target", "item"],
    "properties": {
        "action": {"type": "string", "enum": list(_PROFILE_OPERATIONS)},
        "target": {"type": "string"},
        "item": _PROFILE_ITEM_SCHEMA,
    },
}

CHANGE_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "reply", "needs_reason", "needs_input", "agent_reason", "operations",
        "constraints", "profile_operations",
    ],
    "properties": {
        "reply": {"type": "string"},
        # True when the manager has not said why. The answer is a question
        # back, never a rejection and never a guess.
        "needs_reason": {"type": "boolean"},
        # True when the request cannot be carried out without guessing *what
        # it refers to* -- which person, which shift, which date. A different
        # gap from `needs_reason`: that one is missing *why*, this one is
        # missing *what*, and a change made against the wrong record is not
        # fixed by knowing the reason for it (D24).
        "needs_input": {"type": "boolean"},
        "agent_reason": {"type": "string"},
        "operations": {
            "type": "array", "items": _OPERATION_SCHEMA,
            "maxItems": _MAX_OPERATIONS,
        },
        "constraints": {"type": "array", "items": _CONSTRAINT_SCHEMA},
        "profile_operations": {
            "type": "array", "items": _PROFILE_OPERATION_SCHEMA,
            "maxItems": 10,
        },
    },
}


class ChangeAgent:
    """Turn a manager's sentence into a proposal they can confirm."""

    def __init__(self, llm):
        self._llm = llm

    def propose(
        self,
        profile: dict,
        schedule: dict,
        request: str,
        stated_reason: str = "",
        availability: Optional[List[dict]] = None,
        history: Optional[List[dict]] = None,
        pending_request: str = "",
    ) -> dict:
        """What the agent would do, and why. Applies nothing.

        `pending_request` is the request a previous turn held rather than
        guess at. When it is set, `request` is the manager's *answer* to the
        question that turn asked, and the two are proposed together — the
        manager answers "ערב" and does not retype "תשבץ את דניאל".
        """
        text = _bounded(request)
        if not text:
            raise AgentError("הבקשה אינה יכולה להיות ריקה")
        pending = _bounded(pending_request)
        resolved = _resume(pending, text)
        payload = {
            "profile": _profile_for_model(profile),
            "schedule": _schedule_for_model(schedule),
            # Whose weekend each closure in the period is, already worked
            # out. Without it a spoken change was the one path into the
            # schedule that could not see the rotation: the scheduler is
            # handed the same fact, the board renders it, and the audit
            # warns about it, while the agent moved people across cycles
            # having never been told one existed.
            "closures": _closures_for_model(profile, schedule),
            "availability": _rows(availability),
            "history": _rows(history, 100),
            "request": resolved,
            # What was asked and what came back, kept apart from the merged
            # sentence. A model that can see it already asked is a model that
            # does not ask the same question twice, which is the loop this
            # closes.
            "asked_last_turn": pending,
            "answer_to_that": text if pending else "",
            "stated_reason": _bounded(stated_reason),
        }
        answer = self._ask(payload)
        return _proposal(
            answer, profile, schedule, _bounded(stated_reason),
            request=resolved,
        )

    def _ask(self, payload: dict) -> dict:
        answer = self._llm.complete_json(
            load("changes"),
            json.dumps(payload, ensure_ascii=False, default=_json_default),
            schema=CHANGE_RESPONSE_SCHEMA,
            flow="changes",
        )
        if not isinstance(answer, dict):
            raise AgentError("המודל החזיר הצעת שינוי לא תקינה")
        return answer


def _proposal(
    answer: dict, profile: dict, schedule: dict, stated_reason: str,
    request: str = "",
) -> dict:
    """The model's turn, bounded, with both gates enforced in code.

    `needs_reason` is not left to the prompt alone: a proposal that would
    change the roster without the manager having said why is withdrawn here
    and turned back into a question. D8 is the decision this protects, and a
    model that forgets it once would otherwise write an unexplained change
    into the only history the system keeps.

    `needs_input` is the same enforcement for a different gap
    ([D24](../../../docs/DECISIONS.md#d24--the-agent-asks-when-it-would-otherwise-guess--strengthens-d8)). A change whose
    *target* was guessed — a name that matches nobody on the roster, or one
    that matches several people — is withdrawn the same way, because the
    reason gate does not help here: knowing why דניאל is being moved does not
    tell you *which* דניאל got moved. The two gates are separate on purpose
    and a proposal can be held by either.
    """
    operations, dropped = _operations(answer.get("operations"), schedule)
    profile_operations = _profile_operations(
        answer.get("profile_operations"), profile
    )

    # Which operations name somebody this workplace cannot identify. Computed
    # before the reason gate because an unidentifiable target is the more
    # basic failure: a reason attached to the wrong person is worse than a
    # missing one.
    unresolved = _unresolved_people(operations, profile)

    needs_reason = bool(answer.get("needs_reason")) and not stated_reason
    if operations and not stated_reason and not answer.get("agent_reason"):
        needs_reason = True

    # An operation held back for naming several possible shifts is a
    # question, not a failure -- the same shape as an unresolvable name, and
    # asked the same way. Only when *nothing* survived: a proposal that can
    # carry out three of four moves should carry out the three and say so,
    # rather than putting the whole request behind one question.
    ambiguous = [
        row for row in dropped if row["why"] == "ambiguous_shift"
    ] if not operations else []

    needs_input = bool(answer.get("needs_input"))
    if unresolved or ambiguous:
        needs_input = True
    if needs_input:
        # Held for the same reason and in the same way as a missing reason:
        # the manager is asked, and nothing is queued in the meantime. A
        # mutation proposed against a target nobody could resolve is exactly
        # the guess this gate exists to refuse.
        operations = []
        profile_operations = []
        # One gap at a time. Asking "which דניאל, and also why?" in the same
        # breath is two questions for a manager who has answered neither, and
        # the reason is worth asking for only once the target is settled.
        needs_reason = False
    if needs_reason:
        # A question, not a rejection: the manager omitted something, and
        # the product's answer to an omission is to ask.
        operations = []
    if profile_operations:
        operations = []
        needs_reason = False

    reply = _bounded(answer.get("reply"))
    if unresolved and not reply:
        # The model claimed no ambiguity, so it wrote no question. Code found
        # one anyway, and a held proposal with nothing said would read as the
        # agent having ignored the request.
        reply = _ask_which_person(unresolved)
    elif ambiguous:
        reply = _ask_which_shift(ambiguous[0])
    elif dropped and not needs_reason and not needs_input and (
        not operations and not profile_operations
    ):
        # Everything the model asked for was aimed at something that is not
        # there. Its `reply` describes the change as though it happened, and
        # leaving that standing is how "the agent does not really change
        # shifts" felt like the agent ignoring the manager: a confident
        # sentence, no confirm button, and nothing moved. Say which target
        # was missing instead.
        reply = _report_dropped(dropped)

    return {
        "reply": reply,
        "needs_reason": needs_reason,
        "needs_input": needs_input,
        # Echoed back only while a question is open. A finished proposal
        # carries nothing to resume, so the client cannot send a stale
        # request back and have an answered question re-open.
        "pending_request": request if needs_input else "",
        "agent_reason": _bounded(answer.get("agent_reason")),
        "stated_reason": stated_reason,
        "operations": operations,
        "profile_operations": profile_operations,
        "constraints": _constraints(answer.get("constraints")),
    }


def _resume(pending: str, reply: str) -> str:
    """The held request and the manager's answer to it, read as one sentence.

    The same join `bl/planner.py` does on the read path, and deliberately the
    same shape: a clarification answers the request rather than replacing it,
    so what goes to the model is both halves. Plain text rather than a parsed
    pending-intent record — the sentence is what the model already reads, and
    a structured duplicate of it is a second thing to keep in sync.
    """
    pending = _bounded(pending)
    reply = _bounded(reply)
    if not pending:
        return reply
    if not reply:
        return pending
    if pending in reply:
        return reply
    return "%s (%s)" % (pending, reply)


def _unresolved_people(operations: List[dict], profile: dict) -> List[dict]:
    """Every person an operation names whom the roster cannot pin down.

    Two failures, reported apart because they are asked about differently: a
    name matching *several* people needs "which one", and a name matching
    *none* needs "who did you mean". Both are the model having supplied an
    identity rather than read one, which is the thing it may not do.
    """
    unresolved = []
    seen = set()
    for operation in operations:
        for field in ("employee", "with_employee"):
            name = _bounded(operation.get(field))
            if not name or name in seen:
                continue
            seen.add(name)
            found = resolve_employee(profile, name)
            if found["found"]:
                continue
            unresolved.append({
                "name": name,
                "ambiguous": bool(found["ambiguous"]),
                "matches": found["matches"],
            })
    return unresolved


def _ask_which_person(unresolved: List[dict]) -> str:
    """The question code asks when the model did not.

    Deliberately one question about one name — the first unresolved one —
    rather than a list. A manager handed three questions answers none of
    them, and resolving the first commonly resolves the rest.
    """
    first = unresolved[0]
    if first["ambiguous"] and first["matches"]:
        return "יש כמה עובדים בשם %s — למי מהם התכוונתם: %s?" % (
            first["name"], "‏, ".join(first["matches"]),
        )
    return (
        "לא זיהיתי מי זה/זו %s ברשימת הצוות. אפשר לכתוב את השם כפי שהוא "
        "מופיע ברשימה?" % first["name"]
    )


def _ask_which_shift(held: dict) -> str:
    """The question code asks when a change named a day but not a shift.

    Offers the real candidates rather than asking an open question — one tap
    instead of another sentence, which is what the prompt asks the model for
    and what code should do when the model did not.
    """
    options = held.get("options") or []
    if options:
        return "לאיזו משמרת ב-%s התכוונת עבור %s — %s?" % (
            held["date"], held["employee"], " או ".join(options),
        )
    return "לאיזו משמרת ב-%s התכוונת עבור %s?" % (held["date"], held["employee"])


def _report_dropped(dropped: List[dict]) -> str:
    """What could not be carried out, said plainly instead of swallowed.

    One line about one target, for the same reason `_ask_which_person` asks
    about one name: a manager handed a list of four things that did not work
    reads none of them. The first is the one the request was mostly about.
    """
    first = dropped[0]
    if first["why"] == "not_assigned":
        return (
            "%s לא משובץ/ת ב-%s בסידור הזה, אז אין מה להוריד. אפשר לבדוק את "
            "התאריך?" % (first["employee"], first["date"])
        )
    if first["shift"]:
        return (
            "אין משמרת %s בתאריך %s בסידור הזה, אז לא ביצעתי כלום. אפשר "
            "לבדוק את המשמרת ואת התאריך?" % (first["shift"], first["date"])
        )
    return (
        "אין משמרות בתאריך %s בסידור הזה, אז לא ביצעתי כלום. אפשר לבדוק את "
        "התאריך?" % first["date"]
    )


def _operations(offered: Any, schedule: dict) -> tuple:
    """Operations bounded to what this schedule can actually be changed by.

    Returns the usable operations **and what was dropped**, because a
    dropped operation used to disappear: the model would answer "העברתי את
    דנה לערב", code would find no slot for the row it named, and the manager
    got a confident sentence with nothing to confirm and nothing changed.
    Silence was the bug — a target that cannot be found is something to say,
    not something to swallow (see `_report_dropped`).

    **An empty shift means "that day", not "no shift".** The model writes one
    when the manager did: *"תוריד את דנה מיום חמישי"* names a person and a
    date and nothing else, and `schedule_service._match` has always read a
    blank shift as the whole day. Bounding against the slot grid alone
    therefore threw away the most ordinary removal the product has — `("",
    date)` is never a slot. So a blank shift is resolved against the
    schedule: one assignment that day fills itself in, several is a question
    for the manager (D24), and none is a target that is not there.

    A shift and date the period genuinely does not contain is still dropped.
    That is a check on whether the target exists, not on whether the choice
    was good — the audit is what comments on the choice.
    """
    if not isinstance(offered, list):
        return [], []
    slots = {
        (_bounded(slot.get("shift_name")), _date(slot.get("slot_date")))
        for slot in (schedule or {}).get("slots") or []
    }
    # What each person is actually on, per date. A removal is bounded by this
    # rather than by the grid: the row being taken off is an assignment, and
    # a schedule with no stored slots (an import, an older period) still has
    # assignments somebody may need removed.
    rostered: Dict[tuple, List[str]] = {}
    for row in (schedule or {}).get("assignments") or []:
        if not isinstance(row, dict):
            continue
        key = (_bounded(row.get("employee")), _date(row.get("date")))
        shift = _bounded(row.get("shift"))
        if key[0] and key[1] and shift not in rostered.setdefault(key, []):
            rostered[key].append(shift)

    operations, dropped = [], []
    for item in offered[:_MAX_OPERATIONS]:
        if not isinstance(item, dict):
            continue
        action = _bounded(item.get("action"))
        employee = _bounded(item.get("employee"))
        date = _date(item.get("date"))
        if action not in _OPERATIONS or not employee or not date:
            continue
        shift, why = _resolve_shift(
            action, employee, _bounded(item.get("shift")), date,
            slots, rostered,
        )
        if why:
            dropped.append({
                "action": action, "employee": employee,
                "shift": _bounded(item.get("shift")), "date": date,
                "why": why, "options": _shift_options(
                    action, employee, date, slots, rostered
                ),
            })
            continue
        operation = {
            "action": action,
            "employee": employee,
            "shift": shift,
            "date": date,
            "reason": _bounded(item.get("reason")),
        }
        if action == OP_SWAP:
            with_employee = _bounded(item.get("with_employee"))
            with_date = _date(item.get("with_date")) or date
            if not with_employee:
                continue
            with_shift, why = _resolve_shift(
                action, with_employee, _bounded(item.get("with_shift")),
                with_date, slots, rostered, fallback=shift,
            )
            if why:
                dropped.append({
                    "action": action, "employee": with_employee,
                    "shift": _bounded(item.get("with_shift")),
                    "date": with_date, "why": why,
                    "options": _shift_options(
                        action, with_employee, with_date, slots, rostered
                    ),
                })
                continue
            operation.update({
                "with_employee": with_employee,
                "with_shift": with_shift,
                "with_date": with_date,
            })
        operations.append(operation)
    return operations, dropped


def _resolve_shift(
    action: str,
    employee: str,
    shift: str,
    date: str,
    slots: set,
    rostered: Dict[tuple, List[str]],
    fallback: str = "",
) -> tuple:
    """The shift an operation means, or why it cannot be carried out.

    Returns `(shift, why)` with `why` empty on success. The three failures
    are kept apart because they are answered differently: a target the
    period does not have is something to state, a person not on that date is
    something to state, and *several* possible shifts is the one case that
    is a question for the manager rather than a report to them (D24).
    """
    on_that_day = rostered.get((employee, date), [])
    if action == OP_REMOVE or (action == OP_SWAP and on_that_day):
        # Removing and swapping both act on a row that already exists, so
        # the roster answers first: it knows which shift the person is
        # actually on, which the grid does not.
        if shift in on_that_day:
            return shift, ""
        if shift:
            # A named shift the period genuinely runs is a real target even
            # when this person is not on it: whether the row exists is a
            # fact the manager can see on the grid, and holding the whole
            # proposal over it would put code in front of a question the
            # name gate below may need to ask first.
            return (shift, "") if (shift, date) in slots else (
                "", "not_assigned" if on_that_day else "no_slot"
            )
        if len(on_that_day) == 1:
            return on_that_day[0], ""
        return "", "ambiguous_shift" if on_that_day else "not_assigned"

    shift = shift or fallback
    if shift:
        # An assignment needs a real slot to land on: `add_assignment` is
        # given a slot id, so a shift the period does not run that day has
        # nothing to write to.
        return (shift, "") if (shift, date) in slots else ("", "no_slot")
    running = [name for name, day in slots if day == date]
    if len(running) == 1:
        # One shift runs that day, so naming it is not a guess -- there was
        # nothing else the manager could have meant.
        return running[0], ""
    return "", "ambiguous_shift" if running else "no_slot"


def _shift_options(
    action: str,
    employee: str,
    date: str,
    slots: set,
    rostered: Dict[tuple, List[str]],
) -> List[str]:
    """The shifts a held question can offer as answers.

    What the person is on, for a removal; what runs that day, for a
    placement. Offering the real candidates is the difference between one
    tap and another sentence — the prompt asks for the same thing and this
    is what code has when the model did not.
    """
    if action == OP_REMOVE:
        return sorted(rostered.get((employee, date), []))
    return sorted({name for name, day in slots if day == date})


def _profile_operations(offered: Any, profile: dict) -> List[dict]:
    """Bound profile edits to the four operations the UI can also perform."""
    if not isinstance(offered, list):
        return []
    employee_names = {
        _bounded(row.get("name")) for row in (profile or {}).get("employees") or []
        if isinstance(row, dict)
    }
    shift_names = {
        _bounded(row.get("name")) for row in (profile or {}).get("shifts") or []
        if isinstance(row, dict)
    }
    result = []
    for raw in offered[:10]:
        if not isinstance(raw, dict):
            continue
        action = _bounded(raw.get("action"))
        target = _bounded(raw.get("target"))
        item = raw.get("item") if isinstance(raw.get("item"), dict) else {}
        item = {
            "name": _bounded(item.get("name")),
            "role": _bounded(item.get("role")),
            "eligible_shifts": [
                _bounded(value) for value in item.get("eligible_shifts") or []
                if _bounded(value)
            ],
            "start_time": _bounded(item.get("start_time")),
            "end_time": _bounded(item.get("end_time")),
            "headcount": item.get("headcount") or 1,
            "is_on_call": bool(item.get("is_on_call")),
        }
        name = item["name"]
        if action not in _PROFILE_OPERATIONS or not name:
            continue
        if action == PROFILE_ADD_EMPLOYEE and name in employee_names:
            continue
        if action == PROFILE_UPDATE_EMPLOYEE and target not in employee_names:
            continue
        if action == PROFILE_ADD_SHIFT and name in shift_names:
            continue
        if action == PROFILE_UPDATE_SHIFT and target not in shift_names:
            continue
        result.append({"action": action, "target": target, "item": item})
    return result


def _constraints(offered: Any) -> List[dict]:
    """Constraints the request implied, to be remembered rather than
    worked around once.

    "דנה חולה ביום חמישי" is both a change and a fact about Thursday. Storing
    the fact is what stops the next schedule from putting her right back.
    """
    if not isinstance(offered, list):
        return []
    constraints = []
    for item in offered:
        if not isinstance(item, dict):
            continue
        employee = _bounded(item.get("employee"))
        date = _date(item.get("date"))
        if not employee or not date:
            continue
        constraints.append({
            "employee": employee,
            "date": date,
            "shift": _bounded(item.get("shift")),
            "reason": _bounded(item.get("reason")),
        })
    return constraints


def _profile_for_model(profile: dict) -> dict:
    profile = profile if isinstance(profile, dict) else {}
    return {
        "workplace": profile.get("workplace") or {},
        "employees": profile.get("employees") or [],
        "shifts": profile.get("shifts") or [],
        "rules": profile.get("rules") or [],
        "rest_policy": profile.get("rest_policy") or "",
        "fairness_policy": profile.get("fairness_policy") or "",
        "conflict_policy": profile.get("conflict_policy") or "",
    }


def _closures_for_model(profile: dict, schedule: dict) -> List[dict]:
    """The period's closure cycle, per weekend, as the model reads it.

    The same rows `bl/scheduler.py` sends, from the same arithmetic, because
    the agent proposing a Saturday swap and the agent building the week must
    not disagree about whose Saturday it is. Empty when the period has no
    readable dates or the unit never anchored a cycle — an invented phase is
    worse than none (D3).
    """
    schedule = schedule if isinstance(schedule, dict) else {}
    try:
        start = datetime.date.fromisoformat(_date(schedule.get("starts_on")))
        end = datetime.date.fromisoformat(_date(schedule.get("ends_on")))
    except (TypeError, ValueError):
        return []
    return rotation.schedule_for_model(profile, start, end)


def _schedule_for_model(schedule: dict) -> dict:
    """The period as the model reads it: slots, and who is on each."""
    schedule = schedule if isinstance(schedule, dict) else {}
    return {
        "starts_on": _date(schedule.get("starts_on")),
        "ends_on": _date(schedule.get("ends_on")),
        "slots": [
            {
                "shift": _bounded(slot.get("shift_name")),
                "date": _date(slot.get("slot_date")),
                "headcount": slot.get("headcount", 1),
            }
            for slot in schedule.get("slots") or []
        ],
        "assignments": [
            {
                "employee": _bounded(row.get("employee")),
                "shift": _bounded(row.get("shift")),
                "date": _date(row.get("date")),
                "reason": _bounded(row.get("reason")),
            }
            for row in schedule.get("assignments") or []
        ],
    }


def _rows(rows: Any, limit: int = 200) -> List[dict]:
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)][-limit:]


def _date(value: Any) -> str:
    """A date as `YYYY-MM-DD`, however the row happened to carry it.

    Repository rows come back as `datetime.date` and model output as strings;
    both are compared against each other here, so both are normalized to the
    one shape rather than trusting them to already match.
    """
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return _bounded(value)


def _json_default(value: Any) -> str:
    """SQL temporal values as JSON strings in raw availability/history rows."""
    if isinstance(value, (datetime.date, datetime.time)):
        return value.isoformat()
    raise TypeError(
        "Object of type %s is not JSON serializable"
        % value.__class__.__name__
    )


def _bounded(value: Any, limit: int = _MAX_TEXT_CHARS) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


__all__ = [
    "ChangeAgent", "CHANGE_RESPONSE_SCHEMA",
    "OP_ASSIGN", "OP_REMOVE", "OP_SWAP",
    "PROFILE_ADD_EMPLOYEE", "PROFILE_UPDATE_EMPLOYEE",
    "PROFILE_ADD_SHIFT", "PROFILE_UPDATE_SHIFT",
]
