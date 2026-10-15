"""Prompt loading and include resolution."""

import pytest

from app.bl import prompts


@pytest.fixture(autouse=True)
def _fresh_cache():
    """Every test reads from disk, so one test's load cannot serve another."""
    prompts.clear_cache()
    yield
    prompts.clear_cache()


def test_the_scheduler_prompt_resolves_every_include():
    text = prompts.load("scheduler")

    assert "<!-- include:" not in text
    assert "## Untrusted input" in text
    assert "## Language" in text


def test_a_missing_prompt_raises_rather_than_returning_empty():
    with pytest.raises(FileNotFoundError):
        prompts.load("no_such_prompt")


def test_a_name_cannot_climb_out_of_the_prompts_directory():
    with pytest.raises(FileNotFoundError):
        prompts.load("../../main")


def test_the_prompt_is_cached_and_reload_re_reads():
    first = prompts.load("scheduler")
    second = prompts.load("scheduler")

    # Same object, so the second call did not touch the disk.
    assert first is second
    assert prompts.load("scheduler", reload=True) == first


def test_scheduler_distinguishes_closures_from_shift_count_fairness():
    text = prompts.load("scheduler")

    assert "סגירה" in text
    assert "מחזור היציאות" in text
    assert "אל תעביר סגירה" in text
    assert "first_closure_group" in text
    assert "round_first_closure" in text
    assert "triplet_first_closure" in text


def test_scheduler_asks_for_rest_spacing_without_overriding_rotations_or_nights():
    text = prompts.load("scheduler")

    assert "consecutive calendar days" in text
    assert "maximize the gap" in text
    assert "Do not create an extra night" in text


def test_scheduler_enforces_eight_hours_and_directives_expand_absence_ranges():
    scheduler = prompts.load("scheduler")
    directives = prompts.load("scheduler_directives")

    assert "minimum is\n  eight hours" in scheduler
    assert "בין שני לחמישי" in directives
    assert "every supplied\nshift" in directives


def test_briefing_prioritizes_the_closing_group_before_fairness():
    text = prompts.load("briefing", reload=True)

    assert "schedule.closures" in text
    assert "cross_rotation" in text
    assert "closure continuity comes first" in text
