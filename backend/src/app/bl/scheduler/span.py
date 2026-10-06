"""Generating one contiguous span of dates: ask, verify, repair at most once.

A range job calls this once per span, in order — one date at a time in day
mode, up to a week in week mode. Widening the span does not weaken any check:
the candidate lists, the response schema, the rejection rules and the audit
are all built over whatever dates the call covers. What it changes is the
granularity of the repair and the price of a failure.
"""

import logging
import json
import time
from typing import Callable, List, Optional

from app.bl.scheduler.request import MAX_HISTORY_ROWS, SpanAttempt, SpanRequest
from app.bl.scheduler.slots import build_slots
from app.bl.scheduler.span_audit import add_usage, metrics, usage_of
from app.bl.scheduler.quality import no_worse, quality
from app.bl.scheduler.repair import repair_request, repaired_attempt
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
        measured = dict(model_calls=0, failed_calls=0, prompt_chars=0, schema_chars=0, reply_chars=0, usage={})
        try:
            first = span.read(self._call(payload, span.schema, measured))
        except AgentError as exc:
            exc.generation_metrics = metrics(starts_on, started, "failed", through=ends_on,
                                            usage=measured.pop("usage"))
            exc.generation_metrics.update(measured)
            raise
        return self._complete(span, first, history, instructions, preferences, measured, started)

    def _complete(self, span, first, history, instructions, preferences, measured, started):
        chosen, rejected = first, list(first.rejected)
        baseline = span.audit(first.roster)
        repair_error, repair_dates = "", []
        if first.problems:
            request, payload = repair_request(span, first, history, instructions, preferences)
            repair_dates = sorted(request.dates)
            try:
                answer = self._call(payload, request.schema, measured)
                second = repaired_attempt(span, request, answer, first)
                if len(second.rejected) <= len(first.rejected) and no_worse(baseline, second.warnings):
                    chosen = second
                rejected.extend(second.rejected)
            except AgentError as exc:
                repair_error = bounded(str(exc))
                _log.warning("schedule repair failed span=%s..%s: %s",
                             request.starts_on, request.ends_on, exc)
        improved = chosen is not first and (len(chosen.rejected) < len(first.rejected)
                                            or not no_worse(chosen.warnings, baseline))
        measured.update(repair_dates=repair_dates, repair_error=repair_error,
                        repair_improved=improved,
                        quality_before=quality(first.roster, span.audit_slots, span.profile, baseline))
        warnings = baseline if chosen is first else chosen.warnings
        return self._finish(span, chosen, rejected, bool(first.problems), measured, started, warnings)

    def _call(self, payload, schema, measured):
        measured["model_calls"] += 1
        measured["prompt_chars"] += len(json.dumps(payload, ensure_ascii=False))
        measured["schema_chars"] += len(json.dumps(schema, ensure_ascii=False))
        try:
            answer = self._ask(payload, schema=schema)
        except AgentError as exc:
            measured["failed_calls"] += 1
            measured["usage"] = add_usage(measured["usage"], getattr(exc, "usage", {}))
            raise
        measured["usage"] = add_usage(measured["usage"], usage_of(answer))
        measured["reply_chars"] += len(json.dumps(answer, ensure_ascii=False))
        return answer

    def _finish(
        self, span: SpanRequest, chosen: SpanAttempt, rejected: List[dict],
        repaired: bool, measured: dict, started: float, warnings: List[dict],
    ) -> dict:
        rows = [row for row in chosen.roster if row.get("date") in span.dates]
        notes = lines(chosen.answer.get("notes"))
        if measured["repair_error"]:
            notes.append("בקשת התיקון נכשלה. הטיוטה שנבדקה נשמרה עם האזהרות שנותרו.")
        if rejected:
            notes.append(
                "%d שיבוצים לא תקינים שהחזיר המודל לא נשמרו." % len(rejected)
            )
        result_metrics = metrics(
            span.starts_on, started, status="complete", through=span.ends_on,
            returned=len(chosen.answer.get("assignments") or []),
            accepted=len(rows), rejected=len(rejected),
            warnings=len(warnings), repaired=repaired, usage=measured.pop("usage"),
        )
        result_metrics.update(measured)
        result_metrics["quality"] = quality(chosen.roster, span.audit_slots, span.profile, warnings)
        _log_span(span, result_metrics)
        return {
            "slots": span.slots,
            "assignments": rows,
            "notes": notes,
            "summary": bounded(chosen.answer.get("summary")),
            "warnings": warnings,
            "metrics": result_metrics,
        }


def _log_span(span: SpanRequest, result: dict) -> None:
    _log.info(
        "schedule span=%s..%s status=%s assignments=%d rejected=%d "
        "warnings=%d repaired=%s tokens=%d duration_ms=%d calls=%d coverage=%.1f",
        span.starts_on, span.ends_on, result["status"], result["accepted"],
        result["rejected"], result["warnings"], result["repaired"],
        result["total_tokens"], result["duration_ms"], result["model_calls"],
        result["quality"]["coverage"]["percent"],
    )
