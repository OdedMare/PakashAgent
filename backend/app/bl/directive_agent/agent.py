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
answer that marks a source `unresolved` is final, because it means "code
cannot do this", not "try again".

What then happens is decided per source (`partial.per_source`): if every
source left out is only a wish, the rest is kept and the wishes are
reported; if any is binding, the full scheduler takes the period, as it
always did.

Standing sources -- rules, policies, notes, preferences -- are translated
in `compile` mode and kept in the `cache` it is handed
(`bl/compiled_sources/`), so the next build loads them instead of asking.
`compile` does the same ahead of any build, when setup is saved.
"""

import json
from typing import Dict, List, Optional

from app.bl.compiled_sources import NullCache, settle
from app.bl.directive_agent.schema import (
    MAX_CALLS_PER_TURN, MAX_DRY_RUNS, TOOL_DESCRIPTIONS, TOOL_NAMES, TURN_SCHEMA,
)
from app.bl.directive_agent.partial import assemble, per_source
from app.bl.directive_agent.tools import TranslationTools
from app.bl.prompts import load
from app.bl.scheduler.directives import semantic_sources
from app.bl.scheduler.span_audit import add_usage, usage_of
from app.common.errors import AgentError

MAX_TURNS = 4


class DirectiveAgent:
    def __init__(self, llm, max_turns: int = MAX_TURNS):
        self._llm = llm
        self._max_turns = max(1, max_turns)

    def translate(self, profile: dict, starts_on: str, ends_on: str, availability=None,
                  instructions: str = "", preferences=None, history=None,
                  required_assignments=None, already_scheduled=None,
                  cache=None) -> Optional[dict]:
        """Validated directives and requests, with `unresolved` listing the
        wishes left out, or None when the full scheduler should take the
        request: nothing to translate, the model unreachable, or a binding
        source not translated within the bound.

        A standing source `cache` already holds costs no model call, and
        one it holds as unresolved and binding settles the answer at once."""
        sources = semantic_sources(profile, availability, instructions, preferences)
        if not sources:
            return None
        cache = cache or NullCache()
        by_id = {row["id"]: row for row in sources}
        outcomes = cache.lookup(profile, sources)
        if _binding_left(outcomes, by_id):
            return None
        hits = dict(outcomes)
        run = _Run(self._max_turns)
        misses = [row for row in sources if row["id"] not in hits]
        if misses:
            tools = TranslationTools(profile, starts_on, ends_on, misses, availability,
                                     history, required_assignments, already_scheduled)
            fresh = self._settle(profile, starts_on, ends_on, misses, tools, cache, run)
            if fresh is None:
                return None
            outcomes.update(fresh)
        if _binding_left(outcomes, by_id):
            return None
        return dict(assemble(outcomes, by_id, run.usage), usage=run.usage,
                    model_calls=run.turns, steps=run.steps, cached=len(hits),
                    cached_tokens=sum(row.get("tokens") or 0 for row in hits.values()))

    def compile(self, profile: dict, sources: List[dict], starts_on: str, ends_on: str,
                cache) -> Optional[Dict[str, dict]]:
        """Translate standing sources ahead of any build and keep them in
        `cache`. `starts_on`/`ends_on` is only the week the tools look at;
        what is kept does not depend on it."""
        tools = TranslationTools(profile, starts_on, ends_on, sources)
        return self._settle(profile, starts_on, ends_on, sources, tools, cache,
                            _Run(self._max_turns))

    def _settle(self, profile, starts_on, ends_on, sources, tools, cache, run):
        """Each source's outcome, judged for time and kept where it may be."""
        anchors = cache.anchors(sources)
        base = _payload(profile, starts_on, ends_on, tools, sources, anchors)
        answered = self._converse(base, tools, sources, profile, starts_on, ends_on, run)
        if answered is None:
            return None
        answer, outcomes = answered
        outcomes = settle(answer, sources, outcomes, anchors)
        cache.store(profile, sources, outcomes, run.usage, anchors)
        return outcomes

    def _converse(self, base, tools, sources, profile, starts_on, ends_on, run):
        """The bounded loop: the final answer and its per-source outcomes."""
        while run.turns < self._max_turns:
            final = run.last()
            answer = self._ask(dict(base, results=run.results, final_turn=final))
            if answer is None:
                return None
            run.count(answer)
            calls = _calls(answer)
            if calls and not final:
                run.call(tools, calls)
                continue
            outcomes = per_source(answer, sources, profile, starts_on, ends_on)
            whole = all("items" in outcome for outcome in outcomes.values())
            if whole or answer.get("unresolved") or final:
                return answer, outcomes
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


def _binding_left(outcomes: Dict[str, dict], by_id: Dict[str, dict]) -> bool:
    return any("left" in outcome and by_id[source_id].get("binding", True)
               for source_id, outcome in outcomes.items())


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
             sources: List[dict], anchors: Dict[str, str]) -> dict:
    return {
        "period": {"starts_on": starts_on, "ends_on": ends_on},
        "employees": [
            {"name": name, "eligible_shifts": person.get("eligible_shifts") or []}
            for name, person in tools.people.items()
        ],
        "shifts": sorted({slot["shift_name"] for slot in tools.slots}),
        "slots": [{"date": slot["slot_date"], "shift": slot["shift_name"]}
                  for slot in tools.slots],
        "sources": [_shown(row, anchors) for row in sources],
        "tools": [{"name": name, "purpose": TOOL_DESCRIPTIONS[name]} for name in TOOL_NAMES],
    }


def _shown(source: dict, anchors: Dict[str, str]) -> dict:
    """A source as the model sees it: `compile` for a standing one, whose
    translation outlives this period, `period` for this build's instruction."""
    shown = {key: source[key] for key in ("id", "kind", "context", "text", "binding")}
    if source.get("persistent"):
        shown.update(mode="compile", anchored_on=anchors.get(source["id"]) or "")
    else:
        shown["mode"] = "period"
    return shown


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
