"""A span request and its audited model answer, including fixed neighbours."""

import datetime
from typing import List

from app.bl.audit import audit, load_history
from app.bl.scheduler.availability import effective_availability
from app.bl.scheduler.bounding import (
    committed_for_model, merge, replace_span, required_assignments,
)
from app.bl.scheduler.candidates import candidates_for, read_span_assignments, span_schema
from app.bl.scheduler.payload import (
    closures_for_model, preferences_for_model, profile_beside_candidates, slot_for_model,
)
from app.bl.scheduler.slots import build_slots
from app.bl.scheduler.fairness import period_load
from app.bl.scheduler.span_audit import span_warnings
from app.bl.scheduler.values import bounded, bounded_rows, parse_date

MAX_HISTORY_ROWS = 400


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
        self.raw_availability = availability
        self.availability = effective_availability(
            self.profile, availability, starts_on, ends_on
        )
        # Audit the entire saved period; the prompt still carries only boundaries.
        self.committed = [dict(row) for row in already_scheduled or [] if isinstance(row, dict)]
        self.required = required_assignments(required, slots, self.profile)
        self.candidates = candidates_for(self.profile, slots, self.availability)
        self.schema = span_schema(slots, self.candidates)
        context_dates = self.dates | {bounded(row.get("date")) for row in self.committed}
        context_dates.discard("")
        self.audit_slots = [slot for slot in build_slots(
            self.profile, min(context_dates), max(context_dates)
        ) if slot["slot_date"] in context_dates]
        self.audit_availability = effective_availability(
            self.profile, availability, min(context_dates), max(context_dates)
        )

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
            "period_load": period_load(self, self._fixed_rows()),
            # Both boundaries protect rest when repairing inside a fixed period;
            # load totals carry the other dates without repeating their reasons.
            "already_scheduled": merge(
                self._boundary_rows(),
                committed_for_model(self.required),
            ),
            "required_assignments": committed_for_model(self.required),
            "instructions": bounded(instructions),
        }

    def _fairness(self, history) -> List[dict]:
        return load_history(
            bounded_rows(history, MAX_HISTORY_ROWS) + self._fixed_rows(),
            self.profile.get("shifts") or [],
            self.profile.get("employees") or [], slots=self.audit_slots,
        )

    def _fixed_rows(self) -> List[dict]:
        fixed = [
            row for row in self.committed
            if bounded(row.get("date")) not in self.dates
        ]
        return fixed + self.required

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

    def audit(self, roster: List[dict]) -> List[dict]:
        return audit(roster, self.profile.get("shifts") or [],
                     self.profile.get("employees") or [],
                     availability=self.audit_availability, profile=self.profile,
                     slots=self.audit_slots)

    def _boundary_rows(self) -> List[dict]:
        neighbours = {(parse_date(day) + datetime.timedelta(days=delta)).isoformat()
                      for day in self.dates for delta in (-1, 1)} - self.dates
        return committed_for_model([row for row in self.committed
                                    if row.get("date") in neighbours])
