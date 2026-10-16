"""Bounding text and dates the way every part of the change path reads them."""

import datetime
from typing import Any

from app.bl.shared import bounded, dict_rows


def date_of(value: Any) -> str:
    """A date as `YYYY-MM-DD`, however the row happened to carry it.

    Repository rows come back as `datetime.date` and model output as strings;
    both are normalized to the one shape rather than trusted to match.
    """
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return bounded(value)


def json_default(value: Any) -> str:
    """SQL temporal values as JSON strings in raw availability/history rows."""
    if isinstance(value, (datetime.date, datetime.time)):
        return value.isoformat()
    raise TypeError(
        "Object of type %s is not JSON serializable" % value.__class__.__name__
    )
