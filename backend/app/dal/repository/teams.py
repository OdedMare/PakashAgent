"""Workspace persistence: one team, one boss password, one member link.

A team is the tenant. Every row that belongs to a workplace hangs off one,
which is why this module also owns the *scoped* reads — a caller that wants a
team's interviews asks here rather than filtering in `bl/`, so a forgotten
WHERE clause cannot become a data leak between workplaces.

Passwords are hashed with `hashlib.scrypt` from the standard library. bcrypt
or argon2 would be the usual choice, but both are dependencies, and this
backend pins Python 3.8.10 against an EOL Debian image where every wheel that
needs compiling is a real cost (docs/BUILD_ORDER.md). scrypt is memory-hard,
ships with CPython, and is a genuine password hash -- unlike the SHA-256 that
usually gets reached for when a project wants to avoid a dependency.
"""

import hashlib
import hmac
import os
import secrets
from typing import List, Optional

from app.common.errors import AuthError, ConflictError
from app.dal.database.postgres import connect
from app.dal.repository.base import RepositoryBase, new_id

# scrypt's cost parameters. n=2**14 with r=8 lands around 16MB and a few tens
# of milliseconds per verify -- slow enough to make guessing expensive, fast
# enough that a boss logging in does not notice.
_SCRYPT_N = 2 ** 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_BYTES = 16
# 32 bytes of urlsafe base64 is ~43 characters. The member link is the only
# thing standing between a stranger and the roster, so it is sized to be
# unguessable rather than pretty.
_TOKEN_BYTES = 32


def hash_password(password: str) -> str:
    """`scrypt$<salt-hex>$<hash-hex>`.

    The salt travels with the hash: it is not a secret, and storing it in the
    same column keeps a verify from needing a second lookup. The `scrypt$`
    prefix is what makes a future migration to another algorithm possible
    without a flag day -- `verify_password` can branch on it.
    """
    salt = os.urandom(_SALT_BYTES)
    derived = hashlib.scrypt(
        password.encode("utf-8"), salt=salt,
        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32,
    )
    return "scrypt$%s$%s" % (salt.hex(), derived.hex())


def verify_password(password: str, stored: str) -> bool:
    """Constant-time compare against a stored `hash_password` value.

    A malformed or unknown-scheme value returns False rather than raising:
    the caller is a login, and a corrupt row should read as "wrong password",
    not as a 500 that tells the sender something about the database.
    """
    try:
        scheme, salt_hex, expected_hex = stored.split("$")
    except (ValueError, AttributeError):
        return False
    if scheme != "scrypt":
        return False
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(expected_hex)
    except ValueError:
        return False
    derived = hashlib.scrypt(
        password.encode("utf-8"), salt=salt,
        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=len(expected),
    )
    return hmac.compare_digest(derived, expected)


def new_member_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


class TeamRepository(RepositoryBase):
    def create_team(self, name: str, password: str) -> dict:
        """Open a workspace. Returns the team *with* its member token."""
        team_id = new_id()
        self._execute("""
            INSERT INTO teams (id, name, password_hash, member_token)
            VALUES (%s,%s,%s,%s)
        """, (team_id, name, hash_password(password), new_member_token()))
        return self.get_team(team_id)

    def get_team(self, team_id: str) -> dict:
        return self._one("SELECT * FROM teams WHERE id=%s", (team_id,))

    def list_teams(self) -> List[dict]:
        """Every workspace, for the picker on the login screen.

        Deliberately returns the id and name only. The list is shown to
        anyone who loads the page -- it is how a boss finds their own team --
        so it must not carry the password hash or the member token with it.
        """
        return self._all("SELECT id, name, created_at FROM teams ORDER BY name")

    def authenticate_boss(self, team_id: str, password: str) -> dict:
        """The team if the password matches, `AuthError` if it does not.

        The same Hebrew message covers a wrong password and a team that does
        not exist, so a caller cannot use this endpoint to enumerate which
        workspaces are real.
        """
        rows = self._all("SELECT * FROM teams WHERE id=%s", (team_id,))
        team = rows[0] if rows else None
        # The hash is still verified against a dummy when the team is missing,
        # so a nonexistent team takes the same time as a wrong password and
        # cannot be spotted by how fast the answer comes back.
        stored = team["password_hash"] if team else hash_password("")
        if not verify_password(password, stored) or team is None:
            raise AuthError("שם הצוות או הסיסמה שגויים")
        return team

    def team_by_member_token(self, token: str) -> dict:
        """The team a share link points at. Possession of the token is the
        credential -- there is nothing else to check."""
        rows = self._all(
            "SELECT * FROM teams WHERE member_token=%s", (token,)
        )
        if not rows:
            raise AuthError("הקישור אינו תקף")
        return rows[0]

    def rotate_member_token(self, team_id: str) -> dict:
        """Invalidate the old share link and issue a new one.

        The only way to revoke access for someone who has left, since members
        hold a link rather than an account.
        """
        self._execute(
            "UPDATE teams SET member_token=%s WHERE id=%s",
            (new_member_token(), team_id),
        )
        return self.get_team(team_id)

    def set_password(self, team_id: str, password: str) -> None:
        self._execute(
            "UPDATE teams SET password_hash=%s WHERE id=%s",
            (hash_password(password), team_id),
        )

    def team_profile(self, team_id: str) -> Optional[dict]:
        """The workplace profile from this team's finished interview.

        The newest completed one wins. Re-running the interview is how a
        workplace gets re-taught, and the most recent answer is the one the
        boss meant.
        """
        rows = self._all("""
            SELECT profile FROM interview_sessions
            WHERE team_id=%s AND status='complete' AND profile IS NOT NULL
            ORDER BY updated_at DESC
            LIMIT 1
        """, (team_id,))
        return rows[0]["profile"] if rows else None

    def claim_orphan_sessions(self, team_id: str) -> int:
        """Adopt interviews recorded before workspaces existed.

        Those rows have `team_id IS NULL` and are otherwise unreachable once
        every read is scoped. Claiming them into the first team that is
        created is what keeps an existing install's interview from vanishing
        the moment this feature ships. Only ever claims once -- after the
        first team exists there are no NULL rows left to take.
        """
        with connect(self._store) as connection:
            row = connection.execute("""
                WITH claimed AS (
                    UPDATE interview_sessions SET team_id=%s
                    WHERE team_id IS NULL
                    RETURNING 1
                )
                SELECT count(*) AS n FROM claimed
            """, (team_id,)).fetchone()
            connection.commit()
        return int(row["n"]) if row else 0


__all__ = [
    "TeamRepository", "hash_password", "verify_password", "new_member_token",
]
