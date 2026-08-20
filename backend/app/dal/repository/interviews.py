"""Intro-interview persistence.

`bl/interview.py` is stateless by design — the caller owns the conversation
and passes it back on every turn. This is that owner: the turns live here, so
a refresh resumes the interview instead of restarting it.

Every read is scoped by `team_id`. A session id is a UUID and therefore hard
to guess, but "hard to guess" is not an access control — one workspace's boss
must not be able to read another's interview by holding its id, so the team
is checked rather than trusted.
"""

from typing import List, Optional

from psycopg.types.json import Jsonb

from app.common.errors import ConflictError
from app.dal.database.postgres import connect
from app.dal.repository.base import RepositoryBase, new_id


class InterviewRepository(RepositoryBase):
    def create_session(self, team_id: str) -> dict:
        session_id = new_id()
        self._execute(
            "INSERT INTO interview_sessions (id, team_id) VALUES (%s,%s)",
            (session_id, team_id),
        )
        return self.get_session(session_id, team_id)

    def get_session(self, session_id: str, team_id: str) -> dict:
        """A session, but only if it belongs to this team.

        A mismatch raises NotFoundError from `_one` rather than a distinct
        "wrong team" error, so probing ids tells the caller nothing about
        which sessions exist in workspaces they cannot see.
        """
        session = self._one(
            "SELECT * FROM interview_sessions WHERE id=%s AND team_id=%s",
            (session_id, team_id),
        )
        session["turns"] = self.history(session_id)
        return session

    def active_session(self, team_id: str) -> Optional[dict]:
        """This team's interview in progress, if there is one.

        The workspace, not the browser, is what owns the interview now: a
        boss who logs in from a second machine continues where they left off
        instead of silently starting a parallel interview.
        """
        rows = self._all("""
            SELECT id FROM interview_sessions
            WHERE team_id=%s AND status='active'
            ORDER BY created_at DESC
            LIMIT 1
        """, (team_id,))
        if not rows:
            return None
        return self.get_session(rows[0]["id"], team_id)

    def latest_session(self, team_id: str) -> Optional[dict]:
        """This team's most recent interview, finished or not.

        `active_session` answers "is one open"; this answers "is there one at
        all", which is what reopening needs — the session worth continuing is
        precisely the completed one, and that is the row the other method
        filters out.
        """
        rows = self._all("""
            SELECT id FROM interview_sessions
            WHERE team_id=%s
            ORDER BY updated_at DESC
            LIMIT 1
        """, (team_id,))
        if not rows:
            return None
        return self.get_session(rows[0]["id"], team_id)

    def reopen(self, session_id: str, team_id: str, pending: dict) -> dict:
        """Put a completed session back in progress, keeping its profile.

        The profile column is deliberately left alone. It is the last version
        the boss agreed to, and the management area goes on reading it while
        the interview is open — adding to a workplace must not take the
        schedule away from it in the meantime. Completing again is what
        replaces it.
        """
        self._execute("""
            UPDATE interview_sessions
            SET status='active', pending=%s, updated_at=NOW()
            WHERE id=%s AND team_id=%s
        """, (Jsonb(pending), session_id, team_id))
        return self.get_session(session_id, team_id)

    def history(self, session_id: str) -> List[dict]:
        """Every turn, oldest first — the conversation `IntroInterview` wants.

        Returned whole rather than windowed: the model must not re-ask a
        question answered thirty turns ago, and the interview is bounded at
        roughly the topic count, so there is no context budget to protect.
        """
        return self._all("""
            SELECT role, content, payload, created_at
            FROM interview_turns
            WHERE session_id=%s
            ORDER BY created_at, id
        """, (session_id,))

    def append_turn(
        self, session_id: str, role: str, content: str, payload=None
    ) -> None:
        self._execute("""
            INSERT INTO interview_turns (id, session_id, role, content, payload)
            VALUES (%s,%s,%s,%s,%s)
        """, (new_id(), session_id, role, content,
              Jsonb(payload) if payload is not None else None))

    def save_pending(self, session_id: str, pending: Optional[dict]) -> None:
        """Record the question currently awaiting an answer."""
        self._execute("""
            UPDATE interview_sessions
            SET pending=%s, updated_at=NOW()
            WHERE id=%s
        """, (Jsonb(pending) if pending is not None else None, session_id))

    def complete(self, session_id: str, team_id: str, profile: dict) -> dict:
        """Store the confirmed profile and close the session.

        Guarded rather than a blind UPDATE: completing twice would overwrite
        a profile the boss already approved, and the second write is always
        the accident — a resubmitted confirmation, a double-clicked button.
        """
        with connect(self._store) as connection:
            row = connection.execute("""
                SELECT status FROM interview_sessions
                WHERE id=%s AND team_id=%s
                FOR UPDATE
            """, (session_id, team_id)).fetchone()
            if row and row["status"] == "complete":
                raise ConflictError("הראיון כבר הושלם")
            connection.execute("""
                UPDATE interview_sessions
                SET status='complete', profile=%s, pending=NULL,
                    updated_at=NOW()
                WHERE id=%s AND team_id=%s
            """, (Jsonb(profile), session_id, team_id))
            connection.commit()
        return self.get_session(session_id, team_id)
