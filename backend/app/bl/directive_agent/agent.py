"""`DirectiveAgent`: translate the manager's words by asking tools first.

The single-call translation had to get every name, slot and request right
blind, and one mistake refused the whole answer. Here the model may look
first: resolve a name, list the slots a weekday means, read a person's
eligibility, check a draft, or schedule it in memory and see what breaks.
Code still has the last word: the final answer goes through the same
`read_translation` the single call did, and nothing the tools return is
stored.

Bounded on purpose. `max_turns` model calls at most, `MAX_CALLS_PER_TURN`
tools per call and `MAX_DRY_RUNS` dry runs in all. A final answer code
refuses is handed back with the reasons while turns remain; an
answer that marks a source `unresolved` is final, because it means "this
needs the full scheduler", not "try again".
"""

import json
from typing import List, Optional

from app.bl.directive_agent.schema import (
    MAX_CALLS_PER_TURN, MAX_DRY_RUNS, TOOL_DESCRIPTIONS, TOOL_NAMES, TURN_SCHEMA,
)
from app.bl.directive_agent.tools import TranslationTools
from app.bl.prompts import load
from app.bl.scheduler.directives import read_translation, semantic_sources
from app.bl.scheduler.span_audit import add_usage, usage_of
from app.common.errors import AgentError

MAX_TURNS = 4


class DirectiveAgent:
    def __init__(self, llm, max_turns: int = MAX_TURNS):
        self._llm = llm
        self._max_turns = max(1, max_turns)

    def translate(self, profile: dict, starts_on: str, ends_on: str, availability=None,
                  instructions: str = "", preferences=None, history=None,
                  required_assignments=None, already_scheduled=None) -> Optional[dict]:
        """Validated directives and requests, or None when the full scheduler
        should take the request (nothing to translate, unresolved sources,
        the model unreachable, or no acceptable answer within the bound)."""
        sources = semantic_sources(profile, availability, instructions, preferences)
        if not sources:
            return None
        tools = TranslationTools(profile, starts_on, ends_on, sources, availability,
                                 history, required_assignments, already_scheduled)
        run = _Run(self._max_turns)
        base = _payload(profile, starts_on, ends_on, tools, sources)
        while run.turns < self._max_turns:
            answer = self._ask(dict(base, results=run.results, final_turn=run.last()))
            if answer is None:
                return None
            run.count(answer)
            calls = _calls(answer)
            if calls and not run.last():
                run.call(tools, calls)
                continue
            if answer.get("unresolved"):
                return None
            translated = read_translation(answer, sources, profile, starts_on, ends_on)
            if translated is not None:
                return dict(translated, usage=run.usage, model_calls=run.turns, steps=run.steps)
            run.refused(tools, answer)
        return None

    def _ask(self, payload: dict) -> Optional[dict]:
        try:
            answer = self._llm.complete_json(
                load("scheduler_directives"),
                json.dumps(payload, ensure_ascii=False),
                schema=TURN_SCHEMA,
                flow="scheduler",
            )
        except AgentError:
            return None
        return answer if isinstance(answer, dict) else None


class _Run:
    """What one translation has spent and learnt so far."""

    def __init__(self, max_turns: int):
        self.max_turns = max_turns
        self.turns = 0
        self.dry_runs = 0
        self.usage: dict = {}
        self.results: List[dict] = []
        self.steps: List[str] = []

    def last(self) -> bool:
        return self.turns >= self.max_turns - 1

    def count(self, answer: dict) -> None:
        self.turns += 1
        self.usage = add_usage(self.usage, usage_of(answer))

    def call(self, tools: TranslationTools, calls: List[dict]) -> None:
        for call in calls[:MAX_CALLS_PER_TURN]:
            if call["tool"] == "dry_run":
                if self.dry_runs >= MAX_DRY_RUNS:
                    self.results.append({"tool": "dry_run", "ok": False,
                                         "error": "dry run limit reached; answer now"})
                    continue
                self.dry_runs += 1
            self.steps.append(call["tool"])
            self.results.append(tools.run(call["tool"], call["arguments"]))

    def refused(self, tools: TranslationTools, answer: dict) -> None:
        """Hand a refused final answer back with code's reasons."""
        verdict = tools.run("check", {"directives": answer.get("directives"),
                                      "requests": answer.get("requests")})
        verdict["note"] = "your final answer was refused; fix these and answer again"
        self.steps.append("check")
        self.results.append(verdict)


def _payload(profile: dict, starts_on: str, ends_on: str, tools: TranslationTools,
             sources: List[dict]) -> dict:
    return {
        "period": {"starts_on": starts_on, "ends_on": ends_on},
        "employees": [
            {"name": name, "eligible_shifts": person.get("eligible_shifts") or []}
            for name, person in tools.people.items()
        ],
        "shifts": sorted({slot["shift_name"] for slot in tools.slots}),
        "slots": [{"date": slot["slot_date"], "shift": slot["shift_name"]}
                  for slot in tools.slots],
        "sources": sources,
        "tools": [{"name": name, "purpose": TOOL_DESCRIPTIONS[name]} for name in TOOL_NAMES],
    }


def _calls(answer: dict) -> List[dict]:
    calls = answer.get("calls")
    if not isinstance(calls, list):
        return []
    return [
        {"tool": call["tool"], "arguments": call.get("arguments") or {}}
        for call in calls
        if isinstance(call, dict) and call.get("tool") in TOOL_NAMES
        and isinstance(call.get("arguments") or {}, dict)
    ]


__all__ = ["DirectiveAgent", "MAX_TURNS"]
