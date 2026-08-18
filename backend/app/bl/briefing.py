"""The agent speaking first — what it noticed, without being asked.

Every other model call in this package answers something the manager said.
This one is the agent's own turn: it reads the current state, the audit's
arithmetic and the pending requests, and says what it makes of them.

**It writes nothing, and it proposes nothing that lands.** A briefing item may
carry a `suggestion`, but a suggestion is *text the manager may choose to
send* — it is not an operation, not a queued change, and there is no path
from here to `apply`. That is deliberate: under
[D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-) the
agent decides and under
[D8](../../../docs/DECISIONS.md#d8--two-reasons-both-required) every change
carries the manager's reason, so an agent that acted on its own conclusion
would reverse both at once. Being proactive is about *initiating the
conversation*, not about skipping it —
[D15](../../../docs/DECISIONS.md#d15--the-agent-speaks-first-but-still-never-writes)
is where that line is drawn.

The numbers are not the model's. `warnings` and `fairness` arrive already
computed by `audit.py` and are handed over as facts to reason about, for the
same reason the audit exists at all: arithmetic over a roster is what a model
gets subtly wrong in a way that looks exactly like getting it right. The model
is asked what the numbers *mean together*, which is the part code cannot do.

Stateless, like `Scheduler` and `ChangeAgent`. `schedule_service.py` gathers
the state and stores what was said.
"""

import json
from typing import Any, Dict, List, Optional

from app.bl.prompts import load
from app.common.errors import AgentError

_MAX_TEXT_CHARS = 4000
# Four is a screenful the manager actually reads. A briefing that lists
# everything is a report, and a report is what they open the calendar for.
_MAX_ITEMS = 4

# Why the agent is speaking. Not free text: each one changes what is worth
# saying, and the prompt branches on them by name.
TRIGGER_OPENED = "opened"
TRIGGER_CHANGED = "changed"
TRIGGER_PUBLISHING = "publishing"
TRIGGER_PERIODIC = "periodic"
_TRIGGERS = (
    TRIGGER_OPENED, TRIGGER_CHANGED, TRIGGER_PUBLISHING, TRIGGER_PERIODIC,
)

# What an observation is about. Presentation, like `audit.SEVERITY_*` --
# the UI picks an icon from it and nothing branches on it in code.
KIND_RISK = "risk"
KIND_FAIRNESS = "fairness"
KIND_GAP = "gap"
KIND_REQUEST = "request"
KIND_PATTERN = "pattern"
_KINDS = (KIND_RISK, KIND_FAIRNESS, KIND_GAP, KIND_REQUEST, KIND_PATTERN)

_ITEM_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["text", "kind", "suggestion"],
    "properties": {
        "text": {"type": "string"},
        "kind": {"type": "string", "enum": list(_KINDS)},
        # The sentence the manager could send to act on this. Empty when
        # there is nothing to do -- an observation is allowed to just be one.
        "suggestion": {"type": "string"},
    },
}

BRIEFING_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["headline", "items", "quiet"],
    "properties": {
        "headline": {"type": "string"},
        "items": {
            "type": "array", "items": _ITEM_SCHEMA, "maxItems": _MAX_ITEMS,
        },
        # The agent's own judgment that nothing is worth saying. Honest
        # silence is the feature: an agent that finds something urgent every
        # time gets tuned out, and being tuned out is the only real failure
        # mode for a thing that speaks unprompted.
        "quiet": {"type": "boolean"},
    },
}


class BriefingAgent:
    """What the agent says when nobody asked it anything."""

    def __init__(self, llm):
        self._llm = llm

    def brief(
        self,
        trigger: str,
        profile: dict,
        schedule: Optional[dict] = None,
        warnings: Optional[List[dict]] = None,
        fairness: Optional[dict] = None,
        requests: Optional[List[dict]] = None,
        availability: Optional[List[dict]] = None,
        changes: Optional[List[dict]] = None,
        last_said: Optional[List[str]] = None,
    ) -> dict:
        """One briefing. Persists nothing and changes nothing."""
        payload = {
            "trigger": _trigger(trigger),
            "profile": _profile_for_model(profile),
            "schedule": _schedule_for_model(schedule),
            # Handed over as computed facts, not as something to check.
            "warnings": _rows(warnings, 60),
            "fairness": fairness if isinstance(fairness, dict) else {},
            "requests": _rows(requests, 40),
            "availability": _rows(availability, 120),
            "changes": _rows(changes, 60),
            "last_said": [_bounded(line) for line in (last_said or [])][-8:],
        }
        return _briefing(self._ask(payload))

    def _ask(self, payload: dict) -> dict:
        answer = self._llm.complete_json(
            load("briefing"),
            json.dumps(payload, ensure_ascii=False),
            schema=BRIEFING_RESPONSE_SCHEMA,
        )
        if not isinstance(answer, dict):
            raise AgentError("המודל החזיר תדריך לא תקין")
        return answer


def _briefing(answer: dict) -> dict:
    """The model's turn, bounded, with `quiet` decided in code.

    `quiet` is not taken from the model alone: a briefing with no items is
    quiet whatever it labelled itself, and one with items is not quiet no
    matter what it claimed. The two disagreeing would render as an all-clear
    banner sitting above a list of problems.
    """
    items = _items(answer.get("items"))
    return {
        "headline": _bounded(answer.get("headline")),
        "items": items,
        "quiet": not items,
    }


def _items(offered: Any) -> List[dict]:
    """Observations, bounded and with an unknown `kind` normalized.

    An item with no text is dropped: it would render as an empty row the
    manager cannot act on or dismiss.
    """
    if not isinstance(offered, list):
        return []
    items = []
    for item in offered[:_MAX_ITEMS]:
        if not isinstance(item, dict):
            continue
        text = _bounded(item.get("text"))
        if not text:
            continue
        kind = _bounded(item.get("kind"))
        items.append({
            "text": text,
            "kind": kind if kind in _KINDS else KIND_RISK,
            "suggestion": _bounded(item.get("suggestion")),
        })
    return items


def _trigger(value: Any) -> str:
    """The named trigger, defaulting to `opened`.

    An unrecognized trigger becomes the mildest one rather than raising: this
    call is decoration on top of a screen that must render regardless, so an
    unknown caller gets a general briefing instead of an error where the
    manager expected their calendar.
    """
    text = _bounded(value)
    return text if text in _TRIGGERS else TRIGGER_OPENED


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


def _schedule_for_model(schedule: Optional[dict]) -> Optional[dict]:
    """The period as the model reads it, or None when none has been built.

    Null rather than an empty shape: "there is no schedule yet" is itself the
    most useful thing to say to a manager who just opened an empty control
    room, and an empty slot list reads as a built period with nothing in it.
    """
    if not isinstance(schedule, dict) or not schedule:
        return None
    return {
        "status": _bounded(schedule.get("status")),
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
            }
            for row in schedule.get("assignments") or []
        ],
    }


def _rows(rows: Any, limit: int = 200) -> List[dict]:
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)][-limit:]


def _date(value: Any) -> str:
    """Dates arrive as `datetime.date` from SQL and as strings from the model."""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return _bounded(value)


def _bounded(value: Any, limit: int = _MAX_TEXT_CHARS) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


__all__ = [
    "BriefingAgent", "BRIEFING_RESPONSE_SCHEMA",
    "TRIGGER_OPENED", "TRIGGER_CHANGED", "TRIGGER_PUBLISHING",
    "TRIGGER_PERIODIC",
]
