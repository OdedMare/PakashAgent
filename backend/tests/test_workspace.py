"""Workspace rules: passwords, share links, and the boss/member split.

The crypto helpers are tested directly because they are the whole security
story of this feature -- a hash that does not salt or a signature that is not
verified would pass every HTTP test in the suite while being worthless.
"""

import pytest

from app.bl.workspace_service import WorkspaceService
from app.common.errors import AgentError, AuthError, ConflictError
from app.common.sessions import (
    ROLE_BOSS, ROLE_MEMBER, generate_secret, issue, read,
)
from app.dal.repository.teams import (
    hash_password, new_member_token, verify_password,
)


class _FakeTeams:
    """The team half of the repository, in memory."""

    def __init__(self):
        self.teams = {}
        self.orphans = 0
        self._next = 0

    def create_team(self, name, password):
        self._next += 1
        team_id = "team-%d" % self._next
        self.teams[team_id] = {
            "id": team_id, "name": name,
            "password_hash": hash_password(password),
            "member_token": new_member_token(),
        }
        return dict(self.teams[team_id])

    def get_team(self, team_id):
        return dict(self.teams[team_id])

    def list_teams(self):
        return [dict(team) for team in self.teams.values()]

    def authenticate_boss(self, team_id, password):
        team = self.teams.get(team_id)
        if team is None or not verify_password(password, team["password_hash"]):
            raise AuthError("שם הצוות או הסיסמה שגויים")
        return dict(team)

    def team_by_member_token(self, token):
        for team in self.teams.values():
            if team["member_token"] == token:
                return dict(team)
        raise AuthError("הקישור אינו תקף")

    def rotate_member_token(self, team_id):
        self.teams[team_id]["member_token"] = new_member_token()
        return dict(self.teams[team_id])

    def set_password(self, team_id, password):
        self.teams[team_id]["password_hash"] = hash_password(password)

    def team_profile(self, team_id):
        return None

    def claim_orphan_sessions(self, team_id):
        claimed, self.orphans = self.orphans, 0
        return claimed


@pytest.fixture
def service():
    return WorkspaceService(_FakeTeams())


# --- password hashing -------------------------------------------------------

def test_the_password_is_never_stored_in_the_clear():
    stored = hash_password("sod-gadol")

    assert "sod-gadol" not in stored
    assert stored.startswith("scrypt$")


def test_the_same_password_hashes_differently_every_time():
    """A shared salt would make identical passwords visibly identical in the
    table, and would let one rainbow table cover every team at once."""
    assert hash_password("same") != hash_password("same")


def test_a_correct_password_verifies_and_a_wrong_one_does_not():
    stored = hash_password("correct-horse")

    assert verify_password("correct-horse", stored) is True
    assert verify_password("correct-hors", stored) is False
    assert verify_password("", stored) is False


@pytest.mark.parametrize("corrupt", ["", "nonsense", "sha256$aa$bb", "a$b"])
def test_a_corrupt_hash_reads_as_a_wrong_password_not_a_crash(corrupt):
    """The caller is a login. A malformed row must not become a 500 that
    tells the sender something about the state of the database."""
    assert verify_password("anything", corrupt) is False


# --- session cookies --------------------------------------------------------

def test_a_signed_session_round_trips():
    secret = generate_secret()

    payload = read(secret, issue(secret, "team-9", ROLE_BOSS, 30))

    assert payload["team_id"] == "team-9"
    assert payload["role"] == ROLE_BOSS


def test_a_cookie_signed_with_another_secret_is_rejected():
    cookie = issue(generate_secret(), "team-9", ROLE_BOSS, 30)

    assert read(generate_secret(), cookie) is None


def test_a_tampered_payload_is_rejected():
    """The forgery this exists to stop: keep a valid signature, swap the body
    for one naming another team, and walk into their workspace."""
    secret = generate_secret()
    signature = issue(secret, "team-mine", ROLE_BOSS, 30).rpartition(".")[2]
    forged_body = issue(secret, "team-theirs", ROLE_BOSS, 30).partition(".")[0]

    assert read(secret, "%s.%s" % (forged_body, signature)) is None


def test_a_member_cannot_promote_themselves_by_editing_the_role():
    secret = generate_secret()
    signature = issue(secret, "team-9", ROLE_MEMBER, 30).rpartition(".")[2]
    promoted = issue(secret, "team-9", ROLE_BOSS, 30).partition(".")[0]

    assert read(secret, "%s.%s" % (promoted, signature)) is None


def test_an_expired_session_is_rejected():
    secret = generate_secret()

    assert read(secret, issue(secret, "team-9", ROLE_BOSS, -1)) is None


@pytest.mark.parametrize("cookie", [None, "", "junk", "a.b", "..", "a."])
def test_a_malformed_cookie_is_rejected(cookie):
    assert read(generate_secret(), cookie) is None


# --- workspace rules --------------------------------------------------------

def test_creating_a_workspace_returns_a_boss_role_and_a_share_link(service):
    team = service.create("צוות תפעול", "sod-gadol")

    assert team["name"] == "צוות תפעול"
    assert team["role"] == ROLE_BOSS
    assert team["member_token"]


def test_the_password_hash_never_reaches_the_api(service):
    """`_public` names what goes out rather than deleting what must not, so
    a column added to the table cannot leak by default."""
    team = service.create("צוות", "sod-gadol")

    assert "password_hash" not in team


def test_a_short_password_is_refused_in_hebrew(service):
    with pytest.raises(AgentError) as caught:
        service.create("צוות", "123")

    assert "סיסמה" in str(caught.value)


def test_an_empty_team_name_is_refused(service):
    with pytest.raises(AgentError):
        service.create("   ", "sod-gadol")


def test_logging_in_with_the_right_password_returns_a_boss_session(service):
    created = service.create("צוות", "sod-gadol")

    team = service.login(created["id"], "sod-gadol")

    assert team["id"] == created["id"]
    assert team["role"] == ROLE_BOSS


def test_logging_in_with_the_wrong_password_raises(service):
    created = service.create("צוות", "sod-gadol")

    with pytest.raises(AuthError):
        service.login(created["id"], "sod-katan")


def test_an_unknown_team_and_a_wrong_password_report_the_same_thing(service):
    """Otherwise the login endpoint enumerates which workspaces exist."""
    created = service.create("צוות", "sod-gadol")

    with pytest.raises(AuthError) as wrong:
        service.login(created["id"], "nope")
    with pytest.raises(AuthError) as missing:
        service.login("team-does-not-exist", "nope")

    assert str(wrong.value) == str(missing.value)


def test_a_share_link_opens_the_team_as_a_member(service):
    created = service.create("צוות", "sod-gadol")

    member = service.open_member_link(created["member_token"])

    assert member["id"] == created["id"]
    assert member["role"] == ROLE_MEMBER


def test_a_member_is_never_handed_the_share_token_back(service):
    """It arrived in a URL; echoing it into a response body puts it in
    browser history and in any screenshot of the member's screen."""
    created = service.create("צוות", "sod-gadol")

    member = service.open_member_link(created["member_token"])

    assert member["member_token"] is None


def test_an_invalid_share_link_is_refused(service):
    service.create("צוות", "sod-gadol")

    with pytest.raises(AuthError):
        service.open_member_link("not-a-real-token")


def test_rotating_the_link_invalidates_the_old_one(service):
    """The only revocation available, since members hold a link, not an
    account -- this is what happens when someone leaves the team."""
    created = service.create("צוות", "sod-gadol")
    old_token = created["member_token"]

    rotated = service.rotate_member_link(created["id"])

    assert rotated["member_token"] != old_token
    with pytest.raises(AuthError):
        service.open_member_link(old_token)
    assert service.open_member_link(rotated["member_token"])["id"] == created["id"]


def test_two_workspaces_get_different_share_links(service):
    first = service.create("צוות א", "sod-gadol")
    second = service.create("צוות ב", "sod-gadol")

    assert first["member_token"] != second["member_token"]
    assert service.open_member_link(first["member_token"])["id"] == first["id"]
    assert service.open_member_link(second["member_token"])["id"] == second["id"]


def test_the_team_list_carries_no_secrets(service):
    """It is served to anyone who loads the login screen."""
    service.create("צוות", "sod-gadol")

    listed = service.list_teams()

    assert [key for key in listed[0]] == ["id", "name"]


def test_changing_the_password_requires_the_current_one(service):
    """A live session is not authority to change the credential it came
    from -- otherwise an unattended browser is a permanent takeover."""
    created = service.create("צוות", "sod-gadol")

    with pytest.raises(AuthError):
        service.change_password(created["id"], "wrong", "sod-hadash")

    service.change_password(created["id"], "sod-gadol", "sod-hadash")
    assert service.login(created["id"], "sod-hadash")
    with pytest.raises(AuthError):
        service.login(created["id"], "sod-gadol")


def test_reusing_the_same_password_is_refused(service):
    created = service.create("צוות", "sod-gadol")

    with pytest.raises(ConflictError):
        service.change_password(created["id"], "sod-gadol", "sod-gadol")


def test_the_first_workspace_adopts_interviews_that_predate_workspaces(service):
    """An existing install's finished interview would otherwise become
    unreachable the moment every read starts filtering by team."""
    service._repository.orphans = 3

    first = service.create("צוות א", "sod-gadol")
    second = service.create("צוות ב", "sod-gadol")

    assert first["claimed_sessions"] == 3
    assert second["claimed_sessions"] == 0
