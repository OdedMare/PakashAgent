"""Renaming a soldier or a shift, and deleting a soldier, from unit setup.

A name is an identity key (D9): assignments, constraints, requests, swaps and
claimed identities all name a person or a shift by the string the profile
recorded. An ordinary save therefore refuses to drop one
(`keep_existing_names`). A typo still has to be fixable, so a rename is
stated explicitly — old name to new — and carried out everywhere at once:
here on the profile, and by the repository on every stored row, in the same
transaction as the save.

Deleting a soldier is for a person added by mistake. It is not a departure
(`inactive_from` keeps the name for history); the repository refuses it for
anyone on a published week and points at "הוצאה מהסגל" instead.
"""

import copy
from typing import Any, Dict, List, Optional

from app.bl.profile_service.validation import text
from app.common.errors import AgentError


class IdentityChanges:
    """What one save renames and deletes, validated against the profile."""

    def __init__(self, employees: Dict[str, str], shifts: Dict[str, str],
                 removed: List[str]):
        self.employees = employees
        self.shifts = shifts
        self.removed = removed

    def __bool__(self) -> bool:
        return bool(self.employees or self.shifts or self.removed)

    @classmethod
    def read(cls, current: Optional[dict], employees: Any = None,
             shifts: Any = None, removed: Any = None) -> "IdentityChanges":
        current = current or {}
        people = _names(current.get("employees"))
        vocabulary = _names(current.get("shifts"))
        archived = _names(current.get("archived_shifts"))
        removed_names = _removed(removed, people)
        employee_map = _renames(employees, people, people, "החייל/ת", "חייל/ת")
        shift_map = _renames(shifts, vocabulary, vocabulary | archived,
                             "סוג המשמרת", "משמרת")
        both = sorted(set(employee_map) & set(removed_names))
        if both:
            raise AgentError("לא ניתן גם לשנות את השם של %s וגם למחוק אותו/ה" % both[0])
        return cls(employee_map, shift_map, removed_names)

    def apply(self, profile: Optional[dict]) -> Optional[dict]:
        """The profile with every rename and deletion carried through."""
        if profile is None or not self:
            return profile
        updated = copy.deepcopy(profile)
        gone = set(self.removed)
        if isinstance(updated.get("employees"), list):
            updated["employees"] = [
                _person(row, self.employees, self.shifts, gone)
                for row in updated["employees"]
                if isinstance(row, dict) and text(row.get("name")) not in gone
            ]
        if isinstance(updated.get("shifts"), list):
            updated["shifts"] = [_renamed(row, self.shifts) for row in updated["shifts"]]
        place = updated.get("workplace")
        if isinstance(place, dict):
            for key in ("rotation_presence", "rotation_a_unavailability"):
                if isinstance(place.get(key), list):
                    place[key] = [_with_shifts(rule, "shifts", self.shifts)
                                  for rule in place[key]]
        return updated


def _names(rows: Any) -> set:
    return {text(row.get("name")) for row in rows or []
            if isinstance(row, dict) and text(row.get("name"))}


def _renames(raw: Any, existing: set, taken: set, label: str, noun: str) -> Dict[str, str]:
    """`{old: new}`, each old name saved and each new one free."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise AgentError("רשימת שינויי השם אינה תקינה")
    result: Dict[str, str] = {}
    for old_raw, new_raw in raw.items():
        old, new = text(old_raw), text(new_raw)
        if not old or old == new:
            continue
        if old not in existing:
            raise AgentError("%s %s לא נמצא/ה בפרופיל" % (label, old))
        if not new:
            raise AgentError("לכל %s חייב להיות שם" % noun)
        if new in taken or new in result.values():
            raise AgentError("השם %s כבר קיים; יש לבחור שם אחר" % new)
        result[old] = new
    return result


def _removed(raw: Any, existing: set) -> List[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise AgentError("רשימת המחיקות אינה תקינה")
    names = list(dict.fromkeys(text(item) for item in raw if text(item)))
    for name in names:
        if name not in existing:
            raise AgentError("החייל/ת %s לא נמצא/ה בפרופיל" % name)
    return names


def _person(row: dict, people: Dict[str, str], shifts: Dict[str, str], gone: set) -> dict:
    row = _renamed(row, people)
    if isinstance(row.get("trainers"), list):
        row["trainers"] = [people.get(text(name), name) for name in row["trainers"]
                           if text(name) not in gone]
    for key in ("eligible_shifts", "archived_eligible_shifts"):
        if isinstance(row.get(key), list):
            row[key] = [shifts.get(text(name), name) for name in row[key]]
    if isinstance(row.get("recurring_constraints"), list):
        row["recurring_constraints"] = [_with_shifts(rule, "shifts", shifts)
                                        for rule in row["recurring_constraints"]]
    return row


def _renamed(row: Any, names: Dict[str, str]) -> Any:
    if isinstance(row, dict) and text(row.get("name")) in names:
        row = dict(row, name=names[text(row.get("name"))])
    return row


def _with_shifts(rule: Any, key: str, shifts: Dict[str, str]) -> Any:
    if not isinstance(rule, dict) or not isinstance(rule.get(key), list):
        return rule
    return dict(rule, **{key: [shifts.get(text(name), name) for name in rule[key]]})
