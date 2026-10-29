"""Who the change log says was acting (`common/actor.py`)."""

from app.common.actor import acting_as, actor_of, current_actor


def test_a_boss_is_told_apart_by_their_manager_cookie():
    session = {"role": "boss", "team_id": "t1"}
    assert actor_of(session, {"team_id": "t1", "manager_id": "m1"}) == "boss:m1"
    assert actor_of(session, None) == "boss"


def test_a_manager_cookie_for_another_team_names_nobody():
    session = {"role": "boss", "team_id": "t1"}
    assert actor_of(session, {"team_id": "t2", "manager_id": "m1"}) == "boss"


def test_an_employee_is_named_and_a_member_is_only_a_role():
    assert actor_of({"role": "employee", "employee": "דנה"}) == "employee:דנה"
    assert actor_of({"role": "member"}) == "member"


def test_the_actor_holds_only_inside_its_block():
    assert current_actor() == ""
    with acting_as("boss:m1"):
        assert current_actor() == "boss:m1"
    assert current_actor() == ""
