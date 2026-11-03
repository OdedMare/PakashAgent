"""Reading a reserve unit's roster as another app exports it.

Two shapes are read, both from the unit roster app the friend's team used:

- its CSV export, with a header row:
  שם, סוג שירות, דירוג, טלפון, מייל, קבוצת בית, תפקיד, סטטוס, כשיר/ה ל…, הערות
  where "כשיר/ה ל…" is `א/אלחוט/2026-09-01; ב/טקסט/` (group/role/last active);
- its paste format, without a header or with one starting "שם":
  שם | טלפון | קבוצה | תפקיד | דירוג | מייל | סוג שירות

Phones and e-mails are read and dropped: the product holds no employee
contact details (backend CLAUDE.md). Pure functions; no repository.
"""

import csv
import io
import re
from typing import Dict, List, Optional

from app.bl.shared import text

_RATINGS = {"א": "A", "ב": "B", "ג": "C", "A": "A", "B": "B", "C": "C",
            "מעולה": "A", "בסדר": "B", "גרוע": "C"}
_EXPORT_COLUMNS = {
    "name": ("שם",), "service": ("סוג שירות",), "rating": ("דירוג",),
    "group": ("קבוצת בית", "קבוצה"), "role": ("תפקיד",), "status": ("סטטוס",),
    "quals": ("כשיר/ה ל…", "כשיר/ה ל...", "כשירויות"), "notes": ("הערות",),
}
_PASTE_ORDER = ("name", "phone", "group", "role", "rating", "email", "service")
_QUOTES = re.compile(r"['׳\"״]")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def read_rows(raw: str) -> List[dict]:
    """Every person row, as {name, group, role, rating, track, status,
    quals: [(group, role, date)], notes, line, error}."""
    lines = [line for line in (raw or "").lstrip("﻿").splitlines() if line.strip()]
    if not lines:
        return []
    delimiter = "\t" if "\t" in lines[0] else ","
    table = list(csv.reader(io.StringIO("\n".join(lines)), delimiter=delimiter))
    header = [cell.strip() for cell in table[0]]
    columns = _export_columns(header)
    if columns is not None:
        body, offset = table[1:], 2
    else:
        columns = {key: index for index, key in enumerate(_PASTE_ORDER)}
        starts_with_header = header and header[0].startswith("שם")
        body, offset = (table[1:], 2) if starts_with_header else (table, 1)
    return [_row(cells, columns, number + offset) for number, cells in enumerate(body)
            if any(cell.strip() for cell in cells)]


def _export_columns(header: List[str]) -> Optional[Dict[str, int]]:
    found = {}
    for key, names in _EXPORT_COLUMNS.items():
        for index, cell in enumerate(header):
            if cell in names:
                found[key] = index
                break
    return found if "name" in found and ("quals" in found or "status" in found) else None


def _row(cells: List[str], columns: Dict[str, int], line: int) -> dict:
    def cell(key: str) -> str:
        index = columns.get(key)
        return cells[index].strip() if index is not None and index < len(cells) else ""

    rating_text = _QUOTES.sub("", cell("rating")).strip()
    rating = _RATINGS.get(rating_text, "B" if not rating_text else "")
    errors = [] if cell("name") else ["חסר שם"]
    if not rating:
        errors.append('דירוג "%s" לא מוכר' % cell("rating"))
    return {
        "line": line,
        "name": " ".join(cell("name").split()),
        "group": cell("group"),
        "role": cell("role"),
        "rating": rating or "B",
        "track": "sadir" if "סדיר" in cell("service") else "miluim",
        "status": _status(cell("status")),
        "quals": _quals(cell("quals")),
        "notes": cell("notes"),
        "error": ", ".join(errors),
    }


def _status(value: str) -> str:
    if not value or value.startswith("פעיל"):
        return "active"
    if "פטור" in value or "חופשה" in value:
        return "leave"
    return "inactive"


def _quals(value: str) -> List[tuple]:
    result = []
    for item in value.split(";"):
        parts = [part.strip() for part in item.split("/")]
        if len(parts) < 2 or not parts[1] or parts[1] == "?":
            continue
        date = parts[2] if len(parts) > 2 and _DATE.match(parts[2]) else ""
        result.append((parts[0], parts[1], date))
    return result


def same_group(stated: str, label: str, short: str) -> bool:
    """Whether a cell names a group, by its full name or its letter."""
    clean = _QUOTES.sub("", text(stated)).strip()
    return bool(clean) and clean in (_QUOTES.sub("", label).strip(), _QUOTES.sub("", short).strip())


def group_letter(label: str) -> str:
    """'קבוצה א\\'' -> 'א'; a bare letter stays itself."""
    clean = _QUOTES.sub("", text(label)).strip()
    return clean.split()[-1] if clean else ""


__all__ = ["group_letter", "read_rows", "same_group"]
