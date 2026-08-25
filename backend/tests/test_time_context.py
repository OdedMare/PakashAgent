"""Backend-owned Israel clock, independent of the machine's local timezone."""

import datetime

import pytest

from app.common.time_context import agent_time_context, israel_datetime, israel_today


UTC = datetime.timezone.utc


def test_agent_context_contains_the_full_israel_clock_in_summer():
    context = agent_time_context(datetime.datetime(2026, 8, 25, 12, 36, tzinfo=UTC))

    assert "Timezone: Asia/Jerusalem" in context
    assert "Local datetime: 2026-08-25T15:36:00+03:00" in context
    assert "Local date: 2026-08-25" in context
    assert "Day of week: Tuesday" in context
    assert "Local time: 15:36" in context


def test_iana_timezone_applies_winter_standard_time():
    local = israel_datetime(datetime.datetime(2026, 1, 15, 12, 0, tzinfo=UTC))

    assert local.isoformat() == "2026-01-15T14:00:00+02:00"


def test_utc_to_israel_conversion_rolls_the_calendar_at_midnight():
    instant = datetime.datetime(2026, 8, 24, 21, 30, tzinfo=UTC)

    assert israel_datetime(instant).isoformat() == "2026-08-25T00:30:00+03:00"
    assert israel_today(instant).isoformat() == "2026-08-25"


def test_an_ambiguous_naive_datetime_is_rejected():
    with pytest.raises(ValueError):
        israel_datetime(datetime.datetime(2026, 8, 25, 12, 0))
