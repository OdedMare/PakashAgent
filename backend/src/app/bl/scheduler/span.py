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

from app.bl.scheduler.request import MAX_HISTORY_ROWS, SpanAttempt, SpanRequest
from app.bl.scheduler.slots import build_slots
from app.bl.scheduler.span_audit import add_usage, audit_for_span, metrics, usage_of
from app.bl.scheduler.values import bounded, lines
from app.common.errors.errors import AgentError

_log = logging.getLogger("pakash.scheduler")


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
