"""The model's turn, bounded, with both gates enforced in code.

`needs_reason` is the missing *why* (D8): a proposal that would change the
roster without the manager having said why is withdrawn and turned back into
a question. `needs_input` is the missing *what* (D24): a change whose target
was guessed is withdrawn the same way, because knowing why דניאל is being
moved does not tell you *which* דניאל got moved. Either gate can hold a
proposal, and only one question is asked at a time -- the target first.
"""

from app.bl.changes.profile_ops import constraints, profile_operations
from app.bl.changes.questions import (
    ask_which_person, ask_which_shift, report_dropped, unresolved_people,
)
from app.bl.changes.targets import AMBIGUOUS_SHIFT, bound_operations
from app.bl.changes.values import bounded


class ProposalGate:
    def __init__(self, answer: dict, profile: dict, schedule: dict, stated_reason: str):
        self._answer = answer
        self._stated_reason = stated_reason
        self.operations, self._dropped = bound_operations(
            answer.get("operations"), schedule
        )
        self.profile_operations = profile_operations(
            answer.get("profile_operations"), profile
        )
        # An unidentifiable target is the more basic failure: a reason
        # attached to the wrong person is worse than a missing one.
        self._unresolved = unresolved_people(self.operations, profile)
        # Held for naming several possible shifts only when *nothing* else
        # survived: a proposal that can carry out three of four moves should.
        self._ambiguous = [
            row for row in self._dropped if row["why"] == AMBIGUOUS_SHIFT
        ] if not self.operations else []
        self.needs_reason = self._missing_reason()
        self.needs_input = bool(answer.get("needs_input")) or bool(
            self._unresolved or self._ambiguous
        )
        self._hold()

    def _missing_reason(self) -> bool:
        if self._stated_reason:
            return False
        return bool(self._answer.get("needs_reason")) or bool(
            self.operations and not self._answer.get("agent_reason")
        )

    def _hold(self) -> None:
        if self.needs_input:
            # Nothing is queued while the manager is asked, and the reason is
            # worth asking for only once the target is settled.
            self.operations, self.profile_operations = [], []
            self.needs_reason = False
        if self.needs_reason:
            # A question, not a rejection: the manager omitted something.
            self.operations = []
        if self.profile_operations:
            self.operations = []
            self.needs_reason = False

    def reply(self) -> str:
        reply = bounded(self._answer.get("reply"))
        if self._unresolved and not reply:
            # Code found an ambiguity the model did not; a held proposal with
            # nothing said would read as the agent ignoring the request.
            return ask_which_person(self._unresolved)
        if self._ambiguous:
            return ask_which_shift(self._ambiguous[0])
        if self._dropped and not self.needs_reason and not self.needs_input \
                and not self.operations and not self.profile_operations:
            # Everything aimed at a target that is not there: the model's
            # reply describes the change as though it happened.
            return report_dropped(self._dropped)
        return reply


def build_proposal(
    answer: dict, profile: dict, schedule: dict, stated_reason: str,
    request: str = "",
) -> dict:
    gate = ProposalGate(answer, profile, schedule, stated_reason)
    return {
        "reply": gate.reply(),
        "needs_reason": gate.needs_reason,
        "needs_input": gate.needs_input,
        # Echoed back only while a question is open, so an answered question
        # cannot be re-opened by a stale echo.
        "pending_request": request if gate.needs_input else "",
        "agent_reason": bounded(answer.get("agent_reason")),
        "stated_reason": stated_reason,
        "operations": gate.operations,
        "profile_operations": gate.profile_operations,
        "constraints": constraints(answer.get("constraints")),
    }

