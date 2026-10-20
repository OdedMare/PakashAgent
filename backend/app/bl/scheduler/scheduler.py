"""`Scheduler`: the model call that assigns people into the grid."""

import json
from typing import List, Optional

from app.bl import rotation
from app.bl.prompts import load
from app.bl.scheduler.payload import (
    SCHEDULE_RESPONSE_SCHEMA,
)
from app.bl.scheduler.slots import build_slots, chunks
from app.bl.scheduler.span import SpanGenerator
from app.bl.scheduler.planning import ChunkedRun
from app.bl.scheduler.values import bounded
from app.common.errors import AgentError, ModelOutputError
from app.common.config import ENGINE_AI, ENGINE_AUTO, ENGINE_CODE


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
        engine: str = ENGINE_AI,
        translation_cache=None,
    ) -> dict:
        """Slots for the period plus the model's assignments, chunk by chunk.

        The legacy one-shot path, kept for API consumers. Chunks are NOT
        independent: each sees what earlier ones decided, and its fairness
        tally is recomputed over the real history *plus* this run, so week two
        sees week one's nights as nights. Nothing is persisted here.
        """
        code = self._code_result(
            engine, profile, starts_on, ends_on, availability, history,
            instructions, required_assignments, None, preferences, translation_cache,
        )
        if code is not None:
            if not code["slots"]:
                raise AgentError("לא ניתן לבנות סידור: לא הוגדרו משמרות לתקופה הזו")
            return code
        _check_rotation(profile)
        slots = build_slots(profile, starts_on, ends_on)
        if not slots:
            raise AgentError("לא ניתן לבנות סידור: לא הוגדרו משמרות לתקופה הזו")
        run = ChunkedRun(profile, starts_on, ends_on, slots, availability,
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
        engine: str = ENGINE_AI,
        translation_cache=None,
    ) -> dict:
        """Generate and verify one contiguous stretch of dates. See `span.py`.

        `translation_cache` is the team's kept translations
        (`bl/compiled_sources/`); without one every source is translated."""
        code = self._code_result(
            engine, profile, starts_on, ends_on, availability, history,
            instructions, required_assignments, already_scheduled, preferences,
            translation_cache,
        )
        if code is not None:
            return code
        _check_rotation(profile)
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

    def _code_result(
        self, engine, profile, starts_on, ends_on, availability, history,
        instructions, required_assignments, already_scheduled, preferences, cache=None,
    ):
        """Return a safe code result, or None when AI should take the request."""
        if engine not in (ENGINE_CODE, ENGINE_AUTO):
            return None
        from app.bl.deterministic_scheduler import generate_span, unsupported_reason

        reason = unsupported_reason(profile, availability, instructions, preferences)
        requests = []
        if reason:
            if engine == ENGINE_CODE:
                raise AgentError(reason + ". בחרו במצב AI או אוטומטי.")
            translated = self._translate_directives(
                profile, starts_on, ends_on, availability, instructions, preferences,
                history, required_assignments, already_scheduled, cache,
            )
            if translated is None:
                return None
            availability = list(availability or []) + translated["availability"]
            required_assignments = list(required_assignments or []) + translated["required_assignments"]
            requests = translated["requests"]
        result = generate_span(
            profile, starts_on, ends_on, availability=availability,
            history=history, required_assignments=required_assignments,
            already_scheduled=already_scheduled, requests=requests,
        )
        # Auto keeps free code only when it is already as clean as the audited
        # model path. Code mode remains useful for an intentionally partial
        # draft and exposes the same warnings to the manager.
        if engine == ENGINE_AUTO and result.get("warnings"):
            return None
        if reason:
            _hybrid(result, translated)
        return result

    def _translate_directives(
        self, profile, starts_on, ends_on, availability, instructions, preferences,
        history=None, required_assignments=None, already_scheduled=None, cache=None,
    ):
        """The manager's words as directives and requests, or None. A bounded
        tool loop (`bl/directive_agent/`); code validates its final answer."""
        from app.bl.directive_agent import DirectiveAgent

        return DirectiveAgent(self._llm).translate(
            profile, starts_on, ends_on, availability=availability,
            instructions=instructions, preferences=preferences, history=history,
            required_assignments=required_assignments, already_scheduled=already_scheduled,
            cache=cache,
        )

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


def _hybrid(result: dict, translated: dict) -> None:
    """Say what translating cost, what the kept translations saved, and
    every wish code was built without -- said, never dropped silently."""
    usage = translated["usage"]
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
        "ההנחיות נטענו מתרגום שמור והשיבוץ נבנה בקוד דטרמיניסטי."
        if not translated["model_calls"] else
        "ההנחיות תורגמו ב-AI והשיבוץ נבנה בקוד דטרמיניסטי.")
    result["notes"] = [
        "בקשה רכה לא נלקחה בחשבון בשיבוץ: «%s» (%s)." % (row["text"], row["reason"])
        for row in translated["unresolved"]
    ] + list(result.get("notes") or [])


def _check_rotation(profile):
    # Profile normalization also supplies a default pattern to civilian
    # rosters. A lettered group is what puts a person on an actual cycle.
    grouped = [person for person in profile.get("employees") or []
               if isinstance(person, dict) and bounded(person.get("rotation_group"))]
    errors = rotation.configuration_errors(dict(profile, employees=grouped))
    if errors:
        raise AgentError("יש להשלים את העוגנים והקבוצות בהגדרת היחידה > סבבים ותלתונים: %s" % "; ".join(errors))
