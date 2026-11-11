"""Deleting a shift type from the vocabulary, without rewriting history.

A shift name is an identity key (D9): stored slots, assignments and
constraints name it. Deleting one therefore *archives* it — the row moves to
`archived_shifts`, where the audit and the stats still find its hours for the
periods that used it — and only the next build stops producing it. What the
roster says about the shift is cleaned up here rather than left dangling:
an eligibility list or a recurring constraint naming a shift that no longer
exists would read, once emptied, as "every shift", which is the opposite of
what the manager wrote.
"""

import copy
from typing import List

from app.bl.profile_service.validation import text
from app.common.errors import AgentError


def retire_shift(current: dict, name: str) -> dict:
    """The profile with `name` moved out of the shift vocabulary."""
    name = text(name)
    shifts = [row for row in current.get("shifts") or [] if isinstance(row, dict)]
    retired = next((row for row in shifts if text(row.get("name")) == name), None)
    if retired is None:
        raise AgentError("סוג המשמרת %s לא נמצא בפרופיל" % (name or ""))
    if len(shifts) == 1:
        raise AgentError("לא ניתן למחוק את סוג המשמרת האחרון; בלי משמרות אין ממה לבנות סידור")
    updated = copy.deepcopy(current)
    updated["shifts"] = [row for row in updated["shifts"] if text(row.get("name")) != name]
    archived = [row for row in updated.get("archived_shifts") or []
                if text(row.get("name")) != name]
    updated["archived_shifts"] = archived + [copy.deepcopy(retired)]
    stranded = [
        text(person.get("name")) for person in updated.get("employees") or []
        if _forget_shift(person, name)
    ]
    if stranded:
        raise AgentError(
            "%s מוגדר/ת רק למשמרת %s; יש לעדכן את המשמרות שלו/ה לפני המחיקה"
            % (stranded[0], name)
        )
    return updated


def _forget_shift(person: dict, name: str) -> bool:
    """Drop `name` from one person; True when nothing eligible would remain."""
    eligible = [text(item) for item in person.get("eligible_shifts") or []]
    if name in eligible:
        person["eligible_shifts"] = [item for item in eligible if item != name]
        person["archived_eligible_shifts"] = sorted(
            set(person.get("archived_eligible_shifts") or []) | {name}
        )
        if not person["eligible_shifts"]:
            return True
    person["recurring_constraints"] = _without_shift(
        person.get("recurring_constraints") or [], name
    )
    return False


def _without_shift(rules: List, name: str) -> List:
    kept = []
    for rule in rules:
        if not isinstance(rule, dict) or name not in (rule.get("shifts") or []):
            kept.append(rule)
            continue
        rest = [shift for shift in rule["shifts"] if shift != name]
        # A rule scoped to this shift alone goes with it: an empty list means
        # every shift, which the manager never said.
        if rest:
            kept.append(dict(rule, shifts=rest))
    return kept
