"""The employee's assistant: swap and "make my week easier" questions (D27).

A small, read-only chat for one signed-in employee. It answers two kinds of
question -- *who could I swap with* and *how could my shifts work better* --
over the published schedule, and nothing else.

**It writes nothing.** The reply carries `answer` and `suggestions`; a
suggestion is a swap the employee may *offer* by pressing a button, which
calls the existing `POST /api/employee/swaps` -- the same request the swap
form sends, awaiting the colleague and then the manager (D14).

**Which swaps exist is decided in code** (`swap_options.py`), and the model
may only pick from them by id. It never sees a colleague's constraint, a
pending request, a draft, or the change log: only what the employee's own
screen already shows, plus the list of clean swaps.

**It answers without a model.** Unreachable, unconfigured or malformed, the
reply falls back to the clean swaps in plain Hebrew, as the planner does.
"""

import json
import logging
from typing import List, Optional

from app.bl.audit import fairness, personal_summary
from app.bl.employee_service.personal import teammates
from app.bl.employee_service.swap_options import swap_options
from app.bl.employee_service.values import employees, iso_date, shifts, text, window
from app.bl.prompts import load
from app.common.errors.errors import AgentError
from app.common.time_context.time_context import israel_today

_log = logging.getLogger("pakash.employee_assistant")
_FLOW = "employee_assistant"
_MAX_SUGGESTIONS = 4
_MAX_ANSWER = 1500
_HISTORY_TURNS = 6
_HISTORY_CHARS = 600

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["answer", "suggestions"],
    "properties": {
        "answer": {"type": "string"},
        "suggestions": {
            "type": "array", "items": {"type": "string"}, "maxItems": _MAX_SUGGESTIONS,
        },
    },
}

_NO_SCHEDULE = (
    "עוד אין סידור מפורסם, אז אין משמרות להחליף. "
    "אם יש יום שלא מתאים לך, אפשר כבר עכשיו לשלוח בקשה למנהל בטאב “בקשות והחלפות”."
)


class EmployeeAssistant:
    def __init__(self, repository, schedules, llm=None):
        self._repository = repository
        self._schedules = schedules
        self._llm = llm

    def ask(self, team_id: str, employee: str, question: str,
            history: Optional[List[dict]] = None) -> dict:
        """One reply: an answer, and the clean swaps it points at."""
        asked = text(question)
        if not asked:
            raise AgentError("השאלה ריקה")
        schedule = self._schedules.current(team_id, role="member")
        if not schedule:
            return _reply(_NO_SCHEDULE, [], used_model=False)
        profile = self._repository.team_profile(team_id) or {}
        start, end = window(schedule)
        options = swap_options(
            schedule, profile, self._repository.availability(team_id, start, end),
            employee, israel_today(),
        )
        facts = _facts(employee, schedule, profile, options)
        try:
            return self._with_model(facts, asked, history or [], options)
        except Exception:  # noqa: BLE001 -- any model failure answers without it
            _log.warning("employee assistant fell back team=%s", team_id, exc_info=True)
            return _without_model(asked, options)

    def _with_model(self, facts: dict, question: str, history: List[dict],
                    options: List[dict]) -> dict:
        if self._llm is None:
            raise AgentError("אין מודל מוגדר")
        payload = dict(facts, question=question, recent_conversation=_history(history))
        reply = self._llm.complete_json(
            load("employee_assistant"), json.dumps(payload, ensure_ascii=False),
            schema=_SCHEMA, flow=_FLOW,
        )
        answer = text((reply or {}).get("answer"))[:_MAX_ANSWER]
        if not answer:
            raise AgentError("המודל החזיר תשובה ריקה")
        return _reply(answer, _chosen(reply.get("suggestions"), options), used_model=True)


def _facts(employee: str, schedule: dict, profile: dict, options: List[dict]) -> dict:
    """What the model reads: the employee's own screen, and the clean swaps.

    The team appears only as an average. Colleagues' hours are the manager's
    view (the stats panel), not a teammate's.
    """
    assignments = schedule.get("assignments") or []
    summary = personal_summary(employee, assignments, shifts(profile),
                               warnings=schedule.get("warnings") or [])
    team = fairness(assignments, shifts(profile), employees(profile))
    today = israel_today().isoformat()
    return {
        "employee": employee,
        "today": today,
        "period": {"starts_on": iso_date(schedule.get("starts_on")),
                   "ends_on": iso_date(schedule.get("ends_on"))},
        "shift_types": [_shift_type(row) for row in shifts(profile) if isinstance(row, dict)],
        "my_shifts": [dict(row, upcoming=row["date"] >= today) for row in summary["shifts"]],
        "with_me": teammates(assignments, employee),
        "my_hours": summary["total_hours"],
        "team_average_hours": team["average_hours"],
        "my_by_shift": summary["by_shift"],
        "my_warnings": [text(row.get("message")) for row in summary["warnings"]],
        "swap_options": options,
    }


def _shift_type(row: dict) -> dict:
    return {key: row.get(key) for key in ("name", "start_time", "end_time", "is_on_call")
            if row.get(key) not in (None, "")}


def _history(turns: List[dict]) -> List[dict]:
    return [
        {"from": text(turn.get("role")), "text": text(turn.get("text"))[:_HISTORY_CHARS]}
        for turn in turns[-_HISTORY_TURNS:] if isinstance(turn, dict) and text(turn.get("text"))
    ]


def _chosen(ids, options: List[dict]) -> List[dict]:
    """The options the model pointed at, by id. An unknown id is dropped."""
    wanted = [text(item) for item in ids] if isinstance(ids, list) else []
    known = {option["id"]: option for option in options}
    picked = []
    for option_id in wanted:
        if option_id in known and known[option_id] not in picked:
            picked.append(known[option_id])
    return picked[:_MAX_SUGGESTIONS]


def _without_model(question: str, options: List[dict]) -> dict:
    """The clean swaps in plain Hebrew, narrowed to a named day if there is one."""
    named = [option for option in options if option["mine"]["weekday"] in question]
    shown = (named or options)[:3]
    if not shown:
        return _reply(
            "לא מצאתי כרגע החלפה שהסידור מאפשר בלי ליצור בעיה חדשה. "
            "אם יש יום שלא מתאים לך, אפשר לשלוח בקשה למנהל בטאב “בקשות והחלפות”.",
            [], used_model=False,
        )
    lines = ["אלה החלפות שבדקתי ושהסידור מאפשר:"]
    for option in shown:
        lines.append("- {} ⇄ {} עם {}".format(
            _when(option["mine"]), _when(option["theirs"]), option["colleague"]))
    lines.append("לחיצה על “להציע החלפה” שולחת בקשה לעמית/ה, ואחר כך המנהל מאשר.")
    return _reply("\n".join(lines), shown, used_model=False)


def _when(shift: dict) -> str:
    return "{} {} ({})".format(shift["weekday"], shift["date"][8:10] + "/" + shift["date"][5:7],
                               shift["shift"])


def _reply(answer: str, suggestions: List[dict], used_model: bool) -> dict:
    return {"answer": answer, "suggestions": suggestions, "used_model": used_model}
