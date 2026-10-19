"""Answering without a model: keyword reading, the same tools, Hebrew templates.

The product's floor. `bl/intent.py` places the sentence into one of seven
shapes and each shape maps onto the tools that answer it. A sentence it cannot
place comes back `understood: False` with a list of what it *can* answer --
deliberately not a guess.
"""

from typing import Callable, Dict, Optional

from app.bl import intent as intent_reader
from app.bl.planner import shaping
from app.bl.planner.fallback_answers import FallbackAnswers
from app.common.time_context import israel_today

# Lists what the reader *can* do rather than apologising: a manager told only
# "I did not understand" has no way to find the sentence that would have worked.
_NOT_UNDERSTOOD = (
    "אני רוצה לדייק ולא לנחש. מה תרצו לברר קודם — מחליף לעובד/ת, "
    "מידע על הצוות, חוסרים בסידור, שעות של עובד/ת, או מוכנות לפרסום?"
)


class DeterministicAnswerer:
    def __init__(self, tools):
        answers = FallbackAnswers(tools)
        self._handlers: Dict[str, Callable] = {
            intent_reader.INTENT_REPLACEMENTS: answers.replacements,
            intent_reader.INTENT_ABSENCE: answers.replacements,
            intent_reader.INTENT_GAPS: answers.gaps,
            intent_reader.INTENT_EMPLOYEE: answers.employee,
            intent_reader.INTENT_PUBLISH: answers.publish,
            intent_reader.INTENT_PERIOD: answers.period,
            intent_reader.INTENT_TEAM: answers.team,
        }

    def answer(
        self, team_id: str, request: str, profile: dict,
        period: Optional[dict] = None,
    ) -> dict:
        profile = profile or {}
        read = intent_reader.read(
            request,
            roster=shaping.names(profile.get("employees")),
            shift_names=shaping.names(profile.get("shifts")),
            today=israel_today().isoformat(),
            period=period,
        )
        handler = self._handlers.get(read["intent"])
        if handler is None:
            return _not_understood(read["intent"])
        answer, steps, results, needs_confirmation = handler(team_id, read)
        asking = shaping.is_question(answer)
        return {
            "answer": answer,
            "steps": steps,
            "results": results,
            "needs_confirmation": needs_confirmation,
            "needs_input": asking,
            "question": shaping.plain_question(answer) if asking else None,
            "pending_request": request if asking else "",
            "used_model": False,
            "understood": True,
            "intent": read["intent"],
        }


def _not_understood(intent: str) -> dict:
    return {
        "answer": _NOT_UNDERSTOOD,
        "steps": [],
        "results": [],
        "needs_confirmation": False,
        "needs_input": True,
        "question": None,
        # Nothing to resume: the sentence was never placed, so there is no
        # intent for an answer to continue.
        "pending_request": "",
        "used_model": False,
        "understood": False,
        "intent": intent,
    }

