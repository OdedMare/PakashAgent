"""Answering a manager's question by running tools, with or without a model.

`ChangeAgent` handles the one-shot case — a sentence in, a proposal out — by
putting the whole period in front of the model at once. That works for *"דנה
חולה ביום חמישי"*. It does not work for *"מי יכול להחליף את יוסי בסופ״ש"*,
which needs four countable things worked out in order: which period, which of
יוסי's rows fall in it, who is free for each, and how they rank. A model
asked to do that from a wall of JSON gets it subtly wrong in exactly the way
`audit.py`'s docstring describes.

So this runs a **loop**: the model picks tools, `bl/tools.py` answers with
arithmetic, and the results go back for the next turn until the model has
what it needs to speak. What the model contributes is *which question to ask*
and *how to say the answer in Hebrew*. What it never contributes is a number,
a name, or a verdict — those come from the tools, and the prompt forbids
claiming a placement is valid unless a tool said so
([D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).

## It answers; it does not act

Every tool in the loop is read-only, and this module is handed no repository
of its own — it holds a `ScheduleTools`, which reads. There is no operation
in the response schema, so there is nothing here `apply()` could consume.
That is the same shape `bl/briefing.py` has and for the same reason: a
proactive or exploratory surface that could write would reverse D3, D8 and
D12 at once
([D15](../../../docs/DECISIONS.md#d15--the-agent-speaks-first-but-still-never-writes)).

Asking a question and making a change stay two different flows. When the
answer is *"רון could take it"*, the manager acts on that by sending the
change through `propose()` and confirming it with their reason, exactly as
before.

## Without a model it still works

`answer()` falls back to `bl/intent.py` the moment the model is unreachable
or unconfigured — and `README.md` promises the product works without an LLM,
so this is a supported path rather than an error path. The fallback reads the
sentence with keyword matching, runs the *same tools*, and renders the
results with Hebrew sentence templates.

What is lost is real and is not disguised: the deterministic reader handles
seven question shapes and says plainly that it did not understand anything
else. What is kept is the part that matters — the answer's *content* is
identical either way, because the content was never the model's to begin
with. The model was writing the sentence around it.
"""

import json
from typing import Any, Dict, List, Optional

from app.bl import intent as intent_reader
from app.bl.prompts import load
from app.bl.tools import (
    TOOL_COVERAGE_GAPS,
    TOOL_DESCRIPTIONS,
    TOOL_EMPLOYEE_STATE,
    TOOL_FIND_REPLACEMENTS,
    TOOL_NAMES,
    TOOL_PUBLISH_READINESS,
    TOOL_READ_PERIOD,
    TOOL_TEAM_OVERVIEW,
)
from app.common.errors import AgentError
from app.common.time_context import israel_today

_MAX_TEXT_CHARS = 4000

# How many model turns one question may cost. Three is enough for the deepest
# real chain -- find the period, find the person's shift in it, find who could
# take that shift -- and a bound is what stops a model that keeps asking for
# one more tool from spending a manager's afternoon.
_MAX_TURNS = 3

# How many tools may run in a single turn. Bounded because the model names
# them and an unbounded list is an unbounded number of repository reads.
_MAX_CALLS_PER_TURN = 4

_TOOL_CALL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["tool", "arguments"],
    "properties": {
        "tool": {"type": "string", "enum": list(TOOL_NAMES)},
        "arguments": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "employee": {"type": "string"},
                "shift_name": {"type": "string"},
                "slot_date": {"type": "string"},
                "day": {"type": "string"},
                "starts_on": {"type": "string"},
                "ends_on": {"type": "string"},
                "timezone": {"type": "string"},
                "schedule_id": {"type": "string"},
                "moving_assignment_id": {"type": "string"},
            },
        },
    },
}

PLANNER_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "done", "answer", "tool_calls", "needs_confirmation", "needs_input",
    ],
    "properties": {
        # The model's own statement that it has what it needs. Bounded in
        # code by `_MAX_TURNS` regardless, so a model that never sets it
        # still terminates.
        "done": {"type": "boolean"},
        "answer": {"type": "string"},
        "tool_calls": {
            "type": "array",
            "items": _TOOL_CALL_SCHEMA,
            "maxItems": _MAX_CALLS_PER_TURN,
        },
        # True when what is being described *would* change the schedule, so
        # the manager is told plainly that nothing has happened yet. It is a
        # label on a sentence, not a queued operation -- there is no
        # operation anywhere in this schema.
        "needs_confirmation": {"type": "boolean"},
        # An ambiguous request is not a failed answer. It is one focused
        # question that keeps the conversation moving without guessing.
        "needs_input": {"type": "boolean"},
    },
}


class PlanningAgent:
    """A manager's question, answered by running read-only tools."""

    def __init__(self, llm, tools):
        self._llm = llm
        self._tools = tools

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
        reached — including when none is configured at all. The fallback is
        marked in the result (`used_model: False`) rather than hidden: a
        manager whose answer came from keyword matching should be able to
        tell, because its coverage is narrower and saying so is what keeps
        the narrower coverage honest.

        `pending_request` is the question a previous turn asked about. When
        it is set, `request` is the *answer* to a clarification rather than a
        new question, and the two are read together — "ערב" alone says
        nothing, and making the manager retype the whole sentence is the
        interaction this exists to avoid.
        """
        text = _bounded(request)
        if not text:
            raise AgentError("הבקשה אינה יכולה להיות ריקה")

        pending = _bounded(pending_request)
        resolved = _resume(pending, text)

        try:
            return self._with_model(
                team_id, resolved, profile, period, preferences,
                pending=pending, reply=text if pending else "",
            )
        except AgentError:
            # Unconfigured, unreachable, or answering with unusable JSON.
            # All three mean the same thing here: answer without it.
            return self.without_model(team_id, resolved, profile, period)

    # -- with a model ------------------------------------------------------

    def _with_model(
        self,
        team_id: str,
        request: str,
        profile: dict,
        period: Optional[dict],
        preferences: Optional[List[dict]],
        pending: str = "",
        reply: str = "",
    ) -> dict:
        """The tool loop. Model picks, tools answer, repeat until done."""
        results: List[dict] = []
        steps: List[dict] = []
        answer = ""
        needs_confirmation = False
        needs_input = False

        for _ in range(_MAX_TURNS):
            turn = self._ask({
                "profile": _profile_for_model(profile),
                "period": _period_for_model(period),
                "preferences": _preferences_for_model(preferences),
                "tools": [
                    {"name": name, "purpose": TOOL_DESCRIPTIONS[name]}
                    for name in TOOL_NAMES
                ],
                "results": results,
                "request": request,
                # What the manager was asked last turn and what they said
                # back. Handed over so the model continues that request
                # rather than re-asking it -- a model that cannot see it
                # answered has no way to tell a clarification from a new
                # question, and asking twice is the loop this prevents.
                "asked_last_turn": pending,
                "answer_to_that": reply,
            })

            answer = _bounded(turn.get("answer")) or answer
            needs_confirmation = bool(turn.get("needs_confirmation"))
            needs_input = bool(turn.get("needs_input"))
            calls = _calls(turn.get("tool_calls"))

            if not calls or turn.get("done"):
                break

            for call in calls:
                outcome = self._tools.run(team_id, call["tool"], call["arguments"])
                results.append(outcome)
                steps.append({
                    "tool": call["tool"],
                    "arguments": call["arguments"],
                    "ok": bool(outcome.get("ok", True)),
                })

        return {
            "answer": answer or "לא הצלחתי להרכיב תשובה על סמך מה שבדקתי.",
            # What was actually run, so the manager can see which facts the
            # answer rests on. Transparency is a product requirement here,
            # not debugging output -- an answer whose checks are invisible is
            # one the manager has to take on faith.
            "steps": steps,
            "results": results,
            "needs_confirmation": needs_confirmation,
            "needs_input": needs_input,
            # Carried back only while a question is open, so the client has
            # nothing stale to echo once the answer has landed.
            "pending_request": request if needs_input else "",
            "used_model": True,
            "understood": True,
        }

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
            # `OpenAIJsonClient` already guarantees `AgentError`, but keeping
            # that contract here protects the boss assistant when a custom
            # compatible adapter fails during setup. `answer()` can then use
            # its deterministic tools instead of returning HTTP 500.
            raise AgentError("המודל לא זמין כרגע") from exc
        if not isinstance(answer, dict):
            raise AgentError("המודל החזיר תשובה לא תקינה")
        return answer

    # -- without a model ---------------------------------------------------

    def without_model(
        self,
        team_id: str,
        request: str,
        profile: dict,
        period: Optional[dict] = None,
    ) -> dict:
        """The same tools, chosen by keyword rather than by a model.

        The product's floor. `bl/intent.py` places the sentence into one of
        seven shapes, this maps each shape onto the tools that answer it, and
        the results are rendered with Hebrew templates.

        A sentence it cannot place comes back `understood: False` with a list
        of what it *can* answer. That is deliberately not a guess: an agent
        that acts on a misread sentence with no model to blame is worse than
        one that says it did not follow.
        """
        roster = [_text(row.get("name")) for row in _employees(profile)]
        shift_names = [_text(row.get("name")) for row in _shifts(profile)]
        read = intent_reader.read(
            request, roster=roster, shift_names=shift_names,
            today=israel_today().isoformat(), period=period,
        )

        handler = {
            intent_reader.INTENT_REPLACEMENTS: self._fallback_replacements,
            intent_reader.INTENT_ABSENCE: self._fallback_replacements,
            intent_reader.INTENT_GAPS: self._fallback_gaps,
            intent_reader.INTENT_EMPLOYEE: self._fallback_employee,
            intent_reader.INTENT_PUBLISH: self._fallback_publish,
            intent_reader.INTENT_PERIOD: self._fallback_period,
            intent_reader.INTENT_TEAM: self._fallback_team,
        }.get(read["intent"])

        if handler is None:
            return {
                "answer": _NOT_UNDERSTOOD,
                "steps": [],
                "results": [],
                "needs_confirmation": False,
                "needs_input": True,
                # Nothing to resume: the sentence was never placed, so there
                # is no intent for an answer to continue. Echoing it back
                # would make the next turn read as a clarification of a
                # request that was never understood in the first place.
                "pending_request": "",
                "used_model": False,
                "understood": False,
                "intent": read["intent"],
            }

        answer, steps, results, needs_confirmation = handler(team_id, read)
        asking = _is_question(answer)
        return {
            "answer": answer,
            "steps": steps,
            "results": results,
            "needs_confirmation": needs_confirmation,
            "needs_input": asking,
            "pending_request": request if asking else "",
            "used_model": False,
            "understood": True,
            "intent": read["intent"],
        }

    def _fallback_replacements(self, team_id: str, read: dict) -> tuple:
        """Who could take the shift the absent person holds.

        Two tools in sequence, which is the same chain the model would run:
        find the person's rows for that day, then ask for candidates for each
        one. Doing it in code here rather than describing it to a model is
        what makes this path work with nothing configured.
        """
        employee = read["employee"]
        date = read["date"]
        steps: List[dict] = []
        results: List[dict] = []

        if not employee:
            return (
                "לא זיהיתי על מי מדובר. אפשר לכתוב את השם כפי שהוא מופיע "
                "ברשימת הצוות?",
                steps, results, False,
            )

        state = self._tools.run(
            team_id, TOOL_EMPLOYEE_STATE, {"employee": employee, "day": date},
        )
        steps.append({"tool": TOOL_EMPLOYEE_STATE, "arguments": {
            "employee": employee, "day": date}, "ok": bool(state.get("ok"))})
        results.append(state)

        if not state.get("found"):
            return (
                _text(state.get("reason")) or "לא מצאתי את העובד/ת הזה/הזאת.",
                steps, results, False,
            )

        shifts = [
            row for row in state.get("shifts") or []
            if not date or row.get("date") == date
        ]
        if not shifts:
            when = " ב-%s" % date if date else " בתקופה הזאת"
            return (
                "ל%s אין משמרות%s, אז אין את מי להחליף." % (employee, when),
                steps, results, False,
            )

        lines = []
        for row in shifts:
            found = self._tools.run(team_id, TOOL_FIND_REPLACEMENTS, {
                "employee": employee,
                "shift_name": row["shift"],
                "slot_date": row["date"],
            })
            steps.append({"tool": TOOL_FIND_REPLACEMENTS, "arguments": {
                "employee": employee, "shift_name": row["shift"],
                "slot_date": row["date"]}, "ok": bool(found.get("ok"))})
            results.append(found)

            candidates = found.get("candidates") or []
            if not candidates:
                lines.append(
                    "· %s ב-%s: לא נמצא מי שיכול/ה לקחת בלי ליצור אזהרה."
                    % (row["shift"], row["date"])
                )
                continue
            names = "‏, ".join(
                "%s (%s שעות)" % (item["employee"], _pretty(item["hours"]))
                for item in candidates
            )
            lines.append(
                "· %s ב-%s: %s — לפי הסדר, הקל/ה בשעות ראשון/ה."
                % (row["shift"], row["date"], names)
            )

        opening = (
            "בדקתי מי יכול/ה להחליף את %s. כל מי שמופיע כאן נבדק מול "
            "האילוצים, ההסמכות והשעות — ומי שהשיבוץ היה יוצר אצלו/ה אזהרה "
            "לא נכלל." % employee
        )
        closing = "כדי לבצע החלפה צריך לשלוח את הבקשה ולאשר אותה עם סיבה."
        return ("\n".join([opening] + lines + [closing]), steps, results, True)

    def _fallback_gaps(self, team_id: str, read: dict) -> tuple:
        date = read["date"]
        arguments = {"starts_on": date, "ends_on": date} if date else {}
        found = self._tools.run(team_id, TOOL_COVERAGE_GAPS, arguments)
        steps = [{"tool": TOOL_COVERAGE_GAPS, "arguments": arguments,
                  "ok": bool(found.get("ok"))}]

        if not found.get("found"):
            return (_text(found.get("reason")) or "אין סידור מאוחסן.",
                    steps, [found], False)

        gaps = found.get("gaps") or []
        if not gaps:
            return ("כל המשמרות בתקופה מאוישות במלואן.",
                    steps, [found], False)

        lines = [
            "· %s ב-%s: חסרים %d מתוך %d."
            % (row["shift"], row["date"], row["missing"], row["headcount"])
            for row in gaps
        ]
        opening = "חסרים %d שיבוצים ב-%d משמרות:" % (
            found.get("people_short", 0), found.get("total_gaps", 0),
        )
        return ("\n".join([opening] + lines), steps, [found], False)

    def _fallback_employee(self, team_id: str, read: dict) -> tuple:
        employee = read["employee"]
        if not employee:
            # The sentence was placed as a question about one person without
            # naming one the roster carries. Asking is the only honest move:
            # `employee_state` with an empty name raises, and picking
            # somebody to ask about is the guess this path must not make.
            return (
                "על מי מהצוות תרצו לשמוע?",
                [], [], False,
            )
        found = self._tools.run(
            team_id, TOOL_EMPLOYEE_STATE,
            {"employee": employee, "day": read["date"]},
        )
        steps = [{"tool": TOOL_EMPLOYEE_STATE,
                  "arguments": {"employee": employee}, "ok": bool(found.get("ok"))}]

        if not found.get("found"):
            return (_text(found.get("reason")) or "לא מצאתי את העובד/ת.",
                    steps, [found], False)

        shifts = found.get("shifts") or []
        lines = [
            "ל%s יש %d משמרות בתקופה, בסך הכל %s שעות."
            % (employee, len(shifts), _pretty(found.get("hours", 0.0)))
        ]
        lines.extend(
            "· %s ב-%s" % (row["shift"], row["date"]) for row in shifts
        )
        constraints = found.get("constraints") or []
        if constraints:
            lines.append("אילוצים רשומים: %d." % len(constraints))
        warnings = found.get("warnings") or []
        if warnings:
            lines.append("אזהרות פתוחות: %d." % len(warnings))
        return ("\n".join(lines), steps, [found], False)

    def _fallback_publish(self, team_id: str, read: dict) -> tuple:
        found = self._tools.run(team_id, TOOL_PUBLISH_READINESS, {})
        steps = [{"tool": TOOL_PUBLISH_READINESS, "arguments": {},
                  "ok": bool(found.get("ok"))}]

        if not found.get("found"):
            return (_text(found.get("reason")) or "אין סידור מאוחסן.",
                    steps, [found], False)

        blockers = found.get("blockers") or []
        if not blockers:
            return ("לא מצאתי שום דבר פתוח — התקופה מוכנה לפרסום.",
                    steps, [found], False)
        lines = ["לפני פרסום שווה לשים לב:"] + ["· " + row for row in blockers]
        # Said outright because the audit never gates (D3): the manager may
        # publish over every one of these, and a list that read as a
        # checklist would imply otherwise.
        lines.append("אפשר לפרסם גם ככה — אלה הערות, לא חסימות.")
        return ("\n".join(lines), steps, [found], False)

    def _fallback_period(self, team_id: str, read: dict) -> tuple:
        found = self._tools.run(team_id, TOOL_READ_PERIOD, {"day": read["date"]})
        steps = [{"tool": TOOL_READ_PERIOD, "arguments": {"day": read["date"]},
                  "ok": bool(found.get("ok"))}]

        if not found.get("found"):
            return (_text(found.get("reason")) or "אין סידור מאוחסן.",
                    steps, [found], False)

        period = found.get("schedule") or {}
        warnings = found.get("warnings") or []
        lines = [
            "התקופה %s – %s, בסטטוס %s."
            % (period.get("starts_on"), period.get("ends_on"),
               "פורסם" if period.get("status") == "published" else "טיוטה"),
            "יש בה %d משמרות ו-%d שיבוצים."
            % (period.get("slot_count", 0), period.get("assignment_count", 0)),
        ]
        if warnings:
            lines.append("אזהרות פתוחות: %d." % len(warnings))
        return ("\n".join(lines), steps, [found], False)

    def _fallback_team(self, team_id: str, read: dict) -> tuple:
        found = self._tools.run(team_id, TOOL_TEAM_OVERVIEW, {})
        steps = [{"tool": TOOL_TEAM_OVERVIEW, "arguments": {},
                  "ok": bool(found.get("ok"))}]
        if not found.get("found"):
            return (_text(found.get("reason")) or "לא הוגדרו פרטי צוות.",
                    steps, [found], False)

        employees = found.get("employees") or []
        lines = ["בצוות יש %d עובדים ועובדות:" % len(employees)]
        lines.extend(
            "· %s%s" % (
                row.get("name", ""),
                " — " + row["role"] if row.get("role") else "",
            )
            for row in employees
        )
        shifts = found.get("shifts") or []
        if shifts:
            lines.append("סוגי המשמרות שהוגדרו: %s." % ", ".join(
                row.get("name", "") for row in shifts if row.get("name")
            ))
        rules = [
            _text(row.get("text") or row.get("rule"))
            if isinstance(row, dict) else _text(row)
            for row in found.get("rules") or []
        ]
        rules = [row for row in rules if row]
        if rules:
            lines.append("כללים שנרשמו:")
            lines.extend("· " + row for row in rules)
        return ("\n".join(lines), steps, [found], False)


# What the deterministic reader says when it could not place a sentence.
# Lists what it *can* do rather than apologising: a manager told only "I did
# not understand" has no way to find the sentence that would have worked.
_NOT_UNDERSTOOD = (
    "אני רוצה לדייק ולא לנחש. מה תרצו לברר קודם — מחליף לעובד/ת, "
    "מידע על הצוות, חוסרים בסידור, שעות של עובד/ת, או מוכנות לפרסום?"
)


def _resume(pending: str, reply: str) -> str:
    """The original request and the manager's clarification, read as one.

    Joined rather than replaced. "ערב" is not a request and never was — it
    is the missing half of one, and dropping the half that carried the verb
    is how a clarification turns into a new, emptier question.

    Kept as plain text rather than a parsed intent structure: the sentence
    is what both the model and `bl/intent.py` already read, and a second
    representation of the same request is a second thing to keep in sync.
    """
    pending = _bounded(pending)
    reply = _bounded(reply)
    if not pending:
        return reply
    if not reply:
        return pending
    # An answer that already restates the request is not appended to itself.
    if pending in reply:
        return reply
    return "%s (%s)" % (pending, reply)


def _is_question(value: str) -> bool:
    return _text(value).endswith(("?", "؟"))


def _calls(offered: Any) -> List[dict]:
    """Tool calls the model asked for, bounded to ones that exist."""
    if not isinstance(offered, list):
        return []
    calls = []
    for item in offered[:_MAX_CALLS_PER_TURN]:
        if not isinstance(item, dict):
            continue
        name = _text(item.get("tool"))
        if name not in TOOL_NAMES:
            continue
        arguments = item.get("arguments")
        calls.append({
            "tool": name,
            "arguments": arguments if isinstance(arguments, dict) else {},
        })
    return calls


def _profile_for_model(profile: dict) -> dict:
    """The workplace as the planner reads it.

    The roster and the vocabulary, not the whole period — the tools are what
    fetch schedule rows, and including them here would put back the wall of
    JSON that having tools was meant to remove.
    """
    profile = profile if isinstance(profile, dict) else {}
    return {
        "workplace": profile.get("workplace") or {},
        "employees": profile.get("employees") or [],
        "shifts": profile.get("shifts") or [],
        "rules": profile.get("rules") or [],
    }


def _period_for_model(period: Optional[dict]) -> dict:
    if not isinstance(period, dict):
        return {}
    return {
        "id": _text(period.get("id")),
        "starts_on": _iso(period.get("starts_on")),
        "ends_on": _iso(period.get("ends_on")),
        "status": _text(period.get("status")),
    }


def _preferences_for_model(preferences: Optional[List[dict]]) -> List[dict]:
    """Active preferences as context. Never as instructions.

    Handed over as reported speech — what the manager has said they prefer —
    for the same reason `bl/learn.py` hands over imported cell contents that
    way. A preference is a standing wish, and a standing wish never
    authorises a write: the confirmation step is unchanged by anything in
    this list.
    """
    rows = []
    for row in preferences or []:
        if not isinstance(row, dict):
            continue
        rows.append({
            "kind": _text(row.get("kind")),
            "subject": _text(row.get("subject")),
            "text": _bounded(row.get("text")),
        })
    return rows[:40]


def _employees(profile: dict) -> List[dict]:
    rows = (profile or {}).get("employees")
    return [row for row in rows or [] if isinstance(row, dict)]


def _shifts(profile: dict) -> List[dict]:
    rows = (profile or {}).get("shifts")
    return [row for row in rows or [] if isinstance(row, dict)]


def _pretty(hours: Any) -> str:
    try:
        return "%g" % round(float(hours), 1)
    except (TypeError, ValueError):
        return "0"


def _iso(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return _text(value)


def _bounded(value: Any, limit: int = _MAX_TEXT_CHARS) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


__all__ = ["PlanningAgent", "PLANNER_RESPONSE_SCHEMA"]
