"""`Scheduler`: the manager's words translated, then the constraint solver.

Two steps, and only the first may call a model (D34). Everything code
cannot read on its own — the build's free instruction, rules, policies,
notes and preferences (`directives.semantic_sources`) — goes to the
`DirectiveAgent`, which answers with validated absences, pins and structured
requests. The solver (`bl/solver/`) then assigns every slot of the span in
one solve. A sentence that could not be translated is never sent anywhere
else: the schedule is built without it and its `notes` say so, binding or
not, so the manager can restate it.
"""

from typing import List, Optional

from app.bl import solver
from app.bl.scheduler.directives import semantic_sources
from app.bl.scheduler.slots import plan_spans
from app.bl.scheduler.quality import combine_metrics, quality
from app.bl.shared import text
from app.common.errors import AgentError

_UNREACHABLE = "לא ניתן היה לתרגם את ההנחיות (המודל לא זמין)"
_LEFT_BINDING = "הנחיה מחייבת לא נאכפה בשיבוץ: «%s» (%s). נסחו אותה מחדש או הגדירו אותה כאילוץ."
_LEFT_WISH = "בקשה רכה לא נלקחה בחשבון בשיבוץ: «%s» (%s)."


class Scheduler:
    """Build any span of a period from the workplace profile."""

    def __init__(self, llm, settings=None):
        self._llm = llm
        # The live settings store, or None for the defaults; read per build
        # so a limit saved in the panel applies to the next one.
        self._settings = settings

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
        translation_cache=None,
        keep: Optional[List[dict]] = None,
    ) -> dict:
        """Assign every slot from `starts_on` through `ends_on`.

        `keep` are rows to hold where they still fit — a rebuild after the
        shift vocabulary changed should move as few people as it can.
        `translation_cache` is the team's kept translations
        (`bl/compiled_sources/`); without one every source is translated."""
        translated = self._translate(
            profile, starts_on, ends_on, availability, instructions, preferences,
            history, required_assignments, already_scheduled, translation_cache,
        )
        result = solver.generate_span(
            profile, starts_on, ends_on,
            availability=list(availability or []) + translated["availability"],
            history=history,
            required_assignments=list(required_assignments or []) + translated["required_assignments"],
            already_scheduled=already_scheduled,
            requests=translated["requests"] + _kept(profile, keep),
            **self._limits(),
        )
        if translated["sources"]:
            _report(result, translated)
        return result

    def generate_day(self, profile: dict, day: str, **kwargs) -> dict:
        """Generate exactly one date."""
        return self.generate_span(profile, day, day, **kwargs)

    def generate_verified(self, profile, starts_on, ends_on, availability=None,
                          history=None, instructions="", required_assignments=None,
                          preferences=None, already_scheduled=None, keep=None):
        """A period for the manager's chat: spans in order, each seeing the
        last, then audited and measured as one."""
        committed = list(already_scheduled or [])
        result = dict(slots=[], assignments=[], warnings=[], notes=[], summary="", metrics=[])
        for span in plan_spans(profile, starts_on, ends_on):
            pins = [row for row in required_assignments or [] if row.get("date") in span["dates"]]
            generated = self.generate_span(
                profile, span["date"], span["through"], availability=availability,
                history=history, instructions=instructions, required_assignments=pins,
                preferences=preferences, already_scheduled=committed, keep=keep)
            committed = [row for row in committed if row.get("date") not in span["dates"]]
            committed.extend(generated["assignments"])
            for key in ("slots", "assignments", "warnings", "notes"):
                result[key].extend(generated.get(key) or [])
            result["metrics"].append(generated.get("metrics") or {})
            result["summary"] = generated.get("summary") or result["summary"]
        if not result["slots"]:
            raise AgentError("לא הוגדרו משמרות לתאריכים שנבחרו")
        result["quality"] = quality(committed, result["slots"], profile, result["warnings"])
        result["performance"] = {}
        for measured in result["metrics"]:
            result["performance"] = combine_metrics(result["performance"], measured)
        return result

    def _limits(self) -> dict:
        current = self._settings.get() if self._settings is not None else None
        return {
            "time_limit": float(getattr(current, "solver_time_limit_seconds", 10.0) or 10.0),
            "workers": int(getattr(current, "solver_workers", 8) or 8),
        }

    def _translate(self, profile, starts_on, ends_on, availability, instructions,
                   preferences, history, required_assignments, already_scheduled, cache) -> dict:
        """The manager's sentences as solver input. Never None: a source
        that did not translate is listed in `unresolved` instead."""
        sources = semantic_sources(profile, availability, instructions, preferences)
        empty = {"availability": [], "required_assignments": [], "requests": [],
                 "unresolved": [], "sources": sources, "usage": {}, "model_calls": 0,
                 "steps": [], "cached": 0, "cached_tokens": 0}
        if not sources:
            return empty
        from app.bl.directive_agent import DirectiveAgent

        translated = DirectiveAgent(self._llm).translate(
            profile, starts_on, ends_on, availability=availability,
            instructions=instructions, preferences=preferences, history=history,
            required_assignments=required_assignments, already_scheduled=already_scheduled,
            cache=cache, sources=sources,
        )
        if translated is None:
            empty["unresolved"] = [dict(row, reason=_UNREACHABLE) for row in sources]
            return empty
        return dict(empty, **translated)


def _kept(profile: dict, rows: Optional[List[dict]]) -> List[dict]:
    """Each row to keep as a `prefer` the solver weighs; rows naming a person
    or a shift the profile no longer has are dropped, not refused."""
    people = {text(row.get("name")) for row in profile.get("employees") or [] if isinstance(row, dict)}
    shifts = {text(row.get("name")) for row in profile.get("shifts") or [] if isinstance(row, dict)}
    return [
        {"kind": "prefer", "employees": [row["employee"]], "shifts": [row["shift"]],
         "dates": [row["date"]], "weight": 0.5, "reason": "שמירה על השיבוץ הקודם"}
        for row in rows or []
        if isinstance(row, dict) and row.get("employee") in people and row.get("shift") in shifts
        and row.get("date")
    ]


def _report(result: dict, translated: dict) -> None:
    """Say what translating cost, what kept translations saved, and every
    sentence the schedule was built without -- said, never dropped."""
    usage = translated.get("usage") or {}
    result["metrics"].update({
        "engine": "hybrid",
        "model_calls": translated["model_calls"],
        "translation_steps": translated["steps"],
        "unresolved_sources": len(translated["unresolved"]),
        "compiled_hits": int(translated.get("cached") or 0),
        "tokens_saved": int(translated.get("cached_tokens") or 0),
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or 0),
    })
    result["summary"] = (
        "ההנחיות נטענו מתרגום שמור והשיבוץ נבנה בפותר אילוצים."
        if not translated["model_calls"] else
        "ההנחיות תורגמו ב-AI והשיבוץ נבנה בפותר אילוצים.")
    binding = {row["id"]: row.get("binding", True) for row in translated["sources"]}
    result["notes"] = [
        (_LEFT_BINDING if binding.get(row.get("source_id") or row.get("id"), True) else _LEFT_WISH)
        % (row["text"], row["reason"])
        for row in translated["unresolved"]
    ] + list(result.get("notes") or [])
