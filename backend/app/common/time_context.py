"""Israel-local time for agent context and scheduling calendar decisions."""

import datetime
from typing import Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python 3.8 deployment target
    from backports.zoneinfo import ZoneInfo


ISRAEL_TIMEZONE = "Asia/Jerusalem"
_ISRAEL = ZoneInfo(ISRAEL_TIMEZONE)


def israel_datetime(
    now: Optional[datetime.datetime] = None,
) -> datetime.datetime:
    """Current UTC instant converted to Israel's IANA timezone."""
    instant = now or datetime.datetime.now(datetime.timezone.utc)
    if instant.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return instant.astimezone(_ISRAEL)


def israel_today(
    now: Optional[datetime.datetime] = None,
) -> datetime.date:
    return israel_datetime(now).date()


def agent_time_context(
    now: Optional[datetime.datetime] = None,
) -> str:
    """Machine-readable clock plus the rules every model invocation follows."""
    local = israel_datetime(now).replace(microsecond=0)
    return """Current date and time:
- Timezone: {timezone}
- Local datetime: {datetime}
- Local date: {date}
- Day of week: {weekday}
- Local time: {time}

Time interpretation rules:
- Treat this backend-provided datetime as the only source of current time.
- Interpret relative dates and times using this Israel time unless the user explicitly specifies another timezone or location.
- This includes today/היום, tomorrow/מחר, yesterday/אתמול, now/עכשיו, tonight/הערב, this morning/הבוקר, and this week/השבוע.
- Never infer the current date or time from training data, the browser, or the user's device.
- Resolve scheduling tool dates and times to absolute ISO values; never pass relative expressions to a tool. Use timezone {timezone} when the user did not specify another timezone.
""".format(
        timezone=ISRAEL_TIMEZONE,
        datetime=local.isoformat(),
        date=local.date().isoformat(),
        weekday=local.strftime("%A"),
        time=local.strftime("%H:%M"),
    )


__all__ = [
    "ISRAEL_TIMEZONE", "agent_time_context", "israel_datetime", "israel_today",
]
