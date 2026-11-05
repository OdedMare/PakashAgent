"""The מכלול commander's one chat, speaking to every משמרת (D43).

Two things are pinned: which משמרות a sentence goes to is read in code
(`bl/complex_routing.py`), and a משמרת's conversation is reachable from the
מכלול screen by path -- only for the commander's own משמרות, and as the
same `commander-<id>` conversations "כניסה לניהול" opens.
"""

from fastapi import Depends

from app.bl.complex_routing import route
from tests.test_complex_api import _as_commander, _open_complex, world  # noqa: F401

TEAMS = [
    {"id": "a", "name": "משמרת א", "employees": ["דנה כהן", "יוסי לוי"]},
    {"id": "b", "name": "משמרת ב", "employees": ["רוני בר"]},
    {"id": "c", "name": "צוות חמ\"ל", "employees": ["שירה טל"]},
]


def test_a_named_team_is_addressed():
    assert route("במשמרת ב מי חסר מחר?", TEAMS) == {"team_ids": ["b"], "by": "team"}
    assert route("תבנה את השבוע למשמרת א' ולמשמרת ב'", TEAMS)["team_ids"] == ["a", "b"]


def test_a_team_named_without_its_prefix_is_addressed():
    assert route("מה המצב בחמ\"ל?", TEAMS) == {"team_ids": ["c"], "by": "team"}


def test_a_named_soldier_addresses_their_own_team():
    assert route("רוני בר חולה מחר", TEAMS) == {"team_ids": ["b"], "by": "soldier"}
    assert route("תוריד את דנה כהן ביום שלישי", TEAMS)["team_ids"] == ["a"]


def test_a_unique_first_name_is_enough():
    assert route("שירה לא מגיעה מחר", TEAMS)["team_ids"] == ["c"]
    shared = TEAMS + [{"id": "d", "name": "משמרת ד", "employees": ["שירה גל"]}]
    assert route("שירה לא מגיעה מחר", shared)["by"] == "all"


def test_a_sentence_naming_neither_goes_to_every_team():
    assert route("מי חסר השבוע?", TEAMS) == {"team_ids": ["a", "b", "c"], "by": "all"}


def test_a_word_inside_another_word_is_not_a_name():
    assert route("משמרת ארוכה מדי", TEAMS)["by"] == "all"


def _chat_world(world):  # noqa: F811
    client, repository, complexes, ids = world
    app = client.app
    from app.api.routers import manager_chat
    from tests.test_complex_api import SECRET
    from app.api.dependencies import Guards

    guards = Guards(SECRET, team_active=repository.team_is_active,
                    team_in_complex=repository.team_in_complex,
                    complex_active=repository.complex_is_active)
    seen = []

    class _Repo:
        def list_chats(self, team_id, manager_id):
            seen.append((team_id, manager_id))
            return []

    app.include_router(manager_chat.build_commander_router(None, _Repo(), guards))
    return client, ids, seen


def test_the_commander_reaches_each_linked_teams_chat_by_path(world):  # noqa: F811
    client, ids, seen = _chat_world(world)
    created = _open_complex(client, ids[:2])
    _as_commander(client, created["id"])

    for team_id in ids[:2]:
        assert client.get("/api/complex/teams/%s/chats" % team_id).status_code == 200
    assert seen == [(ids[0], "commander-" + created["id"]),
                    (ids[1], "commander-" + created["id"])]


def test_a_team_outside_the_complex_is_refused(world):  # noqa: F811
    client, ids, seen = _chat_world(world)
    created = _open_complex(client, ids[:2])
    _as_commander(client, created["id"])

    assert client.get("/api/complex/teams/%s/chats" % ids[2]).status_code == 403
    assert seen == []


def test_without_a_commander_cookie_the_path_is_refused(world):  # noqa: F811
    client, ids, seen = _chat_world(world)
    _open_complex(client, ids[:2])
    client.cookies.clear()
    assert client.get("/api/complex/teams/%s/chats" % ids[0]).status_code == 401
