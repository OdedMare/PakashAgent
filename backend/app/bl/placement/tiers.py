"""Who replaces a soldier, in stages: same role and post first, then wider.

A cover is searched outward from the seat. First the people who hold the
leaving soldier's role and already stand this post -- the shift's own
crew, who know it. Then the same role from another post. Only then anyone
else the placement checks pass, so the manager is never left with nothing
while a fitting holder of the role was there to be asked.

**A post is the shift's `purpose` when it states one, else the shift
itself.** Two shifts with one purpose ("סיור" morning and night) are one
place at different hours. Someone *belongs* to a post when the period has
them on it, or when their `eligible_shifts` names it -- an empty list means
"every shift" and says nothing about where they belong.

When the leaving soldier holds no role there is no role to match, and the
stages are the post alone. Pure arithmetic over the roster and the rows.
"""

from typing import Dict, List

from app.bl.placement import values
from app.bl.shared import person_roles

SAME_POST, SAME_ROLE, OTHER = 0, 1, 2

TIER_LABELS = {
    SAME_POST: "אותו תפקיד מהמשמרת",
    SAME_ROLE: "אותו תפקיד ממקום אחר",
    OTHER: "מחליפים נוספים",
}


class Tiers:
    """The stage of every candidate for one seat, worked out once."""

    def __init__(self, schedule: dict, profile: dict, leaving: str, shift_name: str):
        self._place = posts_by_shift(profile)
        here = self._place.get(shift_name) or shift_name
        self._posts = {
            name for name, place in self._place.items() if place == here
        } | {shift_name}
        people = {values.text(row.get("name")): row for row in values.employees(profile)}
        self._roles = {name: person_roles(row) for name, row in people.items()}
        self._wanted = self._roles.get(leaving) or set()
        self._crew = self._members(schedule, people)

    def tier(self, employee: str) -> int:
        # With no role to match, everyone counts as holding it.
        if self._wanted and not self._roles.get(employee, set()) & self._wanted:
            return OTHER
        return SAME_POST if employee in self._crew else SAME_ROLE

    def mark(self, candidate: dict) -> dict:
        tier = self.tier(values.text(candidate.get("employee")))
        return dict(candidate, tier=tier, tier_label=self.label(tier))

    def label(self, tier: int) -> str:
        if tier == SAME_ROLE and not self._wanted:
            return "ממקום אחר"
        if tier == SAME_POST and not self._wanted:
            return "מהמשמרת"
        return TIER_LABELS[tier]

    def _members(self, schedule: dict, people: Dict[str, dict]) -> set:
        crew = {row["employee"] for row in values.rows(schedule) if row["shift"] in self._posts}
        for name, row in people.items():
            if set(_listed(row.get("eligible_shifts"))) & self._posts:
                crew.add(name)
        return crew


def _place(row: dict, name: str) -> str:
    return values.text((row or {}).get("purpose")) or name


def posts_by_shift(profile: dict) -> Dict[str, str]:
    """Every shift name and the post it belongs to (its purpose, else itself)."""
    return {
        values.text(row.get("name")): _place(row, values.text(row.get("name")))
        for row in values.shifts(profile)
        if isinstance(row, dict) and values.text(row.get("name"))
    }


def _listed(value) -> List[str]:
    if not isinstance(value, list):
        return []
    return [values.text(item) for item in value if values.text(item)]
