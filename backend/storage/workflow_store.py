"""SQLite storage for workflow states."""

import sqlite3
import json
from typing import Optional, List, Dict, Any
from pathlib import Path
from backend.core.logging import get_logger

from backend.core.config import settings

logger = get_logger(__name__)


class WorkflowStore:
    """SQLite-based persistence for workflow states."""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize workflow store.

        Args:
            db_path: Path to SQLite database (defaults to settings)
        """
        self.db_path = db_path or settings.workflow_state_db
        self._init_db()

    def _init_db(self):
        """Create workflow_states table if it doesn't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workflow_states (
                document_id TEXT PRIMARY KEY,
                user_id TEXT,
                status TEXT NOT NULL,
                paused BOOLEAN NOT NULL DEFAULT 0,
                risk_level TEXT,
                retry_count INTEGER DEFAULT 0,
                state_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Migrate existing DB: add user_id column if missing
        try:
            cursor.execute("ALTER TABLE workflow_states ADD COLUMN user_id TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists

        conn.commit()
        conn.close()

        logger.info("workflow_store_initialized", db_path=self.db_path)

    def save_workflow(self, document_id: str, state: Dict[str, Any], user_id: Optional[str] = None):
        """
        Save or update workflow state.

        Args:
            document_id: Unique document identifier
            state: Complete workflow state dictionary
            user_id: Owner of this workflow (JWT sub)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT OR REPLACE INTO workflow_states
            (document_id, user_id, status, paused, risk_level, retry_count, state_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                document_id,
                user_id,
                state.get("status", "processing"),
                state.get("paused", False),
                state.get("risk_level"),
                state.get("retry_count", 0),
                json.dumps(state),
            ),
        )

        conn.commit()
        conn.close()

        logger.info(
            "workflow_state_saved",
            document_id=document_id,
            status=state.get("status"),
        )

    def get_workflow(self, document_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve workflow state by document ID.

        Args:
            document_id: Unique document identifier

        Returns:
            Workflow state dictionary or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM workflow_states WHERE document_id = ?",
            (document_id,),
        )

        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                "document_id": row["document_id"],
                "user_id": row["user_id"],
                "status": row["status"],
                "paused": bool(row["paused"]),
                "risk_level": row["risk_level"],
                "retry_count": row["retry_count"],
                "state": json.loads(row["state_json"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }

        return None

    def get_all_quarantined(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all workflows with paused=True, optionally filtered by owner.

        Args:
            user_id: When provided, only return workflows owned by this user.

        Returns:
            List of quarantined workflow states
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if user_id:
            cursor.execute(
                """
                SELECT * FROM workflow_states
                WHERE paused = 1 AND user_id = ?
                ORDER BY updated_at DESC
                """,
                (user_id,),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM workflow_states
                WHERE paused = 1
                ORDER BY updated_at DESC
                """
            )

        rows = cursor.fetchall()
        conn.close()

        workflows = []
        for row in rows:
            workflows.append({
                "document_id": row["document_id"],
                "status": row["status"],
                "risk_level": row["risk_level"],
                "retry_count": row["retry_count"],
                "state": json.loads(row["state_json"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            })

        logger.info("quarantined_workflows_retrieved", count=len(workflows))

        return workflows

    def get_all_by_status(self, status: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all workflows with a specific status, optionally filtered by owner.

        Args:
            status: Workflow status (processing, completed, failed, quarantined)
            user_id: When provided, only return workflows owned by this user.

        Returns:
            List of workflow states
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if user_id:
            cursor.execute(
                """
                SELECT * FROM workflow_states
                WHERE status = ? AND user_id = ?
                ORDER BY updated_at DESC
                """,
                (status, user_id),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM workflow_states
                WHERE status = ?
                ORDER BY updated_at DESC
                """,
                (status,),
            )

        rows = cursor.fetchall()
        conn.close()

        workflows = []
        for row in rows:
            workflows.append({
                "document_id": row["document_id"],
                "user_id": row["user_id"],
                "status": row["status"],
                "paused": bool(row["paused"]),
                "risk_level": row["risk_level"],
                "retry_count": row["retry_count"],
                "state": json.loads(row["state_json"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            })

        return workflows

    def get_all_workflows(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all workflows regardless of status, optionally filtered by owner.

        Args:
            user_id: When provided, only return workflows owned by this user.

        Returns:
            List of all workflow states
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if user_id:
            cursor.execute(
                """
                SELECT * FROM workflow_states
                WHERE user_id = ?
                ORDER BY updated_at DESC
                """,
                (user_id,),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM workflow_states
                ORDER BY updated_at DESC
                """
            )

        rows = cursor.fetchall()
        conn.close()

        workflows = []
        for row in rows:
            workflows.append({
                "document_id": row["document_id"],
                "user_id": row["user_id"],
                "status": row["status"],
                "paused": bool(row["paused"]),
                "risk_level": row["risk_level"],
                "retry_count": row["retry_count"],
                "state": json.loads(row["state_json"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            })

        return workflows

    def delete_workflow(self, document_id: str):
        """
        Delete a workflow state.

        Args:
            document_id: Unique document identifier
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "DELETE FROM workflow_states WHERE document_id = ?",
            (document_id,),
        )

        conn.commit()
        conn.close()

        logger.info("workflow_state_deleted", document_id=document_id)
