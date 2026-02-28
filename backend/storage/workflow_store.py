"""Postgres storage for workflow states."""

import json
from typing import Optional, List, Dict, Any

from backend.core.logging import get_logger
from backend.core.db import get_pool

logger = get_logger(__name__)


class WorkflowStore:
    """Postgres-based persistence for workflow states."""

    def __init__(self, db_path: Optional[str] = None):
        # db_path ignored — kept for backwards compatibility
        pass

    def save_workflow(
        self,
        document_id: str,
        state: Dict[str, Any],
        user_id: Optional[str] = None,
    ):
        """Save or update workflow state."""
        with get_pool().connection() as conn:
            conn.execute(
                """
                INSERT INTO workflow_states
                    (document_id, user_id, status, paused, risk_level, retry_count, state_json, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (document_id) DO UPDATE SET
                    user_id     = EXCLUDED.user_id,
                    status      = EXCLUDED.status,
                    paused      = EXCLUDED.paused,
                    risk_level  = EXCLUDED.risk_level,
                    retry_count = EXCLUDED.retry_count,
                    state_json  = EXCLUDED.state_json,
                    updated_at  = NOW()
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
        logger.info("workflow_state_saved", document_id=document_id, status=state.get("status"))

    def get_workflow(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve workflow state by document ID."""
        with get_pool().connection() as conn:
            row = conn.execute(
                "SELECT * FROM workflow_states WHERE document_id = %s",
                (document_id,),
            ).fetchone()
        if row:
            return {
                "document_id": row["document_id"],
                "user_id": row["user_id"],
                "status": row["status"],
                "paused": row["paused"],
                "risk_level": row["risk_level"],
                "retry_count": row["retry_count"],
                "state": json.loads(row["state_json"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        return None

    def get_all_quarantined(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all workflows with paused=TRUE, optionally filtered by owner."""
        with get_pool().connection() as conn:
            if user_id:
                rows = conn.execute(
                    "SELECT * FROM workflow_states WHERE paused = TRUE AND user_id = %s "
                    "ORDER BY updated_at DESC",
                    (user_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM workflow_states WHERE paused = TRUE ORDER BY updated_at DESC"
                ).fetchall()
        workflows = [
            {
                "document_id": row["document_id"],
                "status": row["status"],
                "risk_level": row["risk_level"],
                "retry_count": row["retry_count"],
                "state": json.loads(row["state_json"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]
        logger.info("quarantined_workflows_retrieved", count=len(workflows))
        return workflows

    def get_all_by_status(
        self, status: str, user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all workflows with a specific status, optionally filtered by owner."""
        with get_pool().connection() as conn:
            if user_id:
                rows = conn.execute(
                    "SELECT * FROM workflow_states WHERE status = %s AND user_id = %s "
                    "ORDER BY updated_at DESC",
                    (status, user_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM workflow_states WHERE status = %s ORDER BY updated_at DESC",
                    (status,),
                ).fetchall()
        return [
            {
                "document_id": row["document_id"],
                "user_id": row["user_id"],
                "status": row["status"],
                "paused": row["paused"],
                "risk_level": row["risk_level"],
                "retry_count": row["retry_count"],
                "state": json.loads(row["state_json"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def get_all_workflows(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all workflows regardless of status, optionally filtered by owner."""
        with get_pool().connection() as conn:
            if user_id:
                rows = conn.execute(
                    "SELECT * FROM workflow_states WHERE user_id = %s ORDER BY updated_at DESC",
                    (user_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM workflow_states ORDER BY updated_at DESC"
                ).fetchall()
        return [
            {
                "document_id": row["document_id"],
                "user_id": row["user_id"],
                "status": row["status"],
                "paused": row["paused"],
                "risk_level": row["risk_level"],
                "retry_count": row["retry_count"],
                "state": json.loads(row["state_json"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def delete_workflow(self, document_id: str):
        """Delete a workflow state."""
        with get_pool().connection() as conn:
            conn.execute(
                "DELETE FROM workflow_states WHERE document_id = %s",
                (document_id,),
            )
        logger.info("workflow_state_deleted", document_id=document_id)
