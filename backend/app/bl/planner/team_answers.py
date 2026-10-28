"""Template answers to the team questions a manager asks most: who works,
who carried the most, who is away. Each runs one range tool and renders it.

Returns `(answer, steps, results, needs_confirmation)`, like
`fallback_answers.py`, so the chat's fast path and the no-model fallback can
share them.
"""

from typing import List

from app.bl.planner.shaping import pretty, text
from app.bl.planner.trace import ToolTrace
from app.bl.tools import TOOL_WHO_IS_AWAY, TOOL_WHO_WORKS, TOOL_WORKLOAD_RANKING

_MAX_LINES = 60


def _count(number: int, one: str, many: str) -> str:
    return one if number == 1 else "%d %s" % (number, many)


def _when(first: str, last: str) -> str:
    return "ב-%s" % first if first == last else "בין %s ל-%s" % (first, last)


class TeamAnswers:
    def __init__(self, tools):
        self._tools = tools

    def who_works(self, team_id: str, read: dict) -> tuple:
        trace = ToolTrace(self._tools, team_id)
        arguments = {"starts_on": read["starts_on"], "ends_on": read["ends_on"]}
        if read.get("shift"):
            arguments["shift_name"] = read["shift"]
        found = trace.run(TOOL_WHO_WORKS, arguments)
        when = _when(read["starts_on"], read["ends_on"])
        if not found.get("ok") or not found.get("found"):
            return trace.reply("%s: %s." % (when, text(found.get("reason") or found.get("error"))
                                             or "אין שיבוצים"))
        lines = ["%s משובצים %d אנשים%s:" % (
            when, found["people_count"], " ב" + read["shift"] if read.get("shift") else "")]
        for day in found["days"]:
            if found["starts_on"] != found["ends_on"]:
                lines.append("**%s**" % day["date"])
            lines += ["· %s: %s" % (row["shift"], ", ".join(row["employees"]))
                      for row in day["shifts"]]
        return trace.reply("\n".join(_bounded(lines)))

    def workload(self, team_id: str, read: dict) -> tuple:
        trace = ToolTrace(self._tools, team_id)
        arguments = {"starts_on": read["starts_on"], "ends_on": read["ends_on"],
                     "commanders_only": read.get("commanders_only", False)}
        for key, value in (("shift_name", read.get("shift")), ("role", read.get("role"))):
            if value:
                arguments[key] = value
        found = trace.run(TOOL_WORKLOAD_RANKING, arguments)
        when = _when(read["starts_on"], read["ends_on"])
        if not found.get("ok") or not found.get("found"):
            return trace.reply(text(found.get("reason") or found.get("error"))
                               or "לא מצאתי את מי לדרג.")
        scope = " ".join(part for part in (
            "מבין מפקדי המשמרת" if found.get("commanders_only") else "",
            "בתפקיד %s" % found["role"] if found.get("role") else "",
            "במשמרת %s" % found["shift_name"] if found.get("shift_name") else "",
        ) if part)
        scope = " " + scope if scope else ""
        if read.get("fewest"):
            return trace.reply("הכי מעט משמרות%s %s: %s (%s). נבדקו %d אנשים."
                               % (scope, when, ", ".join(found["least"]),
                                  _count(found["least_shifts"], "משמרת אחת", "משמרות"),
                                  found["considered"]))
        lines = ["הכי הרבה משמרות%s %s:" % (scope, when)] + [
            "%d. %s — %s, %s שעות, %s"
            % (index, row["employee"], _count(row["shifts"], "משמרת אחת", "משמרות"),
               pretty(row["hours"]), _count(row["nights"], "לילה אחד", "לילות"))
            for index, row in enumerate(found["ranking"], 1)
        ]
        if len(found["tied_for_most"]) > 1:
            lines.append("במקום הראשון בתיקו: %s." % ", ".join(found["tied_for_most"]))
        lines.append("לפי השיבוצים בסידור, לא לפי נוכחות בפועל.")
        return trace.reply("\n".join(lines))

    def away(self, team_id: str, read: dict) -> tuple:
        trace = ToolTrace(self._tools, team_id)
        found = trace.run(TOOL_WHO_IS_AWAY, {"starts_on": read["starts_on"],
                                             "ends_on": read["ends_on"]})
        when = _when(read["starts_on"], read["ends_on"])
        if not found.get("ok"):
            return trace.reply(text(found.get("error")) or "לא הצלחתי לבדוק.")
        focus = read.get("away_focus") or ""
        lines = []
        for day in found["days"]:
            rows = day["away"]
            if focus == "sick":
                rows = [row for row in rows if row["kind"] == "constraint"
                        and any("חול" in reason for reason in row["reasons"])]
            elif focus == "home":
                rows = [row for row in rows if row["kind"] == "cycle"]
            if not rows:
                continue
            if found["starts_on"] != found["ends_on"]:
                lines.append("**%s**" % day["date"])
            home = [row["employee"] for row in rows if row["kind"] == "cycle"]
            if home:
                lines.append("· בבית לפי המחזור (%d): %s" % (len(home), ", ".join(home)))
            lines += ["· %s — %s%s" % (
                row["employee"], ", ".join(row["reasons"]) or "אילוץ",
                "" if row["whole_day"] else " (%s)" % ", ".join(row["shifts"]))
                for row in rows if row["kind"] == "constraint"]
        if not lines:
            nobody = {"sick": "לא נרשם אף חולה", "home": "אף אחד לא בבית לפי המחזור"}
            return trace.reply("%s %s." % (nobody.get(focus, "לא רשום שמישהו חסר"), when))
        return trace.reply("\n".join(["מי לא נמצא %s:" % when] + _bounded(lines)))


def _bounded(lines: List[str]) -> List[str]:
    if len(lines) <= _MAX_LINES:
        return lines
    return lines[:_MAX_LINES] + ["…ועוד %d שורות. אפשר לשאול על טווח קצר יותר." % (len(lines) - _MAX_LINES)]
