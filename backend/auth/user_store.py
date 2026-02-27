"""SQLite-backed user store."""

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.core.config import settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class UserStore:
    """Manages user accounts in the same SQLite database as conversations."""

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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id         TEXT PRIMARY KEY,
                    username   TEXT UNIQUE NOT NULL,
                    hashed_pw  TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def create_user(self, username: str, hashed_pw: str) -> dict:
        """Create a new user. Raises ValueError if username already taken."""
        user_id = str(uuid.uuid4())
        now = _now()
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO users (id, username, hashed_pw, created_at) VALUES (?, ?, ?, ?)",
                    (user_id, username, hashed_pw, now),
                )
        except sqlite3.IntegrityError:
            raise ValueError(f"Username '{username}' is already taken")
        return {"id": user_id, "username": username, "created_at": now}

    def get_by_username(self, username: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, username, hashed_pw, created_at FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        return dict(row) if row else None

    def get_by_id(self, user_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, username, created_at FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        return dict(row) if row else None
