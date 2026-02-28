"""Postgres-backed user store."""

import uuid
from datetime import datetime, timezone

import psycopg.errors

from backend.core.db import get_pool


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize(row: dict) -> dict:
    """Convert datetime values to ISO strings."""
    return {k: v.isoformat() if isinstance(v, datetime) else v for k, v in row.items()}


class UserStore:
    """Manages user accounts in Postgres."""

    def create_user(self, username: str, hashed_pw: str) -> dict:
        """Create a new user. Raises ValueError if username already taken."""
        user_id = str(uuid.uuid4())
        now = _now()
        try:
            with get_pool().connection() as conn:
                conn.execute(
                    "INSERT INTO users (id, username, hashed_pw, created_at) VALUES (%s, %s, %s, %s)",
                    (user_id, username, hashed_pw, now),
                )
        except psycopg.errors.UniqueViolation:
            raise ValueError(f"Username '{username}' is already taken")
        return {"id": user_id, "username": username, "created_at": now.isoformat()}

    def get_by_username(self, username: str) -> dict | None:
        with get_pool().connection() as conn:
            row = conn.execute(
                "SELECT id, username, hashed_pw, created_at FROM users WHERE username = %s",
                (username,),
            ).fetchone()
        return _serialize(row) if row else None

    def get_by_id(self, user_id: str) -> dict | None:
        with get_pool().connection() as conn:
            row = conn.execute(
                "SELECT id, username, created_at FROM users WHERE id = %s",
                (user_id,),
            ).fetchone()
        return _serialize(row) if row else None
