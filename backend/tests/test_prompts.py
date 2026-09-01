"""Prompt loading and include resolution.

The loader gained includes so the interview wording could be split into
shared fragments, the way AiSummryIO composes its planner prompts. These are
the strings the model is told to obey, so a silently empty or half-resolved
prompt is worse than a crash — that is what most of this asserts.
"""

import re
from pathlib import Path

import pytest

from app.bl import prompts


@pytest.fixture(autouse=True)
def _fresh_cache():
    """Every test reads from disk, so one test's load cannot serve another."""
    prompts.clear_cache()
    yield
    prompts.clear_cache()


def test_the_interview_prompt_resolves_every_include():
    text = prompts.load("interview")

    assert "<!-- include:" not in text
    assert "## How you interview" in text
    assert "## Untrusted input" in text
    assert "## Language" in text


def test_the_interview_prompt_keeps_its_own_body():
    """The includes are additions to the domain wording, not a replacement
    for it — the shift rules are the part only this product has."""
    text = prompts.load("interview")

    assert "Understanding shifts" in text
    assert "start_time" in text


def test_a_shared_fragment_loads_on_its_own():
    assert "one question per turn" in prompts.load(
        "shared/interview_method"
    ).lower()


def test_a_missing_prompt_raises_rather_than_returning_empty():
    with pytest.raises(FileNotFoundError):
        prompts.load("no_such_prompt")


def test_a_name_cannot_climb_out_of_the_prompts_directory():
    with pytest.raises(FileNotFoundError):
        prompts.load("../../main")


def test_the_prompt_is_cached_and_reload_re_reads():
    first = prompts.load("interview")
    second = prompts.load("interview")

    # Same object, so the second call did not touch the disk.
    assert first is second
    assert prompts.load("interview", reload=True) == first


def test_scheduler_distinguishes_closures_from_shift_count_fairness():
    text = prompts.load("scheduler")

    assert "A **closure** is a stretch" in text
    assert "Never move a closure to another group" in text
    assert "first_closure_group" in text
    assert "round_first_closure" in text
    assert "triplet_first_closure" in text


def test_the_closure_fragment_is_shared_by_both_writing_prompts():
    """The rotation wording drifted between these two while it was copied
    into each; one fragment is what keeps them from disagreeing."""
    fragment = prompts.load("shared/closures")

    for name in ("scheduler", "changes"):
        assert fragment in prompts.load(name)


def test_every_prompt_is_written_in_english():
    """Instructions are English so they stay reviewable; the two Hebrew
    literals that remain are input the model must recognise, not prose."""
    allowed = {"\u05dc\u05d0 \u05d6\u05de\u05d9\u05df", "\u05d4\u05d9\u05d5\u05dd", "\u05de\u05d7\u05e8"}
    hebrew = re.compile(r"[\u0590-\u05ff]+(?: [\u0590-\u05ff]+)*")

    for path in sorted(Path(prompts.__file__).parent.glob("**/*.md")):
        found = set(hebrew.findall(path.read_text(encoding="utf-8")))
        assert found <= allowed, (path.name, found - allowed)


def test_interview_collects_separate_round_and_triplet_anchors():
    text = prompts.load("interview", reload=True)

    assert "round_first_closure_date" in text
    assert "triplet_first_closure_date" in text


def test_briefing_prioritizes_the_closing_group_before_fairness():
    text = prompts.load("briefing", reload=True)

    assert "schedule.closures" in text
    assert "cross_rotation" in text
    assert "closure continuity comes first" in text
