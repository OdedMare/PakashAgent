"""`Scheduler`: the model call that assigns people into the grid."""

import json
from typing import List, Optional

from app.bl.audit import load_history
from app.bl.prompts import load
from app.bl.scheduler.availability import (
    availability_for_dates, effective_availability,
)
from app.bl.scheduler.bounding import (
    bound_assignments, committed_for_model, merge, required_assignments,
)
from app.bl.scheduler.payload import (
    SCHEDULE_RESPONSE_SCHEMA, closures_for_model, preferences_for_model,
    profile_for_model, slot_for_model,
)
from app.bl.scheduler.slots import build_slots, chunks
from app.bl.scheduler.span import MAX_HISTORY_ROWS, SpanGenerator
from app.bl.scheduler.request import SpanRequest
from app.bl.scheduler.fairness import load_cost, uneven_load
from app.bl.scheduler.quality import no_worse
from app.bl.scheduler.values import bounded, bounded_rows, lines
from app.common.errors.errors import AgentError, ModelOutputError


class Scheduler:
    """Build one period's assignments from the workplace profile."""

    def __init__(self, llm):
        self._llm = llm
        self._spans = SpanGenerator(self._ask)

    def generate(
        self,
        profile: dict,
        starts_on: str,
        ends_on: str,
        availability: Optional[List[dict]] = None,
        history: Optional[List[dict]] = None,
        instructions: str = "",
        required_assignments: Optional[List[dict]] = None,
        preferences: Optional[List[dict]] = None,
    ) -> dict:
        """Slots for the period plus the model's assignments, chunk by chunk.

        The legacy one-shot path, kept for API consumers. Chunks are NOT
        independent: each sees what earlier ones decided, and its fairness
        tally is recomputed over the real history *plus* this run, so week two
        sees week one's nights as nights. Nothing is persisted here.
        """
        slots = build_slots(profile, starts_on, ends_on)
        if not slots:
            raise AgentError("לא ניתן לבנות סידור: לא הוגדרו משמרות לתקופה הזו")
        run = _ChunkedRun(profile, starts_on, ends_on, slots, availability,
                          history, required_assignments)
        for chunk in chunks(slots):
            answer = self._ask(run.payload(chunk, instructions, preferences))
            run.absorb(answer)
            run.balance(self._ask, chunk, instructions, preferences)
        return run.result()

    def generate_day(self, profile: dict, day: str, **kwargs) -> dict:
        """Generate and verify exactly one date."""
        return self.generate_span(profile, day, day, **kwargs)

    def generate_verified(self, profile, starts_on, ends_on, availability=None,
                          history=None, instructions="", required_assignments=None,
                          preferences=None, already_scheduled=None):
        """The verified span path for chat periods, bounded to one week per call."""
        from app.bl.scheduler.slots import plan_spans, MODE_WEEK
        slots = build_slots(profile, starts_on, ends_on)
        if not slots:
            raise AgentError("לא הוגדרו משמרות לתאריכים שנבחרו")
        committed = list(already_scheduled or [])
        result = dict(slots=slots, assignments=[], warnings=[], notes=[], summary="", metrics=[])
        for span in plan_spans(profile, starts_on, ends_on, MODE_WEEK, availability):
            pins = [row for row in required_assignments or [] if row["date"] in span["dates"]]
            generated = self.generate_span(profile, span["date"], span["through"],
                availability=availability, history=history, instructions=instructions,
                required_assignments=pins, preferences=preferences, already_scheduled=committed)
            result["assignments"].extend(generated["assignments"])
            committed = [row for row in committed if row.get("date") not in span["dates"]]
            committed.extend(generated["assignments"])
            result["warnings"].extend(generated.get("warnings") or [])
            result["notes"].extend(generated.get("notes") or [])
            result["metrics"].append(generated.get("metrics") or {})
        from app.bl.scheduler.request import SpanRequest
        from app.bl.scheduler.quality import combine_metrics, quality
        request = SpanRequest(profile, starts_on, ends_on, slots, availability,
                              already_scheduled, required_assignments)
        result["warnings"] = request.audit(committed)
        result["quality"] = quality(committed, request.audit_slots, profile, result["warnings"])
        result["performance"] = {}
        for measured in result["metrics"]:
            result["performance"] = combine_metrics(result["performance"], measured)
        return result

    def generate_span(
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
        split_on_failure: bool = True,
    ) -> dict:
        """Generate and verify one contiguous stretch of dates. See `span.py`."""
        options = dict(availability=availability, history=history, instructions=instructions,
                       required_assignments=required_assignments,
                       already_scheduled=already_scheduled, preferences=preferences)
        try:
            return self._spans.generate(profile, starts_on, ends_on, **options)
        except ModelOutputError as exc:
            if not split_on_failure:
                raise
            from app.bl.scheduler.recovery import generate_split
            return generate_split(self, profile, starts_on, ends_on, options, exc)

    def _ask(self, payload: dict, schema: Optional[dict] = None) -> dict:
        answer = self._llm.complete_json(
            load("scheduler"),
            json.dumps(payload, ensure_ascii=False),
            schema=schema or SCHEDULE_RESPONSE_SCHEMA,
            flow="scheduler",
        )
        if not isinstance(answer, dict):
            raise ModelOutputError("המודל החזיר סידור לא תקין")
        return answer


class _ChunkedRun:
    """The running state of one legacy chunked generation."""

    def __init__(self, profile, starts_on, ends_on, slots, availability,
                 history, required):
        self._profile = profile
        self._slots = slots
        self._past = bounded_rows(history, MAX_HISTORY_ROWS)
        self._availability = effective_availability(
            profile, availability, starts_on, ends_on
        )
        self._required = required_assignments(required, slots, profile)
        self.assignments: List[dict] = list(self._required)
        self.notes: List[str] = []
        self.summaries: List[str] = []

    def payload(self, chunk: List[dict], instructions: str, preferences) -> dict:
        first, last = chunk[0]["slot_date"], chunk[-1]["slot_date"]
        return {
            "profile": profile_for_model(self._profile),
            "preferences": preferences_for_model(preferences),
            "period": {
                "starts_on": first,
                "ends_on": last,
                "slots": [slot_for_model(slot) for slot in chunk],
            },
            "availability": availability_for_dates(
                self._availability, {slot["slot_date"] for slot in chunk}
            ),
            "closures": closures_for_model(self._profile, first, last),
            # Counted rather than handed over raw (D3): several hundred rows
            # were roughly 60% of this payload.
            "fairness": load_history(
                self._past + self.assignments,
                (self._profile or {}).get("shifts") or [],
                (self._profile or {}).get("employees") or [],
            ),
            "period_load": load_history(
                self.assignments, self._profile.get("shifts") or [],
                self._profile.get("employees") or [], slots=self._slots,
            ),
            "already_scheduled": committed_for_model(self.assignments),
            "required_assignments": committed_for_model(self._required),
            "instructions": bounded(instructions),
        }

    def absorb(self, answer: dict) -> None:
        # Bounded against the whole grid, not just this chunk: a date from
        # next week names a real slot and is a valid decision for the period.
        self.assignments = merge(
            self.assignments,
            bound_assignments(
                answer.get("assignments"), self._slots, self._profile,
                self._availability,
            ),
        )
        self.notes.extend(lines(answer.get("notes")))
        summary = bounded(answer.get("summary"))
        if summary:
            self.summaries.append(summary)

    def balance(self, ask, chunk, instructions, preferences) -> None:
        dates = {slot["slot_date"] for slot in chunk}
        span = SpanRequest(self._profile, min(dates), max(dates), chunk,
                           self._availability, self.assignments,
                           [row for row in self._required if row["date"] in dates])
        baseline = span.audit(self.assignments)
        findings = uneven_load(span, self.assignments, baseline)
        if not findings:
            return
        payload = span.payload(self._past, instructions, preferences)
        payload["repair"] = {"warnings": [item["message"] for item in findings],
                             "instruction": "החזר סידור מלא ומאוזן לתקופה בלבד ושמור על שיבוצי החובה."}
        try:
            second = span.read(ask(payload, schema=span.schema))
            if not second.rejected and no_worse(baseline, span.audit(second.roster)) \
                    and load_cost(span, second.roster) < load_cost(span, self.assignments):
                self.assignments = second.roster
                self.notes.extend(lines(second.answer.get("notes")))
        except AgentError:
            self.notes.append("בקשת איזון העומס נכשלה; הטיוטה שנבנתה נשמרה.")
        self.notes.extend(item["message"] for item in
                          uneven_load(span, self.assignments, span.audit(self.assignments)))

    def result(self) -> dict:
        return {
            "slots": self._slots,
            "assignments": self.assignments,
            "notes": self.notes,
            # Several chunks produce several summaries; joining them is
            # honest, inventing one sentence over them is the model's job.
            "summary": bounded(" ".join(self.summaries)),
        }
