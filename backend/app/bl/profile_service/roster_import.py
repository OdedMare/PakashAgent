"""Turning another app's reserve-unit roster into this product's profile.

The unit is one team. Each of its groups (א–ח) staffs its own 12-hour day
and night shifts, so every group becomes two shifts named after it
("קבוצה א' · יום", "קבוצה א' · לילה") with that group's role composition as
`required_roles` (a role listed N times needs N people), and each person is
eligible only for their home group's shifts. Ratings, service and dated
qualifications carry over (`audit/unit_policy.py`); א/ב/ג become
`competence`, מילואים/סדיר become `service_type` reserve/standard.

`build_patch` writes nothing: it returns the merged employees and shifts
and a report, and the caller saves through `ProfileService.update`.
"""

import datetime
from typing import Dict, List, Optional

from app.bl.profile_service.roster_csv import group_letter, read_rows
from app.bl.profile_service.validation import valid_time
from app.bl.shared import text
from app.common.errors import AgentError

# The app's א/ב/ג ("מעולה", "בסדר", "גרוע") on the roster's competence scale.
_COMPETENCE = {"A": "excellent", "B": "medium", "C": "weak"}


def build_patch(raw: str, profile: Optional[dict], options: Optional[dict] = None,
                today: Optional[datetime.date] = None) -> dict:
    options = options or {}
    profile = profile or {}
    today = today or datetime.date.today()
    rows = read_rows(raw)
    good = [row for row in rows if not row["error"]]
    if not good:
        raise AgentError("לא נמצאו שורות תקינות לייבוא")
    groups = _groups(good, options.get("groups"))
    start = text(options.get("start_time")) or "08:00"
    if not valid_time(start):
        raise AgentError("שעת תחילת משמרת היום חייבת להיות בפורמט HH:MM")
    roles = sorted({role for row in good for role in _row_roles(row)})
    policy = dict(options.get("unit_policy") or profile.get("unit_policy") or {})
    shifts = _shifts(groups, roles, options, start, policy)
    made = {shift["name"] for shift in shifts}
    employees, added = _employees(good, groups, profile.get("employees") or [], today, made)
    return {
        "employees": employees,
        "shifts": _merged(profile.get("shifts") or [], shifts),
        "unit_policy": policy,
        "report": {
            "read": len(rows), "added": added, "updated": len(good) - added,
            "errors": [{"line": row["line"], "error": row["error"]} for row in rows if row["error"]],
            "groups": [dict(group, members=len(group["members"])) for group in groups.values()],
            "roles": roles,
            "shifts": [shift["name"] for shift in shifts],
            "contact_details_dropped": True,
        },
    }


def _groups(rows: List[dict], wanted) -> Dict[str, dict]:
    chosen = {group_letter(item) for item in wanted or [] if group_letter(item)}
    groups: Dict[str, dict] = {}
    for row in rows:
        letter = group_letter(row["group"])
        if not letter or (chosen and letter not in chosen):
            continue
        label = "קבוצה %s'" % letter if len(letter) == 1 else row["group"]
        group = groups.setdefault(letter, {"letter": letter, "label": label, "members": []})
        group["members"].append(row["name"])
    return dict(sorted(groups.items()))


def _row_roles(row: dict) -> List[str]:
    return [role for _, role, _ in row["quals"]] + ([row["role"]] if row["role"] else [])


def _shifts(groups: Dict[str, dict], roles: List[str], options: dict,
            start: str, policy: dict) -> List[dict]:
    default = options.get("staffing") or {"day": {role: 1 for role in roles},
                                          "night": {role: 1 for role in roles}}
    special = options.get("group_staffing") or {}
    hour, minute = (int(part) for part in start.split(":"))
    begins, turns = "%02d:%02d" % (hour, minute), "%02d:%02d" % ((hour + 12) % 24, minute)
    sources = {item for others in (policy.get("role_fallbacks") or {}).values()
               for item in others or []}
    result = []
    for letter, group in groups.items():
        staffing = special.get(letter) or special.get(group["label"]) or default
        for part, label, times in (("day", "יום", (begins, turns)), ("night", "לילה", (turns, begins))):
            seats = [role for role, count in sorted((staffing.get(part) or {}).items())
                     for _ in range(max(0, int(count or 0)))]
            if not seats:
                continue
            result.append({
                "name": "%s · %s" % (group["label"], label),
                "start_time": times[0], "end_time": times[1],
                "staffing": [{"days": [], "headcount": len(seats), "required_roles": seats}],
                "allowed_roles": sorted(set(seats) | sources),
                "shift_type": "regular", "purpose": "",
                "requires_shift_manager": False,
            })
    return result


def _employees(rows: List[dict], groups: Dict[str, dict], existing: List[dict],
               today: datetime.date, made: set):
    people = [dict(person) for person in existing if isinstance(person, dict)]
    index = {text(person.get("name")): person for person in people}
    added = 0
    for row in rows:
        person = index.get(row["name"])
        if person is None:
            person = {"name": row["name"], "exit_pattern": "round", "rotation_group": "",
                      "service_type": "standard", "notes": ""}
            people.append(person)
            index[row["name"]] = person
            added += 1
        _fill(person, row, groups, today, made)
    return people, added


def _fill(person: dict, row: dict, groups: Dict[str, dict], today: datetime.date,
          made: set) -> None:
    group = groups.get(group_letter(row["group"]))
    latest: Dict[str, str] = {}
    for _, role, date in row["quals"]:
        latest[role] = max(latest.get(role, ""), date)
    if row["role"] and row["role"] not in latest:
        latest[row["role"]] = ""
    person.update({
        "role": row["role"] or text(person.get("role")),
        "competence": _COMPETENCE[row["rating"]],
        "service_type": _service(person, row["track"]),
        "qualifications": [{"role": role, "last_active": date} for role, date in sorted(latest.items())],
        "eligible_shifts": [name for name in ("%s · יום" % group["label"], "%s · לילה" % group["label"])
                            if name in made] if group else [],
    })
    if row["notes"] and row["notes"] not in text(person.get("notes")):
        person["notes"] = " ".join(part for part in (text(person.get("notes")), row["notes"]) if part)
    # Not active in the unit's app: kept on the roster, switched off (D49) —
    # a reservist who is not called up now may be next week. Active again:
    # switched back on, unless the manager ended them here.
    person["on_duty"] = row["status"] == "active"


def _merged(existing: List[dict], incoming: List[dict]) -> List[dict]:
    names = {shift["name"] for shift in incoming}
    return [dict(shift) for shift in existing
            if isinstance(shift, dict) and text(shift.get("name")) not in names] + incoming



def _service(person: dict, track: str) -> str:
    """מילואים is `reserve`, סדיר `standard`; a trainee, civilian or הצ״ח
    already set here keeps their status."""
    current = text(person.get("service_type"))
    if current and current not in ("standard", "reserve"):
        return current
    return "reserve" if track == "miluim" else "standard"


__all__ = ["build_patch"]
