"""Prompt loading and include resolution."""

import pytest

from app.bl import prompts


@pytest.fixture(autouse=True)
def _fresh_cache():
    """Every test reads from disk, so one test's load cannot serve another."""
    prompts.clear_cache()
    yield
    prompts.clear_cache()


def test_the_manager_chat_prompt_resolves_every_include():
    text = prompts.load("manager_chat")

    assert "<!-- include:" not in text
    assert "## Language" in text


def test_a_missing_prompt_raises_rather_than_returning_empty():
    with pytest.raises(FileNotFoundError):
        prompts.load("no_such_prompt")


def test_a_name_cannot_climb_out_of_the_prompts_directory():
    with pytest.raises(FileNotFoundError):
        prompts.load("../../main")


def test_the_prompt_is_cached_and_reload_re_reads():
    first = prompts.load("scheduler_directives")
    second = prompts.load("scheduler_directives")

    # Same object, so the second call did not touch the disk.
    assert first is second
    assert prompts.load("scheduler_directives", reload=True) == first


def test_directives_expand_absence_ranges():
    directives = prompts.load("scheduler_directives")

    assert "בין שני לחמישי" in directives
    assert "every supplied\nshift" in directives


