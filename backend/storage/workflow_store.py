"""SQLite storage for workflow states."""

import sqlite3
import json
from typing import Optional, List, Dict, Any
from pathlib import Path
import structlog

from backend.core.config import settings

logger = structlog.get_logger()


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
                status TEXT NOT NULL,
                paused BOOLEAN NOT NULL DEFAULT 0,
                risk_level TEXT,
                retry_count INTEGER DEFAULT 0,
                state_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()

        logger.info("workflow_store_initialized", db_path=self.db_path)

    def save_workflow(self, document_id: str, state: Dict[str, Any]):
        """
        Save or update workflow state.

        Args:
            document_id: Unique document identifier
            state: Complete workflow state dictionary
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT OR REPLACE INTO workflow_states
            (document_id, status, paused, risk_level, retry_count, state_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                document_id,
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
                "status": row["status"],
                "paused": bool(row["paused"]),
                "risk_level": row["risk_level"],
                "retry_count": row["retry_count"],
                "state": json.loads(row["state_json"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }

        return None

    def get_all_quarantined(self) -> List[Dict[str, Any]]:
        """
        Get all workflows with paused=True.

        Returns:
            List of quarantined workflow states
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

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

    def get_all_by_status(self, status: str) -> List[Dict[str, Any]]:
        """
        Get all workflows with a specific status.

        Args:
            status: Workflow status (processing, completed, failed, quarantined)

        Returns:
            List of workflow states
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

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
