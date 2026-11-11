"""Hypothetical roster changes for staffing scenarios."""

from app.bl.audit.unit_policy import reserve_days
from app.bl.shared import text
from app.common.errors import AgentError

_MAX_ADDITIONAL_STAFF = 20
_SERVICE_TYPES = {"standard", "reserve", "civilian", "hatzach"}
_COMPETENCE = {"", "weak", "medium", "high", "excellent"}


def reserve_changes(profile, days, minimum, extra, employee):
    """Change reservist capacity on the copied profile and describe it."""
    if days is None and minimum is None and extra is None:
        return []
    if days is not None and extra is not None:
        raise AgentError("יש לבחור מכסה מוחלטת או תוספת ימים, לא את שתיהן")
    days = _week_days(days, "מספר ימי המילואים") if days is not None else None
    minimum = _week_days(minimum, "מינימום ימי המילואים") if minimum is not None else None
    extra = _extra_days(extra) if extra is not None else None
    selected = [
        row for row in profile.get("employees") or []
        if text(row.get("service_type")) == "reserve"
        and (not employee or text(row.get("name")) == text(employee))
    ]
    if not selected:
        raise AgentError("לא נמצא איש מילואים מתאים לתרחיש")
    return [_change_reservist(person, days, minimum, extra) for person in selected]


def _change_reservist(person, days, minimum, extra):
    cap_before = reserve_days(person)
    min_before = person.get("reserve_min_days")
    requested = cap_before + extra if extra is not None and cap_before is not None else days
    cap_after = min(7, requested) if requested is not None else cap_before
    reason = ""
    if extra is not None and cap_before is None:
        reason = "לא הוגדרה מכסת ימי מילואים, ולכן תוספת יחסית אינה משנה אותה"
    floor = minimum if minimum is not None else min_before
    if cap_after is not None and floor not in (None, "") \
            and _week_days(floor, "מינימום ימי המילואים") > cap_after:
        raise AgentError("מינימום ימי המילואים אינו יכול להיות גבוה ממספר הימים המרבי")
    if cap_after is not None:
        person["reserve_days_per_week"] = cap_after
    if minimum is not None:
        person["reserve_min_days"] = minimum
    changed = cap_after != cap_before or (minimum is not None and minimum != min_before)
    return {
        "employee": text(person.get("name")),
        "before": {"reserve_days_per_week": cap_before, "reserve_min_days": min_before},
        "after": {"reserve_days_per_week": cap_after,
                  "reserve_min_days": person.get("reserve_min_days")},
        "cap_before": cap_before, "requested_cap": requested, "cap_after": cap_after,
        "capped_at_seven": requested is not None and requested > 7,
        "minimum_unchanged": minimum is None, "changed": changed,
        "reason": reason or ("המכסה כבר שבעה ימים" if extra and cap_before == 7 else ""),
    }


def _week_days(value, label):
    if isinstance(value, bool):
        raise AgentError(label + " חייב להיות מספר בין 1 ל-7")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise AgentError(label + " חייב להיות מספר בין 1 ל-7") from exc
    if not 1 <= result <= 7:
        raise AgentError(label + " חייב להיות מספר בין 1 ל-7")
    return result


def _extra_days(value):
    if isinstance(value, bool):
        raise AgentError("תוספת ימי המילואים חייבת להיות מספר בין 1 ל-6")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise AgentError("תוספת ימי המילואים חייבת להיות מספר בין 1 ל-6") from exc
    if not 1 <= result <= 6:
        raise AgentError("תוספת ימי המילואים חייבת להיות מספר בין 1 ל-6")
    return result


def additional_staff(profile, groups):
    if not isinstance(groups, list):
        raise AgentError("תוספת כוח האדם לתרחיש אינה תקינה")
    shifts = {text(row.get("name")) for row in profile.get("shifts") or []}
    existing = {text(row.get("name")) for row in profile.get("employees") or []}
    total, added = 0, []
    for group_index, raw in enumerate(groups, start=1):
        group, total = _staff_group(raw, shifts, total)
        added.append(dict(group, scenario_names=_append_group(
            profile, existing, group, group_index,
        )))
    return added


def _staff_group(raw, shifts, total):
    if not isinstance(raw, dict):
        raise AgentError("כל קבוצת כוח אדם בתרחיש חייבת לכלול סוג שירות ומשמרות")
    try:
        count = int(raw.get("count") or 0)
    except (TypeError, ValueError) as exc:
        raise AgentError("כמות כוח האדם בתרחיש חייבת להיות מספר") from exc
    service_type = text(raw.get("service_type"))
    eligible = list(dict.fromkeys(text(item) for item in raw.get("eligible_shifts") or [] if text(item)))
    competence = text(raw.get("competence"))
    if count < 1 or total + count > _MAX_ADDITIONAL_STAFF:
        raise AgentError("אפשר לבדוק עד 20 אנשי צוות נוספים בתרחיש")
    if service_type not in _SERVICE_TYPES or not eligible or not set(eligible).issubset(shifts):
        raise AgentError("יש לציין סוג שירות ומשמרות מוכרות לכל כוח אדם נוסף")
    if competence not in _COMPETENCE:
        raise AgentError("הרמה המקצועית בתרחיש אינה מוכרת")
    reserve = raw.get("reserve_days_per_week")
    if service_type == "reserve":
        reserve = _week_days(reserve, "מספר ימי המילואים של כוח האדם הנוסף")
    return ({"count": count, "service_type": service_type, "role": text(raw.get("role")),
             "eligible_shifts": eligible, "competence": competence,
             "reserve_days_per_week": reserve}, total + count)


def _append_group(profile, existing, group, group_index):
    names = []
    for member in range(1, group["count"] + 1):
        base, suffix = "כוח תרחיש %d-%d" % (group_index, member), 2
        name = base
        while name in existing:
            name, suffix = "%s (%d)" % (base, suffix), suffix + 1
        existing.add(name)
        person = {
            "name": name, "role": group["role"], "eligible_shifts": group["eligible_shifts"],
            "service_type": group["service_type"], "exit_pattern": "none",
            "rotation_group": "", "counts_toward_staffing": True,
            "competence": group["competence"],
        }
        if group["service_type"] == "reserve":
            person["reserve_days_per_week"] = group["reserve_days_per_week"]
        profile.setdefault("employees", []).append(person)
        names.append(name)
    return names


__all__ = ["additional_staff", "reserve_changes"]
