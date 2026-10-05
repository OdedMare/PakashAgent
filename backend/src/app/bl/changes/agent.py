"""`ChangeAgent`: turn a manager's sentence into a proposal they can confirm."""

import datetime
import json
from typing import List, Optional

from app.bl import rotation
from app.bl.changes.proposal import build_proposal
from app.bl.changes.schema import CHANGE_RESPONSE_SCHEMA
from app.bl.changes.values import bounded, date_of, dict_rows, json_default
from app.bl.shared.clarification import resume
from app.bl.prompts import load
from app.common.errors.errors import AgentError


class ChangeAgent:
    def __init__(self, llm):
        self._llm = llm

    def propose(
        self,
        profile: dict,
        schedule: dict,
        request: str,
        stated_reason: str = "",
        availability: Optional[List[dict]] = None,
        history: Optional[List[dict]] = None,
        pending_request: str = "",
    ) -> dict:
        """What the agent would do, and why. Applies nothing.

        `pending_request` is the request a previous turn held rather than
        guess at. When it is set, `request` is the manager's *answer* to the
        question that turn asked, and the two are proposed together.
        """
        text = bounded(request)
        if not text:
            raise AgentError("הבקשה אינה יכולה להיות ריקה")
        pending = bounded(pending_request)
        resolved = resume(pending, text)
        payload = {
            "profile": _profile_for_model(profile),
            "schedule": _schedule_for_model(schedule),
            # Whose weekend each closure is, already worked out -- otherwise
            # a spoken change is the one path that cannot see the rotation.
            "closures": _closures_for_model(profile, schedule),
            "availability": dict_rows(availability),
            "history": dict_rows(history, 100),
            "request": resolved,
            # What was asked and what came back, kept apart from the merged
            # sentence, so the model does not ask the same question twice.
            "asked_last_turn": pending,
            "answer_to_that": text if pending else "",
            "stated_reason": bounded(stated_reason),
        }
        return build_proposal(
            self._ask(payload), profile, schedule, bounded(stated_reason),
            request=resolved,
        )

    def _ask(self, payload: dict) -> dict:
        answer = self._llm.complete_json(
            load("changes"),
            json.dumps(payload, ensure_ascii=False, default=json_default),
            schema=CHANGE_RESPONSE_SCHEMA,
            flow="changes",
        )
        if not isinstance(answer, dict):
            raise AgentError("המודל החזיר הצעת שינוי לא תקינה")
        return answer


def _profile_for_model(profile: dict) -> dict:
    profile = profile if isinstance(profile, dict) else {}
    return {
        "workplace": profile.get("workplace") or {},
        "employees": profile.get("employees") or [],
        "shifts": profile.get("shifts") or [],
        "rules": profile.get("rules") or [],
        "rest_policy": profile.get("rest_policy") or "",
        "fairness_policy": profile.get("fairness_policy") or "",
        "conflict_policy": profile.get("conflict_policy") or "",
    }


def _closures_for_model(profile: dict, schedule: dict) -> List[dict]:
    """The same closure rows the scheduler sends, from the same arithmetic.

    The agent proposing a Saturday swap and the agent building the week must
    not disagree about whose Saturday it is. Empty when there are no readable
    dates -- an invented phase is worse than none (D3).
    """
    schedule = schedule if isinstance(schedule, dict) else {}
    try:
        start = datetime.date.fromisoformat(date_of(schedule.get("starts_on")))
        end = datetime.date.fromisoformat(date_of(schedule.get("ends_on")))
    except (TypeError, ValueError):
        return []
    return rotation.schedule_for_model(profile, start, end)


def _schedule_for_model(schedule: dict) -> dict:
    """The period as the model reads it: slots, and who is on each."""
    schedule = schedule if isinstance(schedule, dict) else {}
    return {
        "starts_on": date_of(schedule.get("starts_on")),
        "ends_on": date_of(schedule.get("ends_on")),
        "slots": [
            {
                "shift": bounded(slot.get("shift_name")),
                "date": date_of(slot.get("slot_date")),
                "headcount": slot.get("headcount", 1),
            }
            for slot in schedule.get("slots") or []
        ],
        "assignments": [
            {
                "employee": bounded(row.get("employee")),
                "shift": bounded(row.get("shift")),
                "date": date_of(row.get("date")),
                "reason": bounded(row.get("reason")),
            }
            for row in schedule.get("assignments") or []
        ],
    }
