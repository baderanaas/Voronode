"""Postgres-backed conversation and message store."""

import uuid
from datetime import datetime, timezone

from backend.core.db import get_pool


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize(row: dict) -> dict:
    """Convert datetime values to ISO strings for JSON serialisation."""
    return {k: v.isoformat() if isinstance(v, datetime) else v for k, v in row.items()}


class ConversationStore:
    """Manages conversations and messages in Postgres."""

    # ── Conversation CRUD ────────────────────────────────────────────────────

    def create_conversation(self, user_id: str, title: str = "New conversation") -> dict:
        conv_id = str(uuid.uuid4())
        now = _now()
        with get_pool().connection() as conn:
            conn.execute(
                "INSERT INTO conversations (id, user_id, title, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (conv_id, user_id, title, now, now),
            )
        return {
            "id": conv_id,
            "title": title,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

    def list_conversations(self, user_id: str) -> list[dict]:
        with get_pool().connection() as conn:
            rows = conn.execute(
                "SELECT id, title, created_at, updated_at "
                "FROM conversations WHERE user_id = %s ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        return [_serialize(r) for r in rows]

    def get_conversation(self, conv_id: str, user_id: str) -> dict | None:
        with get_pool().connection() as conn:
            row = conn.execute(
                "SELECT id, title, created_at, updated_at "
                "FROM conversations WHERE id = %s AND user_id = %s",
                (conv_id, user_id),
            ).fetchone()
        return _serialize(row) if row else None

    def update_title(self, conv_id: str, title: str, user_id: str):
        with get_pool().connection() as conn:
            conn.execute(
                "UPDATE conversations SET title = %s, updated_at = %s WHERE id = %s AND user_id = %s",
                (title, _now(), conv_id, user_id),
            )

    def delete_conversation(self, conv_id: str, user_id: str):
        with get_pool().connection() as conn:
            conn.execute(
                "DELETE FROM conversations WHERE id = %s AND user_id = %s",
                (conv_id, user_id),
            )

    # ── Message CRUD ─────────────────────────────────────────────────────────

    def add_message(self, conversation_id: str, role: str, content: str) -> dict:
        msg_id = str(uuid.uuid4())
        now = _now()
        with get_pool().connection() as conn:
            conn.execute(
                "INSERT INTO messages (id, conversation_id, role, content, created_at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (msg_id, conversation_id, role, content, now),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = %s WHERE id = %s",
                (now, conversation_id),
            )
        return {
            "id": msg_id,
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "created_at": now.isoformat(),
        }

    def get_recent_messages(self, conversation_id: str, limit: int) -> list[dict]:
        """Return the last *limit* messages as {role, content} dicts."""
        with get_pool().connection() as conn:
            rows = conn.execute(
                "SELECT role, content FROM ("
                "  SELECT role, content, created_at FROM messages "
                "  WHERE conversation_id = %s ORDER BY created_at DESC LIMIT %s"
                ") sub ORDER BY created_at ASC",
                (conversation_id, limit),
            ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in rows]

    def get_all_messages(self, conversation_id: str) -> list[dict]:
        """Return all messages as {role, content, created_at} dicts."""
        with get_pool().connection() as conn:
            rows = conn.execute(
                "SELECT role, content, created_at FROM messages "
                "WHERE conversation_id = %s ORDER BY created_at ASC",
                (conversation_id,),
            ).fetchall()
        return [_serialize(r) for r in rows]
