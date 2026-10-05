"""What the importer believes a file says, before anyone approves it."""

from typing import List, Optional

from app.bl.importer.cells import human_date, parse_date, text


class Interpretation(object):
    """Deliberately a plain object with a `to_dict`: it crosses the HTTP
    boundary to be confirmed, and it is the only thing the manager sees
    before a write happens.
    """

    def __init__(
        self,
        layout: str,
        shifts: List[str],
        people: List[str],
        dates: List[str],
        assignments: List[dict],
        unavailability: List[dict],
        warnings: Optional[List[str]] = None,
    ):
        self.layout = layout
        self.shifts = shifts
        self.people = people
        self.dates = dates
        self.assignments = assignments
        self.unavailability = unavailability
        self.warnings = warnings or []

    @property
    def starts_on(self) -> str:
        return self.dates[0] if self.dates else ""

    @property
    def ends_on(self) -> str:
        return self.dates[-1] if self.dates else ""

    def summary(self) -> str:
        """The one sentence D7 asks for, in Hebrew, for the confirm screen."""
        parts = ["%d אנשים" % len(self.people)]
        if self.dates:
            parts.append("%s עד %s" % (
                human_date(self.starts_on), human_date(self.ends_on),
            ))
        parts.append("%d משמרות" % len(self.shifts))
        parts.append("%d שיבוצים" % len(self.assignments))
        if self.unavailability:
            parts.append("%d סימוני אי-זמינות" % len(self.unavailability))
        return ", ".join(parts)

    def to_dict(self) -> dict:
        return {
            "layout": self.layout,
            "shifts": self.shifts,
            "people": self.people,
            "dates": self.dates,
            "starts_on": self.starts_on,
            "ends_on": self.ends_on,
            "assignments": self.assignments,
            "unavailability": self.unavailability,
            "warnings": self.warnings,
            "summary": self.summary(),
        }

    def deduplicate(self) -> "Interpretation":
        """Remove repeated rows without changing the first visible occurrence."""
        assignments = _unique(
            self.assignments, ("employee", "shift", "date"),
            keep=lambda row: row["employee"] and row["date"],
        )
        unavailability = _unique(
            self.unavailability, ("employee", "shift", "date", "reason"),
            keep=lambda row: row["date"],
        )
        removed = (
            len(self.assignments) - len(assignments)
            + len(self.unavailability) - len(unavailability)
        )
        if removed:
            self.warnings.append(
                "%d שורות כפולות או חלקיות הוסרו מהתצוגה" % removed
            )
        self.assignments, self.unavailability = assignments, unavailability
        self.people = sorted(set(
            [text(name) for name in self.people if text(name)]
            + [row["employee"] for row in unavailability if row["employee"]]
        ))
        self.dates = sorted(set(
            [row["date"] for row in assignments]
            + [row["date"] for row in unavailability]
        ))
        self.warnings = list(dict.fromkeys(self.warnings))
        return self


def _unique(rows: List[dict], fields: tuple, keep) -> List[dict]:
    found, seen = [], set()
    for row in rows:
        clean = {
            field: parse_date(row.get(field)) if field == "date"
            else text(row.get(field))
            for field in fields
        }
        key = tuple(clean[field] for field in fields)
        if not keep(clean) or key in seen:
            continue
        seen.add(key)
        found.append(clean)
    return found
