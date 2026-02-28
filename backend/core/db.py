"""Shared Postgres connection pool and schema initialisation."""

from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

from backend.core.config import settings

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    if _pool is None:
        raise RuntimeError("DB pool not initialised — call open_pool() at startup")
    return _pool


def open_pool() -> None:
    global _pool
    _pool = ConnectionPool(
        settings.database_url,
        min_size=1,
        max_size=10,
        configure=_configure,
    )
    _pool.wait()  # block until min_size connections are ready


def _configure(conn) -> None:
    conn.row_factory = dict_row


def close_pool() -> None:
    global _pool
    if _pool:
        _pool.close()
        _pool = None


def init_db() -> None:
    """Create all application tables. Idempotent — safe to call on every startup."""
    with get_pool().connection() as conn:
        # ── Auth ────────────────────────────────────────────────────────────
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id         TEXT PRIMARY KEY,
                username   TEXT UNIQUE NOT NULL,
                hashed_pw  TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL
            )
            """
        )

        # ── Conversations ────────────────────────────────────────────────────
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id         TEXT PRIMARY KEY,
                user_id    TEXT NOT NULL,
                title      TEXT NOT NULL DEFAULT 'New conversation',
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id              TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL
                    REFERENCES conversations(id) ON DELETE CASCADE,
                role            TEXT NOT NULL,
                content         TEXT NOT NULL,
                created_at      TIMESTAMPTZ NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_messages_conv
                ON messages(conversation_id, created_at)
            """
        )

        # ── Workflow states ──────────────────────────────────────────────────
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_states (
                document_id TEXT PRIMARY KEY,
                user_id     TEXT,
                status      TEXT NOT NULL,
                paused      BOOLEAN NOT NULL DEFAULT FALSE,
                risk_level  TEXT,
                retry_count INTEGER DEFAULT 0,
                state_json  TEXT NOT NULL,
                created_at  TIMESTAMPTZ DEFAULT NOW(),
                updated_at  TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
        conn.execute(
            "ALTER TABLE workflow_states ADD COLUMN IF NOT EXISTS user_id TEXT"
        )
