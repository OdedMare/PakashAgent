"""Calendar limits shared across the spans of an automatic roster build."""

import re
from collections import Counter, defaultdict

from app.common.errors import AgentError

_OFFICER_CAP = re.compile(r"אין לשבץ קצינים ליותר מ\s*[-־–]?\s*(\d{1,3}) משמרות בחודש[.]?")


def single_shift_rule(rule):
    return (isinstance(rule, dict) and rule.get("priority", "hard") == "hard" and
            " ".join(str(rule.get("text") or "").split()).rstrip(".") in {
                "אין לשבץ אדם פעמיים באותו יום", "אדם לא יעשה 2 משמרות ביום", "לכל היותר משמרת אחת לאדם ביום",
            })


def officer_cap(rule):
    if not isinstance(rule, dict) or rule.get("priority", "hard") != "hard":
        return None
    match = _OFFICER_CAP.fullmatch(" ".join(str(rule.get("text") or "").split()))
    return int(match[1]) if match else None


def monthly_officer_limit(profile):
    rules = profile.get("rules") or []
    caps = [cap for rule in rules if (cap := officer_cap(rule)) is not None]
    return min(caps, default=None)


def apply_calendar_limits(model):
    problem = model.problem
    cap = problem.officer_cap
    daily_fixed = Counter((row["employee"], row["date"]) for row in problem.fixed)
    monthly_fixed = Counter((name, date[:7]) for name, shift, date in problem.month_rows)
    for pin in problem.pins:
        name, date = pin["employee"], pin["date"]
        if daily_fixed[name, date] > 1:
            raise AgentError("שיבוץ החובה של %s יוצר שתי משמרות ביום %s" % (name, date))
        if cap is not None and problem.people[name].get("rank_group") == "officer" and monthly_fixed[name, date[:7]] > cap:
            raise AgentError("שיבוץ החובה של %s חורג ממכסת הקצינים בחודש %s" % (name, date[:7]))

    for name in problem.people:
        daily, monthly = defaultdict(list), defaultdict(list)
        for index, variable in model.of_person(name).items():
            date = problem.slots[index]["slot_date"]
            daily[date].append(variable)
            monthly[date[:7]].append(variable)
        for date, variables in daily.items():
            if len(variables) + daily_fixed[name, date] > 1:
                model.at_most(variables, 1 - daily_fixed[name, date])
        if cap is not None and problem.people[name].get("rank_group") == "officer":
            for month, variables in monthly.items():
                model.at_most(variables, cap - monthly_fixed[name, month])
