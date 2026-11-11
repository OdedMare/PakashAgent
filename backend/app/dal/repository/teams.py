"""Workspace persistence: one team, one boss password, one member link.

A team is the tenant. Every row that belongs to a workplace hangs off one,
which is why this module also owns the *scoped* reads — a caller that wants a
team's profile asks here rather than filtering in `bl/`, so a forgotten
WHERE clause cannot become a data leak between workplaces.

Passwords are hashed with `hashlib.scrypt` from the standard library. bcrypt
or argon2 would be the usual choice, but both are dependencies, chosen
against when this backend pinned Python 3.8.10 on an EOL Debian image where
every wheel that needed compiling was a real cost. scrypt is memory-hard,
ships with CPython, and is a genuine password hash -- unlike the SHA-256 that
usually gets reached for when a project wants to avoid a dependency.
"""

import hashlib
import hmac
import json
import os
import secrets
from typing import List, Optional

from psycopg.types.json import Jsonb

from app.common.errors import (
    PROFILE_CHANGED, AuthError, ConflictError, NotFoundError,
)
from app.dal.database import in_atomic
from app.dal.repository.base import RepositoryBase, new_id
from app.dal.repository.profile_cache import ProfileCache

# Per process, shared by every repository instance (`profile_cache.py`).
_profiles = ProfileCache()

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
        return self._all(
            "SELECT id, name, created_at, active FROM teams ORDER BY name"
        )

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
        """The workplace profile saved by the manager.

        The document is sent only when it changed since this process last
        read it (`profile_cache.py`); the row is read every time, so a save
        from any process is seen on the very next read.
        """
        key = (getattr(self._store.get(), "database_schema", ""), team_id)
        cacheable = not in_atomic(self._store)
        revision, updated_at = _profiles.version(key) if cacheable else (None, None)
        rows = self._all("""
            SELECT revision, updated_at,
                   CASE WHEN revision=%s AND updated_at=%s THEN NULL
                        ELSE profile::text END AS profile
            FROM team_profiles WHERE team_id=%s
        """, (revision, updated_at, team_id))
        if not rows:
            _profiles.drop(key)
            return None
        row = rows[0]
        text = row["profile"]
        if text is None:
            text = _profiles.text(key, row["revision"], row["updated_at"])
            if text is None:  # dropped in between: read it whole
                return self._uncached_profile(team_id)
        elif cacheable:
            _profiles.keep(key, row["revision"], row["updated_at"], text)
        return json.loads(text)

    def _uncached_profile(self, team_id: str) -> Optional[dict]:
        rows = self._all(
            "SELECT profile FROM team_profiles WHERE team_id=%s", (team_id,)
        )
        return rows[0]["profile"] if rows else None

    def team_profile_revision(self, team_id: str) -> Optional[int]:
        """The profile's revision, which a save may name to refuse a stale
        edit; None before the first save."""
        rows = self._all(
            "SELECT revision FROM team_profiles WHERE team_id=%s", (team_id,)
        )
        return rows[0]["revision"] if rows else None

    def update_team_profile(
        self, team_id: str, profile: dict,
        expected_revision: Optional[int] = None,
    ) -> dict:
        """Replace the team's working profile.

        With `expected_revision`, only if nobody saved since that revision
        was read: the check and the write are one statement, so two saves
        racing each other cannot both pass it.
        """
        rows = self._all("""
            UPDATE team_profiles SET profile=%s, updated_at=NOW(),
                revision=revision + 1
            WHERE team_id=%s AND (%s::int IS NULL OR revision=%s::int)
            RETURNING team_id
        """, (Jsonb(profile), team_id, expected_revision, expected_revision))
        if rows:
            return profile
        if expected_revision is not None and self.team_profile(team_id) is not None:
            raise ConflictError(PROFILE_CHANGED)
        raise NotFoundError("פרופיל הצוות לא נמצא")

    def create_team_profile(self, team_id: str, profile: dict) -> dict:
        """Create the team's first manually configured profile.

        Two first saves racing each other: the second is refused as stale
        rather than failing on the primary key.
        """
        rows = self._all("""
            INSERT INTO team_profiles (team_id, profile) VALUES (%s,%s)
            ON CONFLICT (team_id) DO NOTHING RETURNING team_id
        """, (team_id, Jsonb(profile)))
        if not rows:
            raise ConflictError(PROFILE_CHANGED)
        return profile


__all__ = [
    "TeamRepository", "hash_password", "verify_password", "new_member_token",
]
