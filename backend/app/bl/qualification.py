"""Whether a person's dated qualifications (כשירות) still stand. Pure arithmetic.

A qualification is a role and the day the person was last active in it
(`qualifications: [{role, last_active}]`, D47); it lapses after the unit's
`qualification_validity_days`. Working shifts keeps it alive, so the clock
runs from whichever is later — the typed date or the person's last shift
already worked on the board. Nobody has to retype the date after every
shift; the board is the record.

Only a dated row is judged here: the setup screen colours a person by what
was dated and leaves the rest plain. (The audit's own notice still reads an
undated row as stale, `unit_policy.qualification_expired`.)
"""

import datetime
from typing import Dict, Mapping, Optional

from app.bl.audit.unit_policy import validity_days
from app.bl.shared import parse_date, text

# Inside this many days of the expiry a qualification reads as "expiring".
EXPIRING_DAYS = 7
_RANK = {"valid": 0, "expiring": 1, "expired": 2}


def effective_last_active(typed, worked, today: datetime.date) -> Optional[datetime.date]:
    """The later of the typed date and the last shift worked by `today`."""
    dates = [day for day in (parse_date(text(typed)) if typed else None,
                             parse_date(text(worked)) if worked else None)
             if day is not None and day <= today]
    return max(dates) if dates else None


def standing(profile: Optional[dict], person: Optional[dict], last_shift,
             today: datetime.date, days: Optional[int] = None) -> Optional[dict]:
    """One person's qualifications on `today`, or None when none is dated.

    `status` is the worst of the dated rows, so a person with one lapsed
    role reads as lapsed; `rows` says which.
    """
    window = days if days and days > 0 else validity_days(profile)
    rows = []
    for raw in (person or {}).get("qualifications") or []:
        if not isinstance(raw, dict) or not text(raw.get("role")) \
                or not parse_date(text(raw.get("last_active"))):
            continue
        active = effective_last_active(raw.get("last_active"), last_shift, today)
        if active is None:  # dated ahead of today: not yet started
            continue
        until = active + datetime.timedelta(days=window)
        left = (until - today).days
        status = "expired" if left < 0 else "expiring" if left <= min(EXPIRING_DAYS, window) else "valid"
        rows.append({"role": text(raw["role"]), "last_active": active.isoformat(),
                     "valid_until": until.isoformat(), "days_left": left, "status": status})
    if not rows:
        return None
    worked = parse_date(text(last_shift)) if last_shift else None
    return {
        "status": max((row["status"] for row in rows), key=_RANK.get),
        "last_shift": worked.isoformat() if worked and worked <= today else None,
        "rows": rows,
    }


def standings(profile: Optional[dict], employees, last_shifts: Mapping[str, object],
              today: datetime.date, days: Optional[int] = None) -> Dict[str, dict]:
    """Every person with a dated qualification, keyed by name."""
    result = {}
    for person in employees or []:
        name = text((person or {}).get("name")) if isinstance(person, dict) else ""
        row = standing(profile, person, last_shifts.get(name), today, days) if name else None
        if row is not None:
            result[name] = row
    return result
