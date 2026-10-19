"""Recording which tools an answer ran, so the manager can see its basis."""

from typing import List, Optional


class ToolTrace:
    """Runs tools and records each call as a step the manager can see."""

    def __init__(self, tools, team_id: str):
        self._tools = tools
        self._team_id = team_id
        self.steps: List[dict] = []
        self.results: List[dict] = []

    def run(self, tool: str, arguments: dict, shown: Optional[dict] = None) -> dict:
        outcome = self._tools.run(self._team_id, tool, arguments)
        self.steps.append({
            "tool": tool,
            "arguments": arguments if shown is None else shown,
            "ok": bool(outcome.get("ok")),
        })
        self.results.append(outcome)
        return outcome

    def reply(self, answer: str, needs_confirmation: bool = False) -> tuple:
        return answer, self.steps, self.results, needs_confirmation
