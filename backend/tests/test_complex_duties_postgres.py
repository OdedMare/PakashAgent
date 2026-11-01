"""A מכלול's duties against a real PostgreSQL.

Skipped without `CHAT_TEST_DSN`, like the other `_postgres` tests. Pins the
scoping (a commander reaches only their own מכלול's types and teams), one
duty per soldier per day, the projection into each team's availability, and
that the team's own constraint delete cannot remove one.
"""

import pytest

from app.common.errors import AgentError, ConflictError, NotFoundError

from tests.test_admin_postgres import pytestmark, repo  # noqa: F401  (fixture)

DAY = "2026-11-10"


@pytest.fixture
def complex_setup(repo):  # noqa: F811
    first = repo.create_team("משמרת א", "pw-1")
    second = repo.create_team("משמרת ב", "pw-2")
    outsider = repo.create_team("משמרת אחרת", "pw-3")
    mine = repo.create_complex("מכלול", "pw")
    other = repo.create_complex("מכלול אחר", "pw")
    repo.set_complex_teams(mine["id"], [first["id"], second["id"]])
    repo.set_complex_teams(other["id"], [outsider["id"]])
    kitchen = repo.create_complex_duty_type(mine["id"], "מטבח", seats=2, weight=1)
    return dict(repo=repo, mine=mine["id"], other=other["id"], first=first["id"],
                second=second["id"], outsider=outsider["id"], kitchen=kitchen)


def test_a_duty_type_is_named_once_per_complex(complex_setup):
    repo, mine, other = complex_setup["repo"], complex_setup["mine"], complex_setup["other"]

    with pytest.raises(ConflictError):
        repo.create_complex_duty_type(mine, "מטבח")
    repo.create_complex_duty_type(other, "מטבח")  # another מכלול may

    guard = repo.create_complex_duty_type(mine, "שמירה", days=["שישי", "שבת"], weight=2)
    with pytest.raises(ConflictError):
        repo.update_complex_duty_type(mine, guard["id"], {"name": "מטבח"})
    updated = repo.update_complex_duty_type(mine, guard["id"], {"seats": 3})
    assert (updated["seats"], updated["weight"], updated["days"]) == (3, 2, ["שישי", "שבת"])
    assert [row["name"] for row in repo.complex_duty_types(mine)] == ["מטבח", "שמירה"]


def test_a_commander_reaches_only_their_own_types_and_teams(complex_setup):
    s = complex_setup
    repo, kitchen = s["repo"], s["kitchen"]

    with pytest.raises(NotFoundError):  # a team outside the מכלול
        repo.set_complex_duty(s["mine"], kitchen["id"], s["outsider"], "דנה", DAY)
    with pytest.raises(NotFoundError):  # another מכלול's commander, my type
        repo.set_complex_duty(s["other"], kitchen["id"], s["outsider"], "דנה", DAY)
    with pytest.raises(NotFoundError):
        repo.complex_duty_type(s["other"], kitchen["id"])

    duty = repo.set_complex_duty(s["mine"], kitchen["id"], s["first"], "דנה", DAY)
    with pytest.raises(NotFoundError):
        repo.delete_complex_duty(s["other"], duty["id"])
    assert repo.complex_duties(s["other"], DAY, DAY) == []


def test_one_duty_per_soldier_per_day(complex_setup):
    s = complex_setup
    repo = s["repo"]
    guard = repo.create_complex_duty_type(s["mine"], "שמירה")
    repo.set_complex_duty(s["mine"], s["kitchen"]["id"], s["first"], "דנה", DAY)

    with pytest.raises(ConflictError):
        repo.set_complex_duty(s["mine"], guard["id"], s["first"], "דנה", DAY)
    # The same name in another משמרת is another soldier.
    repo.set_complex_duty(s["mine"], guard["id"], s["second"], "דנה", DAY)

    rows = repo.complex_duties(s["mine"], DAY, DAY)
    assert sorted((row["team_name"], row["duty_type"]) for row in rows) == [
        ("משמרת א", "מטבח"), ("משמרת ב", "שמירה"),
    ]


def test_a_duty_blocks_the_day_in_its_own_team_only(complex_setup):
    s = complex_setup
    repo = s["repo"]
    duty = repo.set_complex_duty(s["mine"], s["kitchen"]["id"], s["first"], "דנה", DAY)

    rows = repo.availability(s["first"], DAY, DAY)
    assert [(r["employee"], r["constraint_type"], r["start_time"], r["end_time"],
             r["reason"], r["source"]) for r in rows] == [
        ("דנה", "duty", "", "", "מטבח", "complex"),
    ]
    assert repo.availability(s["second"], DAY, DAY) == []
    # The day after the span reaches back to its last night.
    assert len(repo.availability(s["first"], "2026-11-09", "2026-11-09")) == 1
    assert repo.availability(s["first"], "2026-11-08", "2026-11-08") == []
    assert [r["duty_type"] for r in repo.team_complex_duties(s["first"], DAY, DAY)] == ["מטבח"]

    with pytest.raises(AgentError):  # the team's own delete cannot remove it
        repo.delete_availability(duty["id"], s["first"])
    repo.delete_complex_duty(s["mine"], duty["id"])
    assert repo.availability(s["first"], DAY, DAY) == []


def test_deleting_a_type_removes_its_assignments(complex_setup):
    s = complex_setup
    repo = s["repo"]
    repo.set_complex_duty(s["mine"], s["kitchen"]["id"], s["first"], "דנה", DAY)

    repo.delete_complex_duty_type(s["mine"], s["kitchen"]["id"])

    assert repo.complex_duties(s["mine"], DAY, DAY) == []
