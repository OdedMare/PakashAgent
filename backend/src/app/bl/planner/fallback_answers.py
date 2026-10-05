"""One template answer per question shape the keyword reader recognises.

Each method runs the same tools the model would and renders the result in
Hebrew. Each returns `(answer, steps, results, needs_confirmation)`.
"""

from typing import List

from app.bl.planner.shaping import pretty, text
from app.bl.planner.trace import ToolTrace
from app.bl.tools import (
    TOOL_COVERAGE_GAPS, TOOL_EMPLOYEE_STATE, TOOL_FIND_REPLACEMENTS,
    TOOL_PUBLISH_READINESS, TOOL_READ_PERIOD, TOOL_TEAM_OVERVIEW,
)

_NO_PERIOD = "אין סידור מאוחסן."


class FallbackAnswers:
    def __init__(self, tools):
        self._tools = tools

    def replacements(self, team_id: str, read: dict) -> tuple:
        """Who could take the shift the absent person holds.

        Two tools in sequence -- the person's rows for that day, then
        candidates for each -- the same chain the model would run, done in
        code so this path works with nothing configured.
        """
        trace = ToolTrace(self._tools, team_id)
        employee, date = read["employee"], read["date"]
        if not employee:
            return trace.reply(
                "לא זיהיתי על מי מדובר. אפשר לכתוב את השם כפי שהוא מופיע "
                "ברשימת הצוות?"
            )
        state = trace.run(TOOL_EMPLOYEE_STATE, {"employee": employee, "day": date})
        if not state.get("found"):
            return trace.reply(
                text(state.get("reason")) or "לא מצאתי את העובד/ת הזה/הזאת."
            )
        shifts = [
            row for row in state.get("shifts") or []
            if not date or row.get("date") == date
        ]
        if not shifts:
            when = " ב-%s" % date if date else " בתקופה הזאת"
            return trace.reply(
                "ל%s אין משמרות%s, אז אין את מי להחליף." % (employee, when)
            )
        lines = [self._candidates_line(trace, employee, row) for row in shifts]
        opening = (
            "בדקתי מי יכול/ה להחליף את %s. כל מי שמופיע כאן נבדק מול "
            "האילוצים, ההסמכות והשעות — ומי שהשיבוץ היה יוצר אצלו/ה אזהרה "
            "לא נכלל." % employee
        )
        closing = "כדי לבצע החלפה צריך לשלוח את הבקשה ולאשר אותה עם סיבה."
        return trace.reply("\n".join([opening] + lines + [closing]), True)

    @staticmethod
    def _candidates_line(trace: ToolTrace, employee: str, row: dict) -> str:
        found = trace.run(TOOL_FIND_REPLACEMENTS, {
            "employee": employee,
            "shift_name": row["shift"],
            "slot_date": row["date"],
        })
        candidates = found.get("candidates") or []
        if not candidates:
            return (
                "· %s ב-%s: לא נמצא מי שיכול/ה לקחת בלי ליצור אזהרה."
                % (row["shift"], row["date"])
            )
        names = "‏, ".join(
            "%s (%s שעות)" % (item["employee"], pretty(item["hours"]))
            for item in candidates
        )
        return (
            "· %s ב-%s: %s — לפי הסדר, הקל/ה בשעות ראשון/ה."
            % (row["shift"], row["date"], names)
        )

    def gaps(self, team_id: str, read: dict) -> tuple:
        trace = ToolTrace(self._tools, team_id)
        date = read["date"]
        found = trace.run(
            TOOL_COVERAGE_GAPS, {"starts_on": date, "ends_on": date} if date else {}
        )
        if not found.get("found"):
            return trace.reply(text(found.get("reason")) or _NO_PERIOD)
        gaps = found.get("gaps") or []
        if not gaps:
            return trace.reply("כל המשמרות בתקופה מאוישות במלואן.")
        lines = ["חסרים %d שיבוצים ב-%d משמרות:" % (
            found.get("people_short", 0), found.get("total_gaps", 0),
        )] + [
            "· %s ב-%s: חסרים %d מתוך %d."
            % (row["shift"], row["date"], row["missing"], row["headcount"])
            for row in gaps
        ]
        return trace.reply("\n".join(lines))

    def employee(self, team_id: str, read: dict) -> tuple:
        trace = ToolTrace(self._tools, team_id)
        employee = read["employee"]
        if not employee:
            # Asking is the only honest move: picking somebody to ask about is
            # the guess this path must not make.
            return trace.reply("על מי מהצוות תרצו לשמוע?")
        found = trace.run(
            TOOL_EMPLOYEE_STATE, {"employee": employee, "day": read["date"]},
            shown={"employee": employee},
        )
        if not found.get("found"):
            return trace.reply(text(found.get("reason")) or "לא מצאתי את העובד/ת.")
        return trace.reply("\n".join(_employee_lines(employee, found)))

    def publish(self, team_id: str, read: dict) -> tuple:
        trace = ToolTrace(self._tools, team_id)
        found = trace.run(TOOL_PUBLISH_READINESS, {})
        if not found.get("found"):
            return trace.reply(text(found.get("reason")) or _NO_PERIOD)
        blockers = found.get("blockers") or []
        if not blockers:
            return trace.reply("לא מצאתי שום דבר פתוח — התקופה מוכנה לפרסום.")
        lines = ["לפני פרסום שווה לשים לב:"] + ["· " + row for row in blockers]
        # Said outright because the audit never gates (D3): a list that read
        # as a checklist would imply otherwise.
        lines.append("אפשר לפרסם גם ככה — אלה הערות, לא חסימות.")
        return trace.reply("\n".join(lines))

    def period(self, team_id: str, read: dict) -> tuple:
        trace = ToolTrace(self._tools, team_id)
        found = trace.run(TOOL_READ_PERIOD, {"day": read["date"]})
        if not found.get("found"):
            return trace.reply(text(found.get("reason")) or _NO_PERIOD)
        period = found.get("schedule") or {}
        lines = [
            "התקופה %s – %s, בסטטוס %s."
            % (period.get("starts_on"), period.get("ends_on"),
               "פורסם" if period.get("status") == "published" else "טיוטה"),
            "יש בה %d משמרות ו-%d שיבוצים."
            % (period.get("slot_count", 0), period.get("assignment_count", 0)),
        ]
        if found.get("warnings"):
            lines.append("אזהרות פתוחות: %d." % len(found["warnings"]))
        return trace.reply("\n".join(lines))

    def team(self, team_id: str, read: dict) -> tuple:
        trace = ToolTrace(self._tools, team_id)
        found = trace.run(TOOL_TEAM_OVERVIEW, {})
        if not found.get("found"):
            return trace.reply(text(found.get("reason")) or "לא הוגדרו פרטי צוות.")
        return trace.reply("\n".join(_team_lines(found)))


def _employee_lines(employee: str, found: dict) -> List[str]:
    shifts = found.get("shifts") or []
    lines = [
        "ל%s יש %d משמרות בתקופה, בסך הכל %s שעות."
        % (employee, len(shifts), pretty(found.get("hours", 0.0)))
    ]
    lines.extend("· %s ב-%s" % (row["shift"], row["date"]) for row in shifts)
    if found.get("constraints"):
        lines.append("אילוצים רשומים: %d." % len(found["constraints"]))
    if found.get("warnings"):
        lines.append("אזהרות פתוחות: %d." % len(found["warnings"]))
    return lines


def _team_lines(found: dict) -> List[str]:
    employees = found.get("employees") or []
    lines = ["בצוות יש %d עובדים ועובדות:" % len(employees)]
    lines.extend(
        "· %s%s" % (row.get("name", ""), " — " + row["role"] if row.get("role") else "")
        for row in employees
    )
    shifts = [row.get("name", "") for row in found.get("shifts") or [] if row.get("name")]
    if found.get("shifts"):
        lines.append("סוגי המשמרות שהוגדרו: %s." % ", ".join(shifts))
    rules = [
        text(row.get("text") or row.get("rule")) if isinstance(row, dict) else text(row)
        for row in found.get("rules") or []
    ]
    rules = [row for row in rules if row]
    if rules:
        lines.append("כללים שנרשמו:")
        lines.extend("· " + row for row in rules)
    return lines
