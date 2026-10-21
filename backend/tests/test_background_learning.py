"""What the agent notices on its own from the manager's corrections.

- **A counted pattern becomes a visible suggestion.** `observe_corrections`
  has always tallied what the manager keeps fixing and `agent_preferences`
  has always been able to hold a `suggested` row; nothing wrote one. These
  assert that it now does, that it does so **inertly**, and that it does so
  **once** -- a suggestion that came back every time the manager opened the
  screen would be the agent nagging.
- **Nothing about it writes a schedule.** It runs off a read, so the
  stored period is asserted byte-identical afterwards.
"""

import json


from app.bl.schedule_service import ScheduleService
from app.common.errors import AgentError
from app.dal.repository.schedules import (
    PREFERENCE_SUGGESTED,
    SOURCE_AGENT,
)

from tests.test_agent_api import _RepoWithPreferences, _seed
from tests.test_schedule_api import MORNING, TEAM

DANA = "דנה"
YOSSI = "יוסי"


class _NoModel:
    """No model configured -- the deployment default here."""

    def complete_json(self, *args, **kwargs):
        raise AgentError("לא הוגדר מפתח API או שרת תואם OpenAI")


def _service(llm=None):
    repository = _RepoWithPreferences()
    return ScheduleService(repository, llm or _NoModel()), repository


def _corrections(repo, times, employee=DANA, shift=MORNING):
    """`times` corrections of the same person off the same shift+weekday.

    Seven days apart so every one lands on the same weekday, which is what
    the tally is keyed on -- a rule is about Fridays, not about the 3rd.
    """
    for index in range(times):
        repo.append_change(
            TEAM,
            action="moved",
            employee=YOSSI,
            replaced_employee=employee,
            slot_date="2026-08-%02d" % (3 + index * 7),
            shift_name=shift,
            reason="לימודים",
        )


# -- a counted pattern becomes a suggestion --------------------------------


def test_a_repeated_correction_is_remembered_as_a_suggestion():
    """The gap that was open: nothing joined the tally to the table."""
    service, repo = _service()
    _corrections(repo, 3)

    remembered = service.observe_quietly(TEAM)

    assert len(remembered) == 1
    assert remembered[0]["status"] == PREFERENCE_SUGGESTED
    assert remembered[0]["source"] == SOURCE_AGENT
    assert DANA in remembered[0]["text"]


def test_a_suggestion_carries_the_count_and_the_managers_own_reason():
    """Evidence is what makes a suggestion something one can approve (D21)."""
    service, repo = _service()
    _corrections(repo, 3)

    remembered = service.observe_quietly(TEAM)

    evidence = remembered[0]["evidence"]
    assert "3" in evidence
    # The manager's own word, not a paraphrase of it.
    assert "לימודים" in evidence


def test_a_single_correction_is_not_a_pattern():
    """One is not a pattern; it is a Tuesday."""
    service, repo = _service()
    _corrections(repo, 1)

    assert service.observe_quietly(TEAM) == []
    assert repo.preferences(TEAM) == []


def test_the_same_pattern_is_never_suggested_twice():
    """Otherwise every refresh of the screen adds another identical row."""
    service, repo = _service()
    _corrections(repo, 3)

    service.observe_quietly(TEAM)
    service.observe_quietly(TEAM)
    service.observe_quietly(TEAM)

    assert len(repo.preferences(TEAM)) == 1


def test_a_dismissed_suggestion_does_not_come_back():
    """A decision the manager made is not overruled by a background pass."""
    service, repo = _service()
    _corrections(repo, 3)
    remembered = service.observe_quietly(TEAM)
    service.update_preference(TEAM, remembered[0]["id"], status="archived")

    service.observe_quietly(TEAM)

    rows = repo.preferences(TEAM)
    assert len(rows) == 1
    assert rows[0]["status"] == "archived"


def test_a_suggestion_is_inert_until_approved():
    """`ask()` reads only active rows, so a suggestion authorises nothing."""
    service, repo = _service()
    _corrections(repo, 3)

    service.observe_quietly(TEAM)

    assert service.preferences(TEAM, status="active") == []
    assert len(service.preferences(TEAM, status=PREFERENCE_SUGGESTED)) == 1


def test_learning_in_the_background_calls_no_model():
    """Wording is a model's job; a *pattern* is arithmetic, and only
    arithmetic may run unattended."""
    class _Explodes:
        def complete_json(self, *args, **kwargs):
            raise AssertionError("the background path must not call a model")

    service, repo = _service(_Explodes())
    _corrections(repo, 3)

    assert len(service.observe_quietly(TEAM)) == 1


def test_background_learning_never_raises():
    """It is a side effect of a screen that must render regardless."""
    class _BrokenRepo(_RepoWithPreferences):
        def change_log(self, *args, **kwargs):
            raise RuntimeError("database is down")

    service = ScheduleService(_BrokenRepo(), _NoModel())

    assert service.observe_quietly(TEAM) == []


def test_learning_writes_no_schedule():
    """The whole path runs off a read."""
    service, repo = _service()
    _seed(repo)
    _corrections(repo, 3)
    before = json.dumps(repo.assignments, sort_keys=True, default=str)

    service.observe_quietly(TEAM)

    assert json.dumps(repo.assignments, sort_keys=True, default=str) == before


def test_one_workspace_never_learns_from_another():
    """Every read is scoped by the team from the signed session (D10)."""
    service, repo = _service()
    _corrections(repo, 3)

    assert service.observe_quietly("other-team") == []


