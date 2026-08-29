"""The agent that does the assigning, with code answering everything countable.

This is the scheduling half of what `bl/planner.py` already does for
questions: the model runs named tools, the tools answer in pure Python, and
the model decides. What it decides here is who works
([D25](../../../docs/DECISIONS.md#d25--the-agent-assigns-the-tools-count-and-the-engine-is-the-floor-)).

## Why an agent and not the engine

`bl/deterministic_scheduler.py` fills a day by ranking: fewest legal options
first, then the closing group, then the lightest load. It is fast, repeatable
and completely blind to the half of this product that is written in Hebrew —
*"יוסי לא עם רון באותה משמרת"*, *"אחרי סגירה נותנים יום קל"*, *"בערב תמיד
מישהו ותיק"*. Those are rules the manager stated in the interview
([D2](../../../docs/DECISIONS.md#d2--rules-stay-natural-language)) and
preferences they added since
([D21](../../../docs/DECISIONS.md#d21--the-agent-remembers-preferences-and-every-one-of-them-is-visible)),
and a ranking function cannot read one. The agent can, so the agent chooses,
and the engine below it stays the floor for when there is no model.

## What each side is allowed to do

- **Code refuses unusable rows.** A person or shift nobody declared, somebody
  not qualified, a hard constraint, a closure belonging to another group, a
  person already on that slot, a row with no reason (D8). Every refusal goes
  *back to the agent* with its sentence rather than being dropped, so the
  next turn corrects a decision instead of losing it. This is the bound
  `scheduler.py` always applied, not the audit gaining a veto.
- **The agent may take an expensive row** — a sixth consecutive day, hours
  past the ceiling, a short rest, a soft preference overridden — because that
  is exactly the judgment [D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)
  keeps on its side of the line.
- **Code raises the alert either way.** Every cost accepted becomes an alert
  whether or not the agent mentioned it, and so does every slot left short.
  A rule broken quietly is the failure D1's tradeoff was accepted against;
  broken loudly, with the reason attached, it is a decision the manager can
  overrule.

## Alerts are not warnings

`bl/audit.py` recomputes what is true of the stored schedule. An alert says
what happened *while it was being built* and what the manager may want to
decide: a shift nobody legal could take, a rule the agent traded away and
why, a pin that forced everything around it. They ride along on the schedule
like warnings do, and they gate nothing.

## Without a model there is no agent, and the day still gets built

Every failure here — nothing configured, an unreachable server, unusable
JSON, an answer that placed nobody on a day that had legal candidates —
raises `AgentError`. `schedule_service` catches it and runs the deterministic
engine, so the README's promise that the product works with no model
configured is kept by the same fallback that survives an outage.
"""

import datetime
import json
import logging
import time
from typing import Any, Dict, List, Optional

from app.bl import rotation
from app.bl.assignment_tools import (
    TOOL_DESCRIPTIONS,
    TOOL_NAMES,
    DayDraft,
    date_text,
    employees as roster,
    required_rows,
    text,
)
from app.bl.prompts import load
from app.bl.scheduler import build_slots, effective_availability
from app.common.errors import AgentError

_log = logging.getLogger("pakash.assignment")

_MAX_TEXT_CHARS = 4000
# Past assignments read for the fairness tally. Counted here and never sent,
# so this bounds the arithmetic rather than the prompt.
_MAX_HISTORY_ROWS = 400

# How many model turns one date may cost. Three covers the deepest real
# chain -- read the open slots, ask for candidates on the tight ones, answer
# -- plus one repair, and a bound is what stops a model that keeps asking for
# one more tool from spending a manager's afternoon on a Tuesday.
_MAX_TURNS = 4

# How many tools may run in one turn. Bounded because the model names them
# and every name is arithmetic over the whole roster.
_MAX_CALLS_PER_TURN = 6

# What an alert may be. `warning` is something the manager should look at
# before publishing; `info` is the agent explaining a choice it made. Neither
# blocks anything -- see the module docstring.
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"

# Alerts code raises on the agent's behalf, whatever the agent said.
ALERT_UNFILLED = "unfilled_slot"
ALERT_COST = "rule_traded"
ALERT_REJECTED = "rejected_row"

_TOOL_CALL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["tool", "arguments"],
    "properties": {
        "tool": {"type": "string", "enum": list(TOOL_NAMES)},
        "arguments": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "employee": {"type": "string"},
                "shift": {"type": "string"},
            },
        },
    },
}

_ASSIGNMENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["employee", "shift", "reason"],
    "properties": {
        "employee": {"type": "string"},
        "shift": {"type": "string"},
        # Required by the schema as well as checked in code: this is the
        # field the whole decision rests on (D8).
        "reason": {"type": "string"},
    },
}

_ALERT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["message"],
    "properties": {
        "severity": {"type": "string", "enum": [
            SEVERITY_WARNING, SEVERITY_INFO,
        ]},
        "message": {"type": "string"},
        "employee": {"type": "string"},
        "shift": {"type": "string"},
    },
}

ASSIGNMENT_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["done", "tool_calls", "assignments", "alerts", "notes",
                 "summary"],
    "properties": {
        # The agent's own statement that it has decided. Bounded by
        # `_MAX_TURNS` regardless, so a model that never sets it terminates.
        "done": {"type": "boolean"},
        "tool_calls": {
            "type": "array",
            "items": _TOOL_CALL_SCHEMA,
            "maxItems": _MAX_CALLS_PER_TURN,
        },
        "assignments": {"type": "array", "items": _ASSIGNMENT_SCHEMA},
        # What the manager should decide, or know the agent decided. Not
        # operations: there is nothing here `apply()` could read.
        "alerts": {"type": "array", "items": _ALERT_SCHEMA},
        "notes": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
    },
}


class AssignmentAgent:
    """Fill one date by running tools and deciding. Persists nothing."""

    def __init__(self, llm):
        self._llm = llm

    def generate_day(
        self,
        profile: dict,
        day: str,
        availability: Optional[List[dict]] = None,
        history: Optional[List[dict]] = None,
        required_assignments: Optional[List[dict]] = None,
        already_scheduled: Optional[List[dict]] = None,
        shift_names: Optional[List[str]] = None,
        instructions: str = "",
        preferences: Optional[List[dict]] = None,
    ) -> dict:
        """One date, decided by the agent and checked by code.

        The same signature the deterministic engine answers, plus the two
        things only an agent can use: the manager's instructions for this
        build and the standing preferences. Returns the same result shape
        with `alerts` filled in, so `schedule_service` can run either engine
        behind one seam.
        """
        started = time.monotonic()
        errors = rotation.configuration_errors(profile)
        if errors:
            raise AgentError(
                "לא ניתן לשבץ לפני השלמת הגדרת הסבבים והתלתונים: %s."
                % "; ".join(errors)
            )

        slots = build_slots(profile, day, day)
        wanted = {text(name) for name in shift_names or [] if text(name)}
        if wanted:
            slots = [slot for slot in slots if slot["shift_name"] in wanted]
        if not slots:
            return _result(day, started, [], [], [], [], "")

        keys = {(slot["shift_name"], slot["slot_date"]) for slot in slots}
        effective = effective_availability(profile, availability, day, day)
        people = {
            text(row.get("name")): row for row in roster(profile)
        }
        committed = [
            row for row in [
                _row(item) for item in already_scheduled or []
            ]
            if row is not None
            and (row["date"] != day or (row["shift"], row["date"]) not in keys)
        ]
        pins = required_rows(
            required_assignments, slots, people, effective, day
        )
        draft = DayDraft(
            profile, day, slots,
            availability=effective,
            history=_bounded_rows(history, _MAX_HISTORY_ROWS),
            committed=committed + pins,
        )

        results: List[dict] = []
        steps: List[dict] = []
        rejected: List[dict] = []
        alerts: List[dict] = []
        notes: List[str] = []
        summary = ""
        usage: Dict[str, int] = {}
        answered = False
        rows: Any = None
        repair: Optional[dict] = None

        for turn in range(_MAX_TURNS):
            answer = self._ask(_payload(
                profile, draft, slots, day, instructions, preferences,
                results, repair,
            ))
            usage = _add(usage, _usage(answer))
            notes.extend(_lines(answer.get("notes")))
            summary = _bounded(answer.get("summary")) or summary

            calls = _calls(answer.get("tool_calls"))
            rows = answer.get("assignments")
            # Asking and answering are told apart by whether the turn placed
            # anybody, not by `done`: a model that names tools *and* returns
            # an empty roster is still asking, and reading that as a decision
            # would take an empty day for an answer.
            if calls and not rows:
                for call in calls:
                    outcome = draft.run(call["tool"], call["arguments"])
                    results.append(outcome)
                    steps.append({
                        "tool": call["tool"],
                        "arguments": call["arguments"],
                        "ok": bool(outcome.get("ok", True)),
                    })
                continue

            # An answer re-answers the whole date: the previous attempt comes
            # out first so a correction does not land beside what it corrects.
            draft.reset(pins)
            accepted, refused = draft.apply(rows or [])
            answered = True
            rejected = refused
            # Asked for once and read three times: what is still short is
            # what the alerts describe, what a repair turn is told about,
            # and how an empty answer is told apart from an empty day.
            unfilled = draft.unfilled()
            alerts = _alerts(
                answer.get("alerts"), accepted, refused, draft, unfilled
            )
            short = [item for item in unfilled if item["available"]]
            if repair is not None or turn >= _MAX_TURNS - 1:
                # One repair, exactly as `scheduler.py` allows one: a second
                # answer that is still short is the agent saying the day is
                # short, and asking again turns a decision into a loop. What
                # it left stands, and the alerts say what it left.
                break
            if not refused and not short:
                # Nothing left to correct. `done` is the agent's own label
                # and is not required to agree: a full, legal date is a
                # finished date whether or not the model said so.
                break
            # One more turn, told exactly what is wrong with this one. A
            # refused row and a slot the agent left short with people free
            # for it are the two things another turn can actually fix.
            repair = {
                "rejected_rows": [
                    {"row": item["row"], "reason": item["reason"]}
                    for item in refused
                ],
                "still_short": short,
                "instruction": (
                    "החזר מחדש את כל השיבוצים לתאריך הזה. תקן את השורות "
                    "שנדחו, ומלא את המשמרות החסרות או הסבר בהתרעה למה הן "
                    "נשארות חסרות."
                ),
            }

        if not answered:
            raise AgentError("הסוכן לא החזיר שיבוץ לתאריך הזה")
        assignments = draft.assignments()
        if not assignments and any(item["available"] for item in unfilled):
            # The model answered, and answered with nothing, on a date people
            # were free for. Treated as a failure rather than as a decision:
            # a genuinely empty day comes back with an alert saying why.
            raise AgentError("הסוכן לא שיבץ אף אחד לתאריך הזה")

        warnings = draft.warnings()
        if rejected:
            notes.append(
                "%d שיבוצים שהסוכן הציע נדחו בבדיקה ולא נשמרו." % len(rejected)
            )
        metrics = _metrics(
            day, started, len(rows or []), assignments, rejected, warnings,
            usage, steps,
        )
        _log.info(
            "assignment date=%s assigned=%d rejected=%d alerts=%d tools=%d "
            "tokens=%d duration_ms=%d",
            day, len(assignments), len(rejected), len(alerts), len(steps),
            metrics["total_tokens"], metrics["duration_ms"],
        )
        return _result(
            day, started, slots, assignments, notes, alerts, warnings,
            summary, metrics=metrics, steps=steps,
        )

    def _ask(self, payload: dict) -> dict:
        answer = self._llm.complete_json(
            load("assignment"),
            json.dumps(payload, ensure_ascii=False),
            schema=ASSIGNMENT_RESPONSE_SCHEMA,
            flow="assignment",
        )
        if not isinstance(answer, dict):
            raise AgentError("המודל החזיר שיבוץ לא תקין")
        return answer


def _payload(
    profile: dict,
    draft: DayDraft,
    slots: List[dict],
    day: str,
    instructions: str,
    preferences: Optional[List[dict]],
    results: List[dict],
    repair: Optional[dict],
) -> dict:
    """Everything the agent reads, with every number already computed.

    The rules and the preferences travel verbatim, in the manager's own
    words: they are the half of the decision no tool can answer, and turning
    them into flags here would be the structured rule vocabulary D2 refuses.
    """
    payload = {
        "profile": profile if isinstance(profile, dict) else {},
        "preferences": _preferences(preferences),
        "date": day,
        "weekday": slots[0].get("weekday") if slots else "",
        # The day as it stands: what is asked for, what is already on it,
        # what is still short. The agent may re-read it with `open_slots`
        # after it decides, but it never has to spend a turn to start.
        "open_slots": draft.open_slots()["slots"],
        "candidates": [
            draft.candidates(slot["shift_name"]) for slot in slots
        ],
        "workload": draft.workload()["hours"],
        "constraints": draft.availability,
        # Whose closure this date is, worked out rather than derived by a
        # model that cannot check its own phase (D3).
        "closures": rotation.schedule_for_model(
            profile, *_bounds(day)
        ),
        "already_scheduled": [
            row for row in draft.rows if not draft.mine(row)
        ][-60:],
        "tools": [
            {"name": name, "purpose": TOOL_DESCRIPTIONS[name]}
            for name in TOOL_NAMES
        ],
        "results": results[-8:],
        "instructions": _bounded(instructions),
    }
    if repair:
        payload["repair"] = repair
    return payload


def _alerts(
    raw: Any, accepted: List[dict], rejected: List[dict], draft: DayDraft,
    unfilled: List[dict],
) -> List[dict]:
    """What the manager is told about this build.

    Three sources, deliberately merged rather than kept apart: the agent's
    own alerts, one per cost it accepted, and one per slot left short. The
    manager reads a list of things to decide, not a list of who produced
    each line — `source` records that for anyone who cares.
    """
    alerts: List[dict] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        message = _bounded(item.get("message"), 600)
        if not message:
            continue
        severity = text(item.get("severity"))
        alerts.append({
            "code": "agent_note",
            "severity": (
                severity if severity in (SEVERITY_WARNING, SEVERITY_INFO)
                else SEVERITY_WARNING
            ),
            "message": message,
            "employee": text(item.get("employee")),
            "shift": text(item.get("shift")),
            "date": draft.day,
            "source": "agent",
        })

    for row in accepted:
        for cost in row.get("costs") or []:
            alerts.append({
                "code": ALERT_COST,
                "severity": SEVERITY_WARNING,
                # The agent's own reason is attached rather than replaced:
                # "why did it do that" is the first thing the manager asks,
                # and the answer was already written when the row was made.
                "message": "%s (הסוכן שיבץ בכל זאת: %s)" % (
                    cost["message"], row["reason"],
                ),
                "employee": row["employee"],
                "shift": row["shift"],
                "date": row["date"],
                "source": "code",
            })

    for slot in unfilled:
        alerts.append({
            "code": ALERT_UNFILLED,
            "severity": SEVERITY_WARNING,
            "message": (
                "%s ב-%s חסרה %d אנשים; %s"
                % (
                    slot["shift"], slot["date"], slot["missing"],
                    "פנויים לכך: %s" % "‏, ".join(slot["available"])
                    if slot["available"]
                    else "אין אף אחד שיכול לקחת אותה בלי לשבור אילוץ קשיח",
                )
            ),
            "employee": "",
            "shift": slot["shift"],
            "date": slot["date"],
            "source": "code",
        })

    for item in rejected:
        alerts.append({
            "code": ALERT_REJECTED,
            "severity": SEVERITY_INFO,
            "message": "שיבוץ שהסוכן הציע נדחה: %s" % item["reason"],
            "employee": text((item.get("row") or {}).get("employee")),
            "shift": text((item.get("row") or {}).get("shift")),
            "date": draft.day,
            "source": "code",
        })
    return _unique_alerts(alerts)


def _unique_alerts(alerts: List[dict]) -> List[dict]:
    result, seen = [], set()
    for alert in alerts:
        key = (
            alert["code"], alert["employee"], alert["shift"], alert["date"],
            alert["message"],
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(alert)
    return result


def _result(
    day: str,
    started: float,
    slots: List[dict],
    assignments: List[dict],
    notes: List[str],
    alerts: List[dict],
    warnings: List[dict],
    summary: str,
    metrics: Optional[dict] = None,
    steps: Optional[List[dict]] = None,
) -> dict:
    return {
        "slots": slots,
        "assignments": [
            {key: row[key] for key in ("employee", "shift", "date", "reason")}
            for row in assignments
        ],
        "notes": notes,
        "summary": summary or "הסוכן שיבץ את התאריך לפי הכללים והעומסים.",
        "alerts": alerts,
        "warnings": warnings,
        # What the agent actually ran, for the same reason `planner.py`
        # returns it: an answer whose checks are invisible is one the manager
        # has to take on faith.
        "steps": steps or [],
        "metrics": metrics or {
            "date": day,
            "status": "skipped",
            "duration_ms": int((time.monotonic() - started) * 1000),
            "returned": 0, "accepted": 0, "rejected": 0, "warnings": 0,
            "repaired": False, "prompt_tokens": 0, "completion_tokens": 0,
            "total_tokens": 0, "engine": "agent",
        },
    }


def _metrics(
    day: str,
    started: float,
    returned: int,
    assignments: List[dict],
    rejected: List[dict],
    warnings: List[dict],
    usage: Dict[str, int],
    steps: List[dict],
) -> dict:
    return {
        "date": day,
        "status": "complete",
        "duration_ms": int((time.monotonic() - started) * 1000),
        "returned": returned,
        "accepted": len(assignments),
        "rejected": len(rejected),
        "warnings": len(warnings),
        "repaired": bool(rejected),
        "tool_calls": len(steps),
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or 0),
        "engine": "agent",
    }


def _calls(value: Any) -> List[dict]:
    calls = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        name = text(item.get("tool"))
        if name not in TOOL_NAMES:
            continue
        arguments = item.get("arguments")
        calls.append({
            "tool": name,
            "arguments": arguments if isinstance(arguments, dict) else {},
        })
    return calls[:_MAX_CALLS_PER_TURN]


def _row(raw: Any) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    employee = text(raw.get("employee"))
    shift = text(raw.get("shift") or raw.get("shift_name"))
    date = date_text(raw.get("date") or raw.get("slot_date"))
    if not employee or not shift or not date:
        return None
    return {
        "employee": employee, "shift": shift, "date": date,
        "reason": text(raw.get("reason")),
    }


def _preferences(preferences: Any) -> List[dict]:
    """Standing preferences as reported speech. They authorise nothing (D21)."""
    shaped = []
    for row in preferences or []:
        if not isinstance(row, dict):
            continue
        shaped.append({
            "kind": _bounded(row.get("kind")),
            "subject": _bounded(row.get("subject")),
            "text": _bounded(row.get("text")),
        })
    return shaped[:40]


def _bounds(day: str) -> tuple:
    try:
        date = datetime.date.fromisoformat(text(day))
    except (TypeError, ValueError):
        today = datetime.date.today()
        return today, today
    return date, date


def _add(totals: Dict[str, int], usage: dict) -> Dict[str, int]:
    keys = ("prompt_tokens", "completion_tokens", "total_tokens")
    return {
        key: int(totals.get(key) or 0) + int(usage.get(key) or 0)
        for key in keys
    }


def _usage(answer: Any) -> dict:
    usage = answer.get("_usage") if isinstance(answer, dict) else None
    return usage if isinstance(usage, dict) else {}


def _bounded_rows(rows: Any, limit: int) -> List[dict]:
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)][-limit:]


def _lines(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [line for line in (_bounded(item) for item in value) if line]


def _bounded(value: Any, limit: int = _MAX_TEXT_CHARS) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


__all__ = [
    "ALERT_COST",
    "ALERT_REJECTED",
    "ALERT_UNFILLED",
    "ASSIGNMENT_RESPONSE_SCHEMA",
    "AssignmentAgent",
    "SEVERITY_INFO",
    "SEVERITY_WARNING",
]
