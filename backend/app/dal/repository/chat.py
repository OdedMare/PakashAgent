"""Private manager conversations and atomic approval of stored plans."""

from psycopg.types.json import Jsonb

from app.common.errors import ConflictError, NotFoundError
from app.dal.database import atomic, connect
from app.dal.repository.base import RepositoryBase, new_id
from app.dal.repository.jobs import enqueue

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
    plan_id TEXT REFERENCES change_plans(id) ON DELETE SET NULL,
    request_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(chat_id, request_id)
);
COMMIT;
ALTER TABLE manager_chat_messages ADD COLUMN IF NOT EXISTS plan_id TEXT
    REFERENCES change_plans(id) ON DELETE SET NULL;
COMMIT;
CREATE INDEX IF NOT EXISTS manager_chat_messages_order_idx
    ON manager_chat_messages(chat_id, sequence);
COMMIT;
CREATE INDEX IF NOT EXISTS manager_chat_messages_plan_idx
    ON manager_chat_messages(plan_id) WHERE plan_id IS NOT NULL;
COMMIT;
"""


def _with_plan(row):
    """Keep the chat API stable while the plan lives in its own table."""
    row = dict(row)
    plan = row.pop("stored_plan", None)
    payload = dict(row.get("payload") or {})
    if plan is not None:
        payload["plan"] = plan
    if row.get("plan_id"):
        payload["plan_id"] = row["plan_id"]
    row["payload"] = payload
    return row


def _take_back(connection, chat_id, message_id):
    """Remove a manager message and everything after it. Refused once any of
    it was applied: an approved plan and its receipt are the conversation's
    record of a real change and stay where they are."""
    anchor = connection.execute("""
        SELECT sequence, role FROM manager_chat_messages WHERE id=%s AND chat_id=%s
    """, (message_id, chat_id)).fetchone()
    if anchor is None or anchor["role"] != "user":
        raise NotFoundError("ההודעה לא נמצאה")
    applied = connection.execute("""
        SELECT 1 FROM manager_chat_messages
        WHERE chat_id=%s AND sequence >= %s AND (status='applied' OR payload ? 'receipt')
        LIMIT 1
    """, (chat_id, anchor["sequence"])).fetchone()
    if applied:
        raise ConflictError("אחרי ההודעה הזו כבר אושר שינוי, ולכן אי אפשר לערוך אותה. שלחו בקשה חדשה")
    connection.execute("""
        UPDATE change_plans SET status='superseded',updated_at=NOW()
        WHERE status='pending' AND id IN (
            SELECT plan_id FROM manager_chat_messages
            WHERE chat_id=%s AND sequence >= %s AND plan_id IS NOT NULL
        )
    """, (chat_id, anchor["sequence"]))
    connection.execute("""
        DELETE FROM manager_chat_messages WHERE chat_id=%s AND sequence >= %s
    """, (chat_id, anchor["sequence"]))


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

    def get_chat(self, team_id, manager_id, chat_id, from_message=""):
        """The conversation; `from_message` keeps only that message and later.

        A poll during a running reply asks for the tail alone: nothing before
        the working message can change until it finishes, and re-sending every
        earlier plan every two seconds grows with the conversation. An id that
        is not in this chat returns every message.
        """
        chat = self._one("""
            SELECT id,title,created_at,updated_at FROM manager_chats
            WHERE id=%s AND team_id=%s AND manager_id=%s
        """, (chat_id, team_id, manager_id))
        rows = self._all("""
            SELECT m.id,m.role,m.content,m.status,m.payload,m.plan_id,
                   m.created_at,m.request_id,p.body AS stored_plan
            FROM manager_chat_messages m
            LEFT JOIN change_plans p ON p.id=m.plan_id
            WHERE m.chat_id=%s AND m.sequence >= COALESCE((
                SELECT sequence FROM manager_chat_messages WHERE id=%s AND chat_id=%s
            ), 0)
            ORDER BY m.sequence
        """, (chat_id, from_message, chat_id))
        chat["messages"] = [_with_plan(row) for row in rows]
        return chat

    def delete_chat(self, team_id, manager_id, chat_id):
        with atomic(self._store) as connection:
            chat = connection.execute("""
                SELECT id FROM manager_chats
                WHERE id=%s AND team_id=%s AND manager_id=%s FOR UPDATE
            """, (chat_id, team_id, manager_id)).fetchone()
            if chat is None:
                raise NotFoundError("השיחה לא נמצאה")
            connection.execute("""
                UPDATE change_plans SET status='dismissed',updated_at=NOW()
                WHERE status='pending' AND id IN (
                    SELECT plan_id FROM manager_chat_messages
                    WHERE chat_id=%s AND plan_id IS NOT NULL
                )
            """, (chat_id,))
            connection.execute(
                "DELETE FROM manager_chats WHERE id=%s", (chat_id,),
            )

    def start_chat_turn(self, team_id, manager_id, chat_id, content, request_id, payload,
                        replace_from=None):
        """One in-flight turn per conversation; retries do not duplicate it.

        `replace_from` names a manager message to take back: it and every
        later message are removed in the same transaction, so an edited
        request or a second answer replaces the old exchange instead of
        following it."""
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
            if replace_from:
                _take_back(connection, chat_id, replace_from)
            user_id, assistant_id = new_id(), new_id()
            connection.execute("""
                UPDATE change_plans SET status='superseded',updated_at=NOW()
                WHERE status='pending' AND id IN (
                    SELECT plan_id FROM manager_chat_messages
                    WHERE chat_id=%s AND status='pending' AND plan_id IS NOT NULL
                )
            """, (chat_id,))
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
            enqueue(connection, team_id, "chat:" + assistant_id, "manager_chat", {
                "manager_id": manager_id, "chat_id": chat_id, "message_id": assistant_id,
            })
            connection.commit()
        return assistant_id

    def finish_chat_turn(self, chat_id, message_id, content, status, payload):
        plan = payload.get("plan")
        if plan is not None:
            stored_payload = dict(payload)
            stored_payload.pop("plan", None)
            with atomic(self._store) as connection:
                owner = connection.execute("""
                    SELECT c.team_id,m.status FROM manager_chat_messages m
                    JOIN manager_chats c ON c.id=m.chat_id
                    WHERE m.id=%s AND m.chat_id=%s FOR UPDATE
                """, (message_id, chat_id)).fetchone()
                if owner is None or owner["status"] != "working":
                    return
                change_plan = self.create_change_plan(
                    owner["team_id"], plan, "chat", message_id,
                )
                stored_payload["plan_id"] = change_plan["id"]
                connection.execute("""
                    UPDATE manager_chat_messages
                    SET content=%s,status=%s,payload=%s,plan_id=%s
                    WHERE id=%s AND chat_id=%s AND status='working'
                """, (content, status, Jsonb(stored_payload), change_plan["id"],
                      message_id, chat_id))
            return
        self._execute("""
            UPDATE manager_chat_messages SET content=%s,status=%s,payload=%s
            WHERE id=%s AND chat_id=%s AND status='working'
        """, (content, status, Jsonb(payload), message_id, chat_id))

    def ensure_chat_change_plan(
        self, team_id, manager_id, chat_id, message_id,
    ) -> str:
        """Return the message's plan id, importing a pre-migration plan once."""
        with atomic(self._store) as connection:
            row = connection.execute("""
                SELECT m.plan_id,m.payload FROM manager_chat_messages m
                JOIN manager_chats c ON c.id=m.chat_id
                WHERE m.id=%s AND m.chat_id=%s
                  AND c.team_id=%s AND c.manager_id=%s FOR UPDATE
            """, (message_id, chat_id, team_id, manager_id)).fetchone()
            if row is None:
                raise NotFoundError("ההצעה לא נמצאה")
            if row["plan_id"]:
                return row["plan_id"]
            payload = dict(row["payload"] or {})
            plan = payload.pop("plan", None)
            if not plan:
                raise ConflictError("אין תוכנית שממתינה לאישור")
            stored = self.create_change_plan(team_id, plan, "chat", message_id)
            payload["plan_id"] = stored["id"]
            connection.execute("""
                UPDATE manager_chat_messages SET payload=%s,plan_id=%s
                WHERE id=%s AND chat_id=%s
            """, (Jsonb(payload), stored["id"], message_id, chat_id))
            return stored["id"]

    def lock_chat_plan_source(
        self, team_id, manager_id, chat_id, message_id, plan_id,
    ) -> dict:
        """Verify and lock the chat record that owns an approved plan."""
        row = self._one("""
            SELECT m.* FROM manager_chat_messages m
            JOIN manager_chats c ON c.id=m.chat_id
            WHERE m.id=%s AND m.chat_id=%s AND m.plan_id=%s
              AND c.team_id=%s AND c.manager_id=%s
            FOR UPDATE
        """, (message_id, chat_id, plan_id, team_id, manager_id))
        if row["status"] not in ("pending", "applied"):
            raise ConflictError("ההצעה כבר הוחלפה. יש להשתמש בהצעה האחרונה")
        return row

    def chat_turn_progress(self, chat_id, message_id, payload):
        """The checks a running turn has made so far; a stopped turn stays stopped."""
        self._execute("""
            UPDATE manager_chat_messages SET payload=%s
            WHERE id=%s AND chat_id=%s AND status='working'
        """, (Jsonb(payload), message_id, chat_id))

    def chat_turn_draft(self, chat_id, message_id, draft):
        """The reply so far, while the model is still writing it."""
        self._execute("""
            UPDATE manager_chat_messages
            SET payload=jsonb_set(payload, '{draft}', to_jsonb(%s::text), true)
            WHERE id=%s AND chat_id=%s AND status='working'
        """, (draft, message_id, chat_id))

    def chat_activity(self, chat_id, message_id, activity):
        self._execute("""
            UPDATE manager_chat_messages
            SET payload=jsonb_set(payload, '{activity}', to_jsonb(%s::text), true)
            WHERE id=%s AND chat_id=%s AND status='working'
        """, (activity, message_id, chat_id))

    def stop_chat_turn(self, team_id, manager_id, chat_id):
        self.get_chat(team_id, manager_id, chat_id)
        self._execute("""
            UPDATE manager_chat_messages SET status='cancelled',
                content='הבקשה נעצרה. לא בוצע שינוי בסידור'
            WHERE chat_id=%s AND status='working'
        """, (chat_id,))

    def mark_chat_applied(self, chat_id, message_id, payload):
        self._execute("""
            UPDATE manager_chat_messages SET status='applied',payload=%s
            WHERE id=%s AND chat_id=%s
        """, (Jsonb(payload), message_id, chat_id))

    def record_chat_confirmation(self, chat_id, content, request_id, receipt):
        """Called inside chat_approval: the instruction and receipt commit together."""
        self._execute("""
            INSERT INTO manager_chat_messages(id,chat_id,role,content,request_id)
            VALUES (%s,%s,'user',%s,%s)
        """, (new_id(), chat_id, content, request_id))
        self._execute("""
            INSERT INTO manager_chat_messages(id,chat_id,role,content,status,payload)
            VALUES (%s,%s,'assistant',%s,'complete',%s)
        """, (new_id(), chat_id, receipt["message"], Jsonb({"receipt": receipt})))
        self._execute("UPDATE manager_chats SET updated_at=NOW() WHERE id=%s", (chat_id,))

    def dismiss_chat_plan(self, team_id, manager_id, chat_id, message_id):
        plan_id = self.ensure_chat_change_plan(team_id, manager_id, chat_id, message_id)
        with atomic(self._store):
            row = self.lock_chat_plan_source(
                team_id, manager_id, chat_id, message_id, plan_id,
            )
            if row["status"] == "pending":
                self.set_change_plan_status(plan_id, team_id, "dismissed")
                self._execute("""
                    UPDATE manager_chat_messages SET status='dismissed'
                    WHERE id=%s AND chat_id=%s
                """, (message_id, chat_id))
