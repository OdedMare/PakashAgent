"""`PlanningAgent`: a manager's question, answered by read-only tools."""

from typing import List, Optional

from app.bl.planner.fallback import DeterministicAnswerer
from app.bl.planner.model_loop import ModelToolLoop
from app.bl.planner.shaping import bounded, resume
from app.common.errors import AgentError


class PlanningAgent:
    def __init__(self, llm, tools):
        self._with_model = ModelToolLoop(llm, tools)
        self._without_model = DeterministicAnswerer(tools)

    def answer(
        self,
        team_id: str,
        request: str,
        profile: dict,
        period: Optional[dict] = None,
        preferences: Optional[List[dict]] = None,
        pending_request: str = "",
    ) -> dict:
        """What the agent makes of a question. Reads only; writes nothing.

        Falls back to the deterministic reader whenever the model cannot be
        reached — including when none is configured — and says so in the
        result (`used_model: False`), because its coverage is narrower.

        `pending_request` is the question a previous turn asked about. When
        set, `request` is the *answer* to a clarification, and the two are
        read together.
        """
        text = bounded(request)
        if not text:
            raise AgentError("הבקשה אינה יכולה להיות ריקה")
        pending = bounded(pending_request)
        resolved = resume(pending, text)
        try:
            return self._with_model.answer(
                team_id, resolved, profile, period, preferences,
                pending=pending, reply=text if pending else "",
            )
        except AgentError:
            # Unconfigured, unreachable, or answering with unusable JSON.
            # All three mean the same thing here: answer without it.
            return self.without_model(team_id, resolved, profile, period)

    def without_model(
        self, team_id: str, request: str, profile: dict,
        period: Optional[dict] = None,
    ) -> dict:
        """The same tools, chosen by keyword rather than by a model."""
        return self._without_model.answer(team_id, request, profile, period)
