"""What the absence path says, in Hebrew, built from facts code computed.

Templates rather than model prose: every name, date and number here comes
from the roster, the board or `find_replacements`, so there is nothing for
phrasing to get wrong.
"""

import datetime
from typing import List

_DAY_NAMES = ("ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת")


def day_label(iso_date: str) -> str:
    day = datetime.date.fromisoformat(iso_date)
    return "יום %s %d.%d" % (_DAY_NAMES[(day.weekday() + 1) % 7], day.day, day.month)


def dates_label(dates: List[str]) -> str:
    """"26.10–28.10" for a run of days, a list of days otherwise."""
    days = [datetime.date.fromisoformat(value) for value in dates]
    if len(days) > 2 and (days[-1] - days[0]).days == len(days) - 1:
        return "%d.%d–%d.%d" % (days[0].day, days[0].month, days[-1].day, days[-1].month)
    return ", ".join(day_label(value) for value in dates)


def _in(label: str) -> str:
    """Hebrew's attached "ב", hyphenated before a number: "ב-1.11", "ביום"."""
    return ("ב-" if label[:1].isdigit() else "ב") + label


def ask_dates(employee: str) -> str:
    return (
        "באילו תאריכים %s לא זמין/ה? אפשר לכתוב למשל \"מ-1.11 עד 5.11\" "
        "או \"בשני ושלישי\"." % employee
    )


def ask_scope(employee: str, date: str, weekday: str) -> dict:
    """One question with both readings as buttons; each answer is a whole
    sentence, so the click is read on its own and needs no memory."""
    return {
        "question": "%s לא זמין/ה רק ב%s, או בכל יום %s באופן קבוע?" % (
            employee, day_label(date), weekday),
        "recommendation": "",
        "why": "אילוץ קבוע נשמר בפרטי הצוות וחל גם על סידורים עתידיים.",
        "options": [
            {"label": "רק ב%s" % day_label(date),
             "answer": "%s לא זמין/ה בתאריך %s" % (employee, date)},
            {"label": "בכל יום %s (אילוץ קבוע)" % weekday,
             "answer": "%s לא זמין/ה בכל יום %s באופן קבוע" % (employee, weekday)},
        ],
    }


def plan_reply(employee: str, dates: List[str], found: dict) -> tuple:
    """The message above the plan card, and the agent's reason for the plan."""
    lines = ["%s לא זמין/ה %s. הכנתי תוכנית לאישור:" % (employee, _in(dates_label(dates)))]
    for slot in found["slots"]:
        where = "%s · %s" % (day_label(slot["date"]), slot["shift"])
        if slot["pick"]:
            how = "בחירה שלך" if slot["picked_by"] == "manager" else "העומס הנמוך ביותר מבין המתאימים"
            lines.append("- %s: **%s** במקום %s (%s)" % (where, slot["pick"], employee, how))
        else:
            lines.append("- %s: לא נמצא מחליף שעומד בכל הכללים — המשמרת תישאר חסרה" % where)
    if found["free_dates"]:
        lines.append("%s אין ל%s משמרות; נשמר אילוץ היעדרות בלבד." % (
            _in(dates_label(found["free_dates"])), employee))
    if found["slots"]:
        lines.append("אפשר לבחור מחליף אחר מהרשימה שמתחת לתוכנית.")
    reason = (
        "בכל משמרת נבחר/ה, מבין מי שעומדים בכל הכללים, מי שהשעות, המשמרות והלילות "
        "שלו/ה בתקופה הנמוכים ביותר — כולל ההחלפות האחרות בתוכנית — כדי שהעומס יתחלק שווה."
    )
    return "\n".join(lines), reason


def recurring_reply(employee: str, weekdays: List[str], upcoming: List[dict]) -> str:
    days = ", ".join("יום %s" % name for name in weekdays)
    lines = ["הכנתי אילוץ קבוע לאישור: %s לא זמין/ה בכל %s." % (employee, days)]
    if upcoming:
        lines.append("שימו לב: כבר משובצים ל%s %s. האילוץ לא מזיז אותם — "
                     "אחרי האישור אפשר לבקש החלפה." % (
                         employee, ", ".join("%s (%s)" % (day_label(row["date"]), row["shift"])
                                             for row in upcoming)))
    return "\n".join(lines)
