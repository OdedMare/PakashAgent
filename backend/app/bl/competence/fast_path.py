"""Finishing a competence turn in code, before the model is asked anything.

Nothing here writes. A change is a `profile` plan naming only `competence`
on the people it touches, prepared by `ChatPlanBuilder.prepare` and applied
on the manager's approval like any other. A step from no rating, or past
either end, is answered with a reply rather than a guess.
"""

import json
import logging

from app.bl.absence.fast_path import _previous_task, _turn
from app.bl.chat.contract import NeedsManager, RejectedPlan
from app.bl.competence import reader
from app.bl.competence.reader import LABELS
from app.bl.planner.shaping import plain_question
from app.common.errors import AppError

_log = logging.getLogger("pakash.chat")
_ASK = "לא הוגדרה רמה מקצועית ל%s. לאיזו רמה לקבוע? חלשה, בינונית, גבוהה או מצטיינת."


class CompetenceFastPath:
    def __init__(self, repository, planner):
        self._repo = repository
        self._planner = planner

    def handle(self, state) -> bool:
        """Finish this turn without a model round, or return False untouched."""
        try:
            people = {row.get("name") or "": row for row in state.profile.get("employees") or []}
            read = self._read(state, list(people))
            if read is None:
                return False
            return self._answer(state, read, people)
        except (NeedsManager, RejectedPlan, AppError) as exc:
            _log.info("competence fast path declined: %s", exc)
            return False
        except Exception:
            _log.exception("competence fast path failed; using the model")
            return False

    def _read(self, state, roster):
        read = reader.read(state.request, roster)
        if read is not None:
            return read
        task = _previous_task(state)
        level = reader.level_in(state.request)
        if task.get("kind") == "competence_level" and level is not None:
            # "גבוהה" answering "to which level?" continues the request.
            return dict(names=[name for name in task.get("names") or [] if name in roster],
                        level=level, request=task.get("request") or state.request)
        return None

    def _answer(self, state, read, people):
        if not read["names"]:
            return False
        changes, unrated, held = {}, [], []
        for name in read["names"]:
            current = people[name].get("competence") or ""
            target = read["level"] if "level" in read else reader.shifted(current, read["step"])
            if target is None:
                (unrated if not current else held).append(name)
            elif target != current:
                changes[name] = (current, target)
        if unrated:
            return self._ask(state, unrated, read)
        if not changes:
            return self._finish(state, _unchanged(read, held, people), "complete", {})
        return self._plan(state, changes, read.get("request") or state.request, held)

    def _ask(self, state, names, read):
        who = " ו".join(names)
        question = dict(plain_question(_ASK % who), options=[
            {"label": LABELS[level], "answer": "קבע רמה מקצועית %s ל%s" % (LABELS[level], who)}
            for level in reader.LEVELS
        ])
        return self._finish(state, question["question"], "complete", dict(
            question=question,
            task=dict(kind="competence_level", names=names, request=state.request),
        ))

    def _plan(self, state, changes, request, held):
        lines = ["%s: מ%s ל%s" % (name, LABELS[before], LABELS[after])
                 for name, (before, after) in changes.items()]
        reply = "עדכון רמה מקצועית — %s. הבנייה הבאה תאזן את המשמרות לפי הרמה המקצועית החדשה." % "; ".join(lines)
        if held:
            reply += " %s כבר ברמה הקיצונית ולא שונו." % ", ".join(held)
        patch = dict(employees=[dict(name=name, competence=after)
                                for name, (_, after) in changes.items()])
        turn = _turn("profile", reply, request,
                     profile_patch_json=json.dumps(patch, ensure_ascii=False))
        plan = self._planner.prepare(state.team_id, turn, state.schedule_id, request)
        if plan is None:
            return False
        return self._finish(state, reply, "pending", dict(plan=plan))

    def _finish(self, state, reply, status, output):
        output.setdefault("steps", [])
        output.setdefault("results", [])
        output.setdefault("question", None)
        output["fast_path"] = "competence"
        output["_usage"] = dict(prompt_tokens=0, completion_tokens=0, total_tokens=0,
                                model_rounds=0)
        self._repo.finish_chat_turn(
            state.chat_id, state.message_id, reply, status,
            json.loads(json.dumps(output, ensure_ascii=False, default=str)),
        )
        _log.info("chat usage rounds=0 prompt=0 completion=0 total=0 fast_path=competence")
        return True


def _unchanged(read, held, people) -> str:
    if held:
        edge = "הגבוהה ביותר" if read.get("step", 0) > 0 else "הנמוכה ביותר"
        return "הרמה המקצועית של %s כבר %s." % (", ".join(held), edge)
    name = read["names"][0]
    return "הרמה המקצועית של %s כבר %s." % (", ".join(read["names"]),
                                       LABELS[people[name].get("competence") or ""])
