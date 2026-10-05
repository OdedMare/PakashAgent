"""Generating one contiguous span of dates: ask, verify, repair at most once.

A range job calls this once per span, in order — one date at a time in day
mode, up to a week in week mode. Widening the span does not weaken any check:
the candidate lists, the response schema, the rejection rules and the audit
are all built over whatever dates the call covers. What it changes is the
granularity of the repair and the price of a failure.
"""

import logging
import time
from typing import Callable, List, Optional

from app.bl.audit import load_history
from app.bl.scheduler.availability import effective_availability
from app.bl.scheduler.bounding import (
    committed_for_model, merge, previous_day, replace_span,
    required_assignments,
)
from app.bl.scheduler.candidates import (
    candidates_for, read_span_assignments, span_schema,
)
from app.bl.scheduler.payload import (
    closures_for_model, preferences_for_model, profile_beside_candidates,
    slot_for_model,
)
from app.bl.scheduler.slots import build_slots
from app.bl.scheduler.span_audit import (
    add_usage, audit_for_span, metrics, span_warnings, usage_of,
)
from app.bl.scheduler.values import bounded, bounded_rows, lines

# Past assignments read for the fairness tally. They are counted here and
# never sent, so this bounds the arithmetic rather than the prompt.
MAX_HISTORY_ROWS = 400

_REPAIR_INSTRUCTION = (
    "החזר מחדש את כל השיבוצים לתאריכים האלה בלבד. "
    "תקן את הבעיות המפורטות ואל תשנה תאריכים קודמים."
)

_log = logging.getLogger("pakash.scheduler")


class SpanAttempt:
    """One model answer for a span, read and audited."""

    def __init__(self, answer: dict, roster: List[dict], rejected: List[dict],
                 warnings: List[dict]):
        self.answer = answer
        self.roster = roster
        self.rejected = rejected
        self.warnings = warnings

    @property
    def problems(self) -> int:
        return len(self.rejected) + len(self.warnings)


class SpanRequest:
    """Everything one span's calls are built from, computed once."""

    def __init__(
        self, profile: dict, starts_on: str, ends_on: str, slots: List[dict],
        availability, already_scheduled, required,
    ):
        self.profile = profile if isinstance(profile, dict) else {}
        self.starts_on, self.ends_on = starts_on, ends_on
        self.slots = slots
        self.dates = {slot["slot_date"] for slot in slots}
        self.availability = effective_availability(
            self.profile, availability, starts_on, ends_on
        )
        self.committed = bounded_rows(already_scheduled)
        self.required = required_assignments(required, slots, self.profile)
        self.candidates = candidates_for(self.profile, slots, self.availability)
        self.schema = span_schema(slots, self.candidates)

    def payload(self, history, instructions: str, preferences) -> dict:
        return {
            "profile": profile_beside_candidates(self.profile),
            "preferences": preferences_for_model(preferences),
            "period": {
                "starts_on": self.starts_on,
                "ends_on": self.ends_on,
                "slots": [
                    slot_for_model(slot, index, self.candidates)
                    for index, slot in enumerate(self.slots, 1)
                ],
            },
            "candidate_employees": self.candidates["employees"],
            "availability": self.availability,
            "closures": closures_for_model(
                self.profile, self.starts_on, self.ends_on
            ),
            "fairness": self._fairness(history),
            # Only the day before the span is needed verbatim, for
            # cross-midnight rest; load totals carry the rest of the range.
            "already_scheduled": merge(
                previous_day(self.committed, self.starts_on),
                committed_for_model(self.required),
            ),
            "required_assignments": committed_for_model(self.required),
            "instructions": bounded(instructions),
        }

    def _fairness(self, history) -> List[dict]:
        earlier = [
            row for row in self.committed
            if bounded(row.get("date")) < self.starts_on
        ]
        return load_history(
            bounded_rows(history, MAX_HISTORY_ROWS) + earlier + self.required,
            self.profile.get("shifts") or [],
            self.profile.get("employees") or [],
        )

    def read(self, answer: dict) -> SpanAttempt:
        accepted, rejected = read_span_assignments(
            answer.get("assignments"), self.slots, self.profile,
            self.candidates, self.availability,
        )
        roster = replace_span(self.committed, self.required + accepted, self.dates)
        warnings = span_warnings(
            roster, self.slots, self.profile, self.availability,
            self.candidates, self.dates,
        )
        return SpanAttempt(answer, roster, rejected, warnings)


class SpanGenerator:
    def __init__(self, ask: Callable):
        self._ask = ask

    def generate(
        self,
        profile: dict,
        starts_on: str,
        ends_on: str,
        availability: Optional[List[dict]] = None,
        history: Optional[List[dict]] = None,
        instructions: str = "",
        required_assignments: Optional[List[dict]] = None,
        already_scheduled: Optional[List[dict]] = None,
        preferences: Optional[List[dict]] = None,
    ) -> dict:
        started = time.monotonic()
        slots = build_slots(profile, starts_on, ends_on)
        if not slots:
            return {
                "slots": [], "assignments": [], "notes": [], "summary": "",
                "metrics": metrics(
                    starts_on, started, status="skipped", through=ends_on
                ),
            }
        span = SpanRequest(
            profile, starts_on, ends_on, slots,
            availability, already_scheduled, required_assignments,
        )
        payload = span.payload(history, instructions, preferences)
        first = span.read(self._ask(payload, schema=span.schema))
        chosen, rejected, usage = first, list(first.rejected), usage_of(first.answer)
        if first.problems:
            second = span.read(self._ask(_repair(payload, first), schema=span.schema))
            usage = add_usage(usage, usage_of(second.answer))
            # A repair is another model answer, not proof of improvement:
            # keep the first when the second has more concrete problems.
            if second.problems <= first.problems:
                chosen = second
            rejected.extend(second.rejected)
        return self._finish(
            span, chosen, rejected, bool(first.problems), usage, started
        )

    def _finish(
        self, span: SpanRequest, chosen: SpanAttempt, rejected: List[dict],
        repaired: bool, usage: dict, started: float,
    ) -> dict:
        rows = [row for row in chosen.roster if row.get("date") in span.dates]
        warnings = audit_for_span(
            chosen.roster, span.slots, span.profile, span.availability, span.dates
        )
        notes = lines(chosen.answer.get("notes"))
        if rejected:
            notes.append(
                "%d שיבוצים לא תקינים שהחזיר המודל לא נשמרו." % len(rejected)
            )
        result_metrics = metrics(
            span.starts_on, started, status="complete", through=span.ends_on,
            returned=len(chosen.answer.get("assignments") or []),
            accepted=len(rows), rejected=len(rejected),
            warnings=len(warnings), repaired=repaired, usage=usage,
        )
        _log_span(span, result_metrics)
        return {
            "slots": span.slots,
            "assignments": rows,
            "notes": notes,
            "summary": bounded(chosen.answer.get("summary")),
            "warnings": warnings,
            "metrics": result_metrics,
        }


def _repair(payload: dict, attempt: SpanAttempt) -> dict:
    repair = dict(payload)
    repair["repair"] = {
        "rejected_rows": attempt.rejected,
        "warnings": [item["message"] for item in attempt.warnings],
        "instruction": _REPAIR_INSTRUCTION,
    }
    return repair


def _log_span(span: SpanRequest, result: dict) -> None:
    _log.info(
        "schedule span=%s..%s status=%s assignments=%d rejected=%d "
        "warnings=%d repaired=%s tokens=%d duration_ms=%d",
        span.starts_on, span.ends_on, result["status"], result["accepted"],
        result["rejected"], result["warnings"], result["repaired"],
        result["total_tokens"], result["duration_ms"],
    )
