"""Private manager conversations and atomic approval of stored plans."""

from contextlib import contextmanager

from psycopg.errors import SerializationFailure
from psycopg.types.json import Jsonb

from app.common.errors.errors import ConflictError, NotFoundError
from app.dal.database.postgres import atomic, connect
from app.dal.repository.base import RepositoryBase, new_id

CHAT_DDL = """
CREATE TABLE IF NOT EXISTS manager_chats (
    id TEXT PRIMARY KEY,
    team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    manager_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT 'שיחה חדשה',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
COMMIT;
CREATE INDEX IF NOT EXISTS manager_chats_owner_idx
    ON manager_chats(team_id, manager_id, updated_at DESC);
COMMIT;
CREATE TABLE IF NOT EXISTS manager_chat_messages (
    id TEXT PRIMARY KEY,
    chat_id TEXT NOT NULL REFERENCES manager_chats(id) ON DELETE CASCADE,
    sequence BIGSERIAL NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user','assistant')),
    content TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'complete',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    request_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(chat_id, request_id)
);
COMMIT;
CREATE INDEX IF NOT EXISTS manager_chat_messages_order_idx
    ON manager_chat_messages(chat_id, sequence);
COMMIT;
"""


class ChatRepository(RepositoryBase):
    def list_chats(self, team_id, manager_id):
        return self._all("""
            SELECT id, title, created_at, updated_at FROM manager_chats
            WHERE team_id=%s AND manager_id=%s ORDER BY updated_at DESC LIMIT 100
        """, (team_id, manager_id))

    def create_chat(self, team_id, manager_id):
        chat_id = new_id()
        self._execute("""
            INSERT INTO manager_chats(id,team_id,manager_id) VALUES (%s,%s,%s)
        """, (chat_id, team_id, manager_id))
        return self.get_chat(team_id, manager_id, chat_id)

    def get_chat(self, team_id, manager_id, chat_id):
        chat = self._one("""
            SELECT id,title,created_at,updated_at FROM manager_chats
            WHERE id=%s AND team_id=%s AND manager_id=%s
        """, (chat_id, team_id, manager_id))
        chat["messages"] = self._all("""
            SELECT id,role,content,status,payload,created_at FROM manager_chat_messages
            WHERE chat_id=%s ORDER BY sequence
        """, (chat_id,))
        return chat

    def delete_chat(self, team_id, manager_id, chat_id):
        self.get_chat(team_id, manager_id, chat_id)
        self._execute("""
            DELETE FROM manager_chats WHERE id=%s AND team_id=%s AND manager_id=%s
        """, (chat_id, team_id, manager_id))

    def start_chat_turn(self, team_id, manager_id, chat_id, content, request_id, payload):
        """One in-flight turn per conversation; retries do not duplicate it."""
        with connect(self._store) as connection:
            chat = connection.execute("""
                SELECT * FROM manager_chats
                WHERE id=%s AND team_id=%s AND manager_id=%s FOR UPDATE
            """, (chat_id, team_id, manager_id)).fetchone()
            if chat is None:
                raise NotFoundError("השיחה לא נמצאה")
            existing = connection.execute("""
                SELECT id FROM manager_chat_messages WHERE chat_id=%s AND request_id=%s
            """, (chat_id, request_id)).fetchone()
            if existing:
                return None
            working = connection.execute("""
                SELECT id FROM manager_chat_messages WHERE chat_id=%s AND status='working'
            """, (chat_id,)).fetchone()
            if working:
                raise ConflictError("הסוכן עדיין עובד על ההודעה הקודמת")
            user_id, assistant_id = new_id(), new_id()
            connection.execute("""
                UPDATE manager_chat_messages SET status='superseded'
                WHERE chat_id=%s AND status='pending'
            """, (chat_id,))
            connection.execute("""
                INSERT INTO manager_chat_messages(id,chat_id,role,content,request_id)
                VALUES (%s,%s,'user',%s,%s)
            """, (user_id, chat_id, content, request_id))
            connection.execute("""
                INSERT INTO manager_chat_messages(id,chat_id,role,status,payload)
                VALUES (%s,%s,'assistant','working',%s)
            """, (assistant_id, chat_id, Jsonb(payload)))
            connection.execute("""
                UPDATE manager_chats SET updated_at=NOW(),
                    title=CASE WHEN title='שיחה חדשה' THEN %s ELSE title END
                WHERE id=%s
            """, (content[:70], chat_id))
            connection.commit()
        return assistant_id

    def finish_chat_turn(self, chat_id, message_id, content, status, payload):
        self._execute("""
            UPDATE manager_chat_messages SET content=%s,status=%s,payload=%s
            WHERE id=%s AND chat_id=%s AND status='working'
        """, (content, status, Jsonb(payload), message_id, chat_id))

    def stop_chat_turn(self, team_id, manager_id, chat_id):
        self.get_chat(team_id, manager_id, chat_id)
        self._execute("""
            UPDATE manager_chat_messages SET status='cancelled',
                content='הבקשה נעצרה. לא בוצע שינוי בסידור'
            WHERE chat_id=%s AND status='working'
        """, (chat_id,))

    @contextmanager
    def chat_approval(self, team_id, manager_id, chat_id, message_id):
        """Approval, all domain writes, and the receipt commit together."""
        try:
            with atomic(self._store) as connection:
                chat = connection.execute("""
                    SELECT id FROM manager_chats
                    WHERE id=%s AND team_id=%s AND manager_id=%s FOR UPDATE
                """, (chat_id, team_id, manager_id)).fetchone()
                if chat is None:
                    raise NotFoundError("השיחה לא נמצאה")
                row = connection.execute("""
                    SELECT * FROM manager_chat_messages WHERE id=%s AND chat_id=%s
                    FOR UPDATE
                """, (message_id, chat_id)).fetchone()
                if row is None:
                    raise NotFoundError("ההצעה לא נמצאה")
                if row["status"] not in ("pending", "applied"):
                    raise ConflictError("ההצעה כבר הוחלפה. יש להשתמש בהצעה האחרונה")
                yield dict(row)
        except SerializationFailure as exc:
            raise ConflictError("הסידור השתנה במקביל. יש לרענן ולבקש הצעה מעודכנת") from exc

    def mark_chat_applied(self, chat_id, message_id, payload):
        self._execute("""
            UPDATE manager_chat_messages SET status='applied',payload=%s
            WHERE id=%s AND chat_id=%s
        """, (Jsonb(payload), message_id, chat_id))

    def dismiss_chat_plan(self, team_id, manager_id, chat_id, message_id):
        with self.chat_approval(team_id, manager_id, chat_id, message_id) as row:
            if row["status"] == "pending":
                self._execute("""
                    UPDATE manager_chat_messages SET status='dismissed'
                    WHERE id=%s AND chat_id=%s
                """, (message_id, chat_id))
