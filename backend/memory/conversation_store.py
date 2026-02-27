"""SQLite-backed conversation and message store."""

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.core.config import settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConversationStore:
    """Manages conversations and messages in a local SQLite database."""

    def __init__(self):
        db_path = Path(settings.sqlite_db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = str(db_path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id         TEXT PRIMARY KEY,
                    user_id    TEXT NOT NULL,
                    title      TEXT NOT NULL DEFAULT 'New conversation',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id              TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL
                        REFERENCES conversations(id) ON DELETE CASCADE,
                    role            TEXT NOT NULL,
                    content         TEXT NOT NULL,
                    created_at      TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_messages_conv
                    ON messages(conversation_id, created_at);
            """
            )

    # ── Conversation CRUD ────────────────────────────────────────────────────

    def create_conversation(self, user_id: str, title: str = "New conversation") -> dict:
        conv_id = str(uuid.uuid4())
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO conversations (id, user_id, title, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (conv_id, user_id, title, now, now),
            )
        return {"id": conv_id, "title": title, "created_at": now, "updated_at": now}

    def list_conversations(self, user_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, title, created_at, updated_at "
                "FROM conversations WHERE user_id = ? ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_conversation(self, conv_id: str, user_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, title, created_at, updated_at "
                "FROM conversations WHERE id = ? AND user_id = ?",
                (conv_id, user_id),
            ).fetchone()
        return dict(row) if row else None

    def update_title(self, conv_id: str, title: str, user_id: str):
        with self._connect() as conn:
            conn.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                (title, _now(), conv_id, user_id),
            )

    def delete_conversation(self, conv_id: str, user_id: str):
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM conversations WHERE id = ? AND user_id = ?",
                (conv_id, user_id),
            )

    # ── Message CRUD ─────────────────────────────────────────────────────────

    def add_message(self, conversation_id: str, role: str, content: str) -> dict:
        msg_id = str(uuid.uuid4())
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO messages (id, conversation_id, role, content, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (msg_id, conversation_id, role, content, now),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conversation_id),
            )
        return {
            "id": msg_id,
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "created_at": now,
        }

    def get_recent_messages(self, conversation_id: str, limit: int) -> list[dict]:
        """Return the last *limit* messages as {role, content} dicts."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT role, content FROM ("
                "  SELECT role, content, created_at FROM messages "
                "  WHERE conversation_id = ? ORDER BY created_at DESC LIMIT ?"
                ") ORDER BY created_at ASC",
                (conversation_id, limit),
            ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in rows]

    def get_all_messages(self, conversation_id: str) -> list[dict]:
        """Return all messages as {role, content, created_at} dicts."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT role, content, created_at FROM messages "
                "WHERE conversation_id = ? ORDER BY created_at ASC",
                (conversation_id,),
            ).fetchall()
        return [dict(r) for r in rows]
