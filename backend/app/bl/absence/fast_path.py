"""Finishing an absence turn in code, before the model is asked anything.

"עודד חולה בשני ושלישי", "עודד טס לחו"ל", "ירין לא יכולה לעבוד בשישי":
these are the most common things a manager types, and each one used to cost
three or four full model rounds -- the whole profile, period and transcript
re-sent every time -- to arrive at what code can work out directly: the
person, the dates, their shifts, and who is free to cover them.

**Nothing here writes, and nothing here is a second way to plan.** The
plan is built by handing `ChatPlanBuilder.prepare` the same turn the model
would have returned, so it passes every check and audit a model plan does
and waits for the same approval. Anything this cannot read with certainty
returns `False` and the model takes the turn exactly as before.
"""

import copy
import datetime
import json
import logging

from app.bl.absence import reader
from app.bl.absence.dates import dates_in
from app.bl.absence.options import AbsenceOptions, absence_constraints
from app.bl.absence.replies import (
    ask_dates, ask_scope, plan_reply, recurring_reply,
)
from app.bl.absence.selections import selections
from app.bl.chat.contract import NeedsManager, RejectedPlan
from app.bl.intent.vocabulary import WEEKDAYS
from app.bl.planner.shaping import plain_question
from app.common.errors import AppError
from app.common.time_context import israel_today

_log = logging.getLogger("pakash.chat")
_FOLLOW_UPS = ("absence_dates", "absence_scope")


def _turn(kind, reply, request, **fields):
    """A model-shaped turn, so the plan goes through the model's own checks."""
    turn = dict(
        kind=kind, reply=reply, agent_reason=reply, stated_reason=request,
        needs_reason=False, needs_input=False, operations=[], constraints=[],
        profile_operations=[], exceptions=[], schedule_id="", profile_patch_json="",
        starts_on="", ends_on="", instructions="", replace_existing=False,
        question=None, tool_calls=[],
    )
    turn.update(fields)
    return turn


class AbsenceFastPath:
    def __init__(self, repository, context, planner):
        self._repo = repository
        self._context = context
        self._planner = planner
        self._options = AbsenceOptions(repository, context)

    def handle(self, state) -> bool:
        """Finish this turn without a model round, or return False untouched."""
        try:
            read, chosen = self._read(state)
            if read is None:
                return False
            handlers = {
                "ask_dates": self._ask_dates, "ask_scope": self._ask_scope,
                "recurring": self._recurring, "dates": self._absence,
            }
            return handlers[read["scope"]](state, read, chosen)
        except (NeedsManager, RejectedPlan, AppError) as exc:
            # A plan code could not settle is the model's to work out: it
            # sees the same request with nothing lost.
            _log.info("absence fast path declined: %s", exc)
            return False
        except Exception:
            # A shortcut must never cost the manager the answer: whatever
            # broke here, the ordinary model turn still runs.
            _log.exception("absence fast path failed; using the model")
            return False

    def _read(self, state):
        profile = state.profile
        roster = [row.get("name") or "" for row in profile.get("employees") or []]
        shifts = [row.get("name") or "" for row in profile.get("shifts") or []]
        week = state.context.get("visible_week") or ""
        today = israel_today().isoformat()
        task = _previous_task(state)
        chosen = selections(state.request)
        read = reader.read(state.request, roster, shifts, today, week)
        if task.get("kind") in _FOLLOW_UPS and not (read and read["dates"]) \
                and dates_in(state.request, today, week) \
                and not any(name and name in state.request for name in roster):
            # "מ-1.11 עד 5.11" answering "when?" continues the sentence it answers.
            read = reader.read(task["request"] + " " + state.request, roster, shifts, today, week)
            if read and read["scope"] == "ask_dates":
                return None, []
        if task.get("kind") == "absence" and chosen and not (read and read["dates"]):
            read = dict(employee=task["employee"], dates=task["dates"],
                        request=task["request"], scope="dates", weekdays=[])
        if read and task.get("kind") == "absence" and read["employee"] == task.get("employee") \
                and read["dates"] == task.get("dates"):
            # Earlier choices stand unless this message re-chooses the slot.
            again = {(row["date"], row["shift"]) for row in chosen}
            chosen = [row for row in task.get("chosen") or []
                      if (row["date"], row["shift"]) not in again] + chosen
        return read, chosen

    def _ask_dates(self, state, read, chosen):
        question = ask_dates(read["employee"])
        self._finish(state, question, "complete", dict(
            question=plain_question(question),
            task=dict(kind="absence_dates", request=read["request"]),
        ))
        return True

    def _ask_scope(self, state, read, chosen):
        question = ask_scope(read["employee"], read["dates"][0], read["weekdays"][0])
        self._finish(state, question["question"], "complete", dict(
            question=question,
            task=dict(kind="absence_scope", request=read["request"]),
        ))
        return True

    def _absence(self, state, read, chosen):
        employee, dates, request = read["employee"], read["dates"], read["request"]
        found = self._options.build(state.team_id, employee, dates, chosen, reason=request)
        if found["error"]:
            return False
        operations = []
        for slot in found["slots"]:
            operations.append(dict(action="remove", employee=employee, shift=slot["shift"],
                                   date=slot["date"], reason=request))
            if slot["pick"]:
                operations.append(dict(action="assign", employee=slot["pick"], shift=slot["shift"],
                                       date=slot["date"], reason=_assign_reason(slot)))
        reply, agent_reason = plan_reply(employee, dates, found)
        turn = _turn("changes", reply, request, agent_reason=agent_reason,
                     operations=operations, schedule_id=found["schedule_id"],
                     constraints=absence_constraints(employee, dates, request))
        # Every assignment here is either the manager's own pick or the
        # ranked choice they are about to approve on the plan card.
        picks = [slot["pick"] for slot in found["slots"] if slot["pick"]]
        plan = self._planner.prepare(state.team_id, turn, found["schedule_id"] or state.schedule_id,
                                     request, picks)
        if plan is None:
            return False
        task = dict(kind="absence", request=request, employee=employee, dates=dates,
                    chosen=[dict(date=slot["date"], shift=slot["shift"], employee=slot["pick"])
                            for slot in found["slots"] if slot["picked_by"] == "manager"])
        steps = [{"tool": "find_replacements", "ok": True} for _ in found["results"]]
        self._finish(state, reply, "pending", dict(
            plan=plan, results=found["results"], steps=steps, task=task,
            absence=dict(slots=found["slots"], free_dates=found["free_dates"]),
        ))
        return True

    def _recurring(self, state, read, chosen):
        employee, request = read["employee"], read["request"]
        employees = copy.deepcopy(state.profile.get("employees") or [])
        person = next(row for row in employees if row.get("name") == employee)
        rule = dict(days=read["weekdays"], shifts=[], available=False, is_hard=True,
                    start_time="", end_time="", reason=request)
        person["recurring_constraints"] = list(person.get("recurring_constraints") or []) + [rule]
        reply = recurring_reply(employee, read["weekdays"], self._upcoming(state, employee, read))
        turn = _turn("profile", reply, request,
                     profile_patch_json=json.dumps(dict(employees=employees), ensure_ascii=False))
        plan = self._planner.prepare(state.team_id, turn, state.schedule_id, request)
        if plan is None:
            return False
        self._finish(state, reply, "pending", dict(plan=plan))
        return True

    def _upcoming(self, state, employee, read):
        """Shifts already on the board that the new standing rule now covers;
        named in the reply, never moved by a profile plan."""
        wanted = {WEEKDAYS[name] for name in read["weekdays"]}
        today = israel_today().isoformat()
        rows = []
        for row in (state.payload.get("schedule") or {}).get("assignments") or []:
            date = str(row.get("date") or "")[:10]
            if row.get("employee") != employee or date < today:
                continue
            if (datetime.date.fromisoformat(date).weekday() + 1) % 7 in wanted:
                rows.append(dict(date=date, shift=row.get("shift") or ""))
        return rows

    def _finish(self, state, reply, status, output):
        output.setdefault("steps", [])
        output.setdefault("results", [])
        output.setdefault("question", None)
        output["fast_path"] = "absence"
        output["_usage"] = dict(prompt_tokens=0, completion_tokens=0, total_tokens=0,
                                model_rounds=0)
        self._repo.finish_chat_turn(
            state.chat_id, state.message_id, reply, status,
            json.loads(json.dumps(output, ensure_ascii=False, default=str)),
        )
        _log.info("chat usage rounds=0 prompt=0 completion=0 total=0 fast_path=absence")


def _previous_task(state) -> dict:
    """What the agent's last answer left open: the question it asked, or the
    absence plan it offered, so a click or a short answer continues it."""
    for row in reversed(state.payload.get("conversation") or []):
        if row.get("role") == "assistant":
            task = (row.get("context") or {}).get("task")
            return task if isinstance(task, dict) else {}
    return {}


def _assign_reason(slot: dict) -> str:
    if slot["picked_by"] == "manager":
        return "בחירת המנהל להחלפת %s" % slot["replacing"]
    chosen = next((row for row in slot["candidates"] if row["employee"] == slot["pick"]), {})
    return "מחליף/ה את %s; העומס הנמוך ביותר מבין המתאימים: %s" % (
        slot["replacing"], chosen.get("why") or "נבדק מול כל הכללים")
