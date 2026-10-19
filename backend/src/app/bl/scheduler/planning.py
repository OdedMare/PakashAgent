"""Bound weekly requests by input size as well as staffing demand."""

import json
from typing import List

from app.bl.audit import load_history
from app.bl.scheduler.availability import availability_for_dates, effective_availability
from app.bl.scheduler.bounding import bound_assignments, committed_for_model, merge, required_assignments
from app.bl.scheduler.fairness import load_cost, uneven_load
from app.bl.scheduler.payload import closures_for_model, profile_for_model, slot_for_model
from app.bl.scheduler.quality import no_worse
from app.bl.scheduler.request import SpanRequest
from app.bl.scheduler.request import MAX_HISTORY_ROWS
from app.bl.scheduler.values import bounded, bounded_rows, lines
from app.bl.shared import preferences_for_model
from app.common.errors import AgentError

# A character budget, not a token estimate or a promise about model capacity.
# An oversized single day keeps every rule; output/context failures stay visible.
MAX_SPAN_INPUT_CHARS = 32000


def sized_chunks(profile, chunks, availability=None):
    result = []
    for chunk in chunks:
        by_date = {}
        for slot in chunk:
            by_date.setdefault(slot["slot_date"], []).append(slot)
        current = []
        # ponytail: at most seven dates per chunk; measure whole prompts rather
        # than maintain a second estimate that drifts from the request contract.
        for slots in by_date.values():
            proposed = current + slots
            if current and input_chars(profile, proposed, availability) > MAX_SPAN_INPUT_CHARS:
                result.append(current)
                current = []
            current.extend(slots)
        if current:
            result.append(current)
    return result


def input_chars(profile, slots, availability):
    request = SpanRequest(profile, slots[0]["slot_date"], slots[-1]["slot_date"],
                          slots, availability, [], [])
    return len(json.dumps(request.payload([], "", []), ensure_ascii=False)) + \
        len(json.dumps(request.schema, ensure_ascii=False))


def split_dates(dates):
    middle = len(dates) // 2
    return [dates[:middle], dates[middle:]] if middle else []


class ChunkedRun:
    """State for the legacy chunked generation endpoint."""

    def __init__(self, profile, starts_on, ends_on, slots, availability, history, required):
        self._profile = profile
        self._slots = slots
        self._past = bounded_rows(history, MAX_HISTORY_ROWS)
        self._availability = effective_availability(profile, availability, starts_on, ends_on)
        self._required = required_assignments(required, slots, profile, self._availability)
        self.assignments: List[dict] = list(self._required)
        self.notes: List[str] = []
        self.summaries: List[str] = []

    def payload(self, chunk: List[dict], instructions: str, preferences) -> dict:
        first, last = chunk[0]["slot_date"], chunk[-1]["slot_date"]
        return {
            "profile": profile_for_model(self._profile),
            "preferences": preferences_for_model(preferences),
            "period": {"starts_on": first, "ends_on": last,
                       "slots": [slot_for_model(slot) for slot in chunk]},
            "availability": availability_for_dates(
                self._availability, {slot["slot_date"] for slot in chunk}),
            "closures": closures_for_model(self._profile, first, last),
            "fairness": load_history(
                self._past + self.assignments, self._profile.get("shifts") or [],
                self._profile.get("employees") or []),
            "period_load": load_history(
                self.assignments, self._profile.get("shifts") or [],
                self._profile.get("employees") or [], slots=self._slots),
            "already_scheduled": committed_for_model(self.assignments),
            "required_assignments": committed_for_model(self._required),
            "instructions": bounded(instructions),
        }

    def absorb(self, answer: dict) -> None:
        self.assignments = merge(
            self.assignments,
            bound_assignments(answer.get("assignments"), self._slots, self._profile,
                              self._availability),
        )
        self.notes.extend(lines(answer.get("notes")))
        self.summaries.append(bounded(answer.get("summary")))

    def balance(self, ask, chunk, instructions, preferences) -> None:
        dates = {slot["slot_date"] for slot in chunk}
        span = SpanRequest(self._profile, min(dates), max(dates), chunk,
                           self._availability, self.assignments,
                           [row for row in self._required if row["date"] in dates])
        baseline = span.audit(self.assignments)
        findings = uneven_load(span, self.assignments, baseline, self._past)
        if not findings:
            return
        payload = span.payload(self._past, instructions, preferences)
        payload["repair"] = {"warnings": [item["message"] for item in findings],
                             "instruction": "החזר סידור מלא ומאוזן לתקופה בלבד ושמור על שיבוצי החובה."}
        try:
            second = span.read(ask(payload, schema=span.schema))
            if not second.rejected and no_worse(baseline, span.audit(second.roster)) \
                    and load_cost(span, second.roster, self._past) < load_cost(span, self.assignments, self._past):
                self.assignments = second.roster
                self.notes.extend(lines(second.answer.get("notes")))
                self.summaries[-1] = bounded(second.answer.get("summary"))
        except AgentError:
            self.notes.append("בקשת איזון העומס נכשלה; הטיוטה שנבנתה נשמרה.")
        self.notes.extend(item["message"] for item in
                          uneven_load(span, self.assignments, span.audit(self.assignments), self._past))

    def result(self) -> dict:
        return {"slots": self._slots, "assignments": self.assignments,
                "notes": self.notes, "summary": bounded(" ".join(self.summaries))}
