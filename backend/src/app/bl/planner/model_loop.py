"""The tool loop: the model picks tools, the tools answer, repeat until done."""

import json
from typing import List, Optional

from app.bl.planner import shaping
from app.bl.planner.schema import PLANNER_RESPONSE_SCHEMA
from app.bl.prompts import load
from app.bl.tools import TOOL_DESCRIPTIONS, TOOL_NAMES
from app.common.errors import AgentError

# How many model turns one question may cost. Three is enough for the deepest
# real chain -- find the period, find the person's shift in it, find who could
# take that shift -- and a bound stops a model that keeps asking for one more.
_MAX_TURNS = 3
_NO_ANSWER = "לא הצלחתי להרכיב תשובה על סמך מה שבדקתי."


class ModelToolLoop:
    def __init__(self, llm, tools):
        self._llm = llm
        self._tools = tools

    def answer(
        self,
        team_id: str,
        request: str,
        profile: dict,
        period: Optional[dict],
        preferences: Optional[List[dict]],
        pending: str = "",
        reply: str = "",
    ) -> dict:
        base = {
            "profile": shaping.profile_for_model(profile),
            "period": shaping.period_for_model(period),
            "preferences": shaping.preferences_for_model(preferences),
            "tools": [
                {"name": name, "purpose": TOOL_DESCRIPTIONS[name]}
                for name in TOOL_NAMES
            ],
            "request": request,
            # What the manager was asked last turn and what they said back,
            # so the model continues that request rather than re-asking it.
            "asked_last_turn": pending,
            "answer_to_that": reply,
        }
        state = _LoopState()
        for _ in range(_MAX_TURNS):
            turn = self._ask(dict(base, results=state.results))
            calls = state.read(turn)
            if not calls or turn.get("done"):
                break
            state.run(self._tools, team_id, calls)
        return state.result(request)

    def _ask(self, payload: dict) -> dict:
        try:
            answer = self._llm.complete_json(
                load("planner"),
                json.dumps(payload, ensure_ascii=False),
                schema=PLANNER_RESPONSE_SCHEMA,
                flow="planner",
            )
        except AgentError:
            raise
        except Exception as exc:
            # A custom compatible adapter failing during setup must still let
            # `answer()` fall back to the deterministic tools, not a 500.
            raise AgentError("המודל לא זמין כרגע") from exc
        if not isinstance(answer, dict):
            raise AgentError("המודל החזיר תשובה לא תקינה")
        return answer


class _LoopState:
    def __init__(self):
        self.results: List[dict] = []
        self.steps: List[dict] = []
        self.answer = ""
        self.question = None
        self.needs_confirmation = False
        self.needs_input = False

    def read(self, turn: dict) -> List[dict]:
        self.answer = shaping.bounded(turn.get("answer")) or self.answer
        self.question = shaping.question(turn.get("question"))
        self.needs_confirmation = bool(turn.get("needs_confirmation"))
        self.needs_input = bool(turn.get("needs_input")) or self.question is not None
        return shaping.tool_calls(turn.get("tool_calls"))

    def run(self, tools, team_id: str, calls: List[dict]) -> None:
        # Tool calls are an internal turn, not a question for the boss.
        self.question, self.needs_input = None, False
        for call in calls:
            outcome = tools.run(team_id, call["tool"], call["arguments"])
            self.results.append(outcome)
            self.steps.append({
                "tool": call["tool"],
                "arguments": call["arguments"],
                "ok": bool(outcome.get("ok", True)),
            })

    def result(self, request: str) -> dict:
        return {
            "answer": self.answer or _NO_ANSWER,
            # What was actually run, so the manager can see which facts the
            # answer rests on -- a product requirement, not debugging output.
            "steps": self.steps,
            "results": self.results,
            "needs_confirmation": self.needs_confirmation,
            "needs_input": self.needs_input,
            "question": self.question,
            # Carried back only while a question is open, so the client has
            # nothing stale to echo once the answer has landed.
            "pending_request": request if self.needs_input else "",
            "used_model": True,
            "understood": True,
        }
