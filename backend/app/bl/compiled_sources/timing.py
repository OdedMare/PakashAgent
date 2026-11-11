"""When a standing source speaks about: code's check on the model's reading.

A sentence saved in setup may carry time: "עודד חולה 3 או 4 ימים", "דנה
בחופשה 3-7.11". The model reads the expression against the date the
sentence was written (`anchored_on`) and says, per source, in `timing`:

| `kind` | meaning |
|---|---|
| `none` | the sentence names no time; its items should be recurring |
| `absolute` | a date is written in the sentence itself |
| `relative` | the dates were counted from `anchored_on` |

`settle` holds that answer to what code can check before anything is
kept for later builds:

- `none` with dated items means the model spread a recurring sentence over
  this period's dates. Used for this build, never kept.
- `relative` dates must fall within `RELATIVE_HORIZON_DAYS` from the
  anchor, and the certain range must end no later than `maybe_through`.
- `absolute` dates must lie between the earliest and latest date the
  sentence itself writes.

A source the model itself marked unresolved is kept that way too, so a
policy code cannot represent stops costing a translation on every build;
one code refused, or one the model skipped, is tried again next time.

A source failing the check is left out ("ביטוי הזמן לא הובן"), exactly like
an item code refused, and is kept that way: the same words fail the same
way next time. `expires_on` is the last date a fully dated source speaks
about; past it the source cannot affect a build.
"""

import datetime
import re
from typing import Any, Dict, List, Optional

from app.bl.shared import text

TIMING_KINDS = ("none", "absolute", "relative")
RELATIVE_HORIZON_DAYS = 90
UNREAD_TIME = "ביטוי הזמן לא הובן"

_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_RANGE = re.compile(r"(?<![\d.])(\d{1,2})\s*[-–]\s*(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?(?![\d])")
_DAY = re.compile(r"(?<![\d.])(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?(?![\d])")


def settle(answer: Any, sources: List[dict], outcomes: Dict[str, dict],
           anchors: Dict[str, str]) -> Dict[str, dict]:
    """`outcomes` with each standing source judged, and marked `store`."""
    rows = _timing_rows(answer)
    result = {}
    for source in sources:
        outcome = dict(outcomes[source["id"]])
        if source.get("persistent"):
            outcome.update(_judge(source, outcome, rows.get(source["id"]) or {},
                                  anchors.get(source["id"]) or ""))
        result[source["id"]] = outcome
    return result


def _judge(source: dict, outcome: dict, row: dict, anchored_on: str) -> dict:
    question = text(row.get("question"))
    if "left" in outcome:
        # The model saying "code cannot do this" is an answer worth keeping;
        # code refusing what it said, or it saying nothing, is worth a retry.
        return {"store": not outcome.get("retry"), "question": question}
    dates = _dates(outcome["items"])
    undated = any(kind == "request" and not value["dates"] for kind, value in outcome["items"])
    kind = row.get("kind") if row.get("kind") in TIMING_KINDS else "none"
    if dates and kind == "none":
        return {"store": False}
    if dates and not _believable(kind, dates, row, source["text"], anchored_on):
        return {"store": True, "left": UNREAD_TIME, "items": [], "question": ""}
    expires = "" if undated or not dates else max(dates).isoformat()
    return {"store": True, "expires_on": expires, "question": question}


def _believable(kind: str, dates: List[datetime.date], row: dict, sentence: str,
                anchored_on: str) -> bool:
    anchor = _date(anchored_on)
    if anchor is None:
        return False
    if kind == "relative":
        horizon = anchor + datetime.timedelta(days=RELATIVE_HORIZON_DAYS)
        starts, ends = _date(row.get("starts_on")), _date(row.get("ends_on"))
        maybe = _date(row.get("maybe_through")) if text(row.get("maybe_through")) else ends
        if None in (starts, ends, maybe) or not starts <= ends <= maybe:
            return False
        return all(anchor <= day <= horizon for day in dates)
    written = mentioned_dates(sentence, anchor)
    return bool(written) and all(min(written) <= day <= max(written) for day in dates)


def mentioned_dates(sentence: str, anchor: datetime.date) -> List[datetime.date]:
    """Every date written in `sentence`: ISO, `d.m`, `d/m`, `d.m.yy` and the
    range `d-d.m`. A year left out is the one that puts the date nearest
    after the anchor, give or take half a year."""
    found = []
    for match in _ISO.finditer(sentence or ""):
        found.append(_make(int(match.group(1)), int(match.group(2)), int(match.group(3))))
    for match in _RANGE.finditer(sentence or ""):
        month, year = int(match.group(3)), _year(match.group(4), anchor, int(match.group(3)))
        found.extend(_make(year, month, int(match.group(day))) for day in (1, 2))
    for match in _DAY.finditer(sentence or ""):
        month = int(match.group(2))
        found.append(_make(_year(match.group(3), anchor, month), month, int(match.group(1))))
    return [day for day in found if day is not None]


def _year(written: Optional[str], anchor: datetime.date, month: int) -> int:
    if written:
        year = int(written)
        return year + 2000 if year < 100 else year
    if month < anchor.month - 6:
        return anchor.year + 1
    if month > anchor.month + 6:
        return anchor.year - 1
    return anchor.year


def _make(year: int, month: int, day: int) -> Optional[datetime.date]:
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def _dates(items: List[tuple]) -> List[datetime.date]:
    values = []
    for kind, value in items:
        values.extend(value["dates"] if kind == "request" else [value["date"]])
    return [day for day in (_date(value) for value in values) if day is not None]


def _timing_rows(answer: Any) -> Dict[str, dict]:
    rows = answer.get("timing") if isinstance(answer, dict) else None
    if not isinstance(rows, list):
        return {}
    return {row.get("source_id"): row for row in rows if isinstance(row, dict)}


def _date(value: Any) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat(text(value))
    except ValueError:
        return None


__all__ = ["RELATIVE_HORIZON_DAYS", "TIMING_KINDS", "UNREAD_TIME", "mentioned_dates", "settle"]
