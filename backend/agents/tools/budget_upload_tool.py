"""
BudgetUploadTool - Extract and store an Excel/CSV budget.

Used by UploadAgent to process budget files provided via temp path.
"""

import structlog
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

logger = structlog.get_logger()


class BudgetUploadTool:
    """
    Tool that runs the full budget ingestion pipeline:
    Excel/CSV → extract → validate → Neo4j

    Action format: "process|file_path=<path>"
    """

    def run(
        self,
        query: str = "",
        action: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute the budget upload pipeline.

        Args:
            query: Original user query (for context)
            action: "process|file_path=<path>"
            context: Unused (upload is one-pass)

        Returns:
            Dict with status, budget_id, project_name, total_allocated, summary
        """
        logger.info("budget_upload_tool_run", action=action[:100])

        parsed = self._parse_action(action)
        command = parsed["command"]
        params = parsed["params"]

        if command != "process":
            return {
                "status": "failed",
                "error": f"Unsupported action '{command}'. Use: process|file_path=<path>",
            }

        file_path = params.get("file_path", "").strip()
        if not file_path:
            return {
                "status": "failed",
                "error": "Missing file_path parameter. Use: process|file_path=<path>",
            }

        return self._process_budget(file_path)

    def _parse_action(self, action: str) -> Dict[str, Any]:
        """Parse 'command|key=value|...' into dict."""
        parts = action.split("|")
        command = parts[0].strip()
        params: Dict[str, str] = {}
        for part in parts[1:]:
            if "=" in part:
                key, value = part.split("=", 1)
                params[key.strip()] = value
        return {"command": command, "params": params}

    def _process_budget(self, file_path: str) -> Dict[str, Any]:
        """Run the full budget ingestion pipeline."""
        path = Path(file_path)
        try:
            # --- Step 1: Extract and validate ---
            from backend.ingestion.budget_extractor import BudgetExtractor
            extractor = BudgetExtractor()
            budget_data = extractor.extract_and_validate(path)

            # --- Step 2: Build models ---
            from backend.core.models import Budget, BudgetLine
            budget = Budget(
                id=(
                    budget_data["budget_id"]
                    if "budget_id" in budget_data
                    else budget_data["project_id"] + "-BUD-001"
                ),
                project_id=budget_data["project_id"],
                project_name=budget_data["project_name"],
                total_allocated=budget_data["metadata"]["total_allocated"],
                total_spent=budget_data["metadata"]["total_spent"],
                total_remaining=(
                    budget_data["metadata"]["total_allocated"]
                    - budget_data["metadata"]["total_spent"]
                ),
                line_count=budget_data["metadata"]["line_count"],
                extracted_at=datetime.fromisoformat(
                    budget_data["metadata"]["extracted_at"]
                ),
                validation_warnings=budget_data["metadata"]["validation_warnings"],
            )
            budget_lines = [
                BudgetLine(**line_data)
                for line_data in budget_data["budget_lines"]
            ]

            # --- Step 3: Insert into Neo4j ---
            from backend.services.graph_builder import GraphBuilder
            graph_builder = GraphBuilder()
            budget_id = graph_builder.insert_budget(budget, budget_lines)

            summary = (
                f"Budget for {budget.project_name} with total allocation of "
                f"${float(budget.total_allocated):,.2f} processed and stored (ID: {budget_id})."
            )
            if budget.validation_warnings:
                summary += f" {len(budget.validation_warnings)} validation warning(s) noted."

            logger.info(
                "budget_upload_tool_success",
                budget_id=budget_id,
                project_name=budget.project_name,
            )

            return {
                "status": "success",
                "budget_id": budget.id,
                "project_id": budget.project_id,
                "project_name": budget.project_name,
                "total_allocated": float(budget.total_allocated),
                "total_spent": float(budget.total_spent),
                "line_count": budget.line_count,
                "summary": summary,
            }

        except Exception as e:
            logger.error("budget_upload_tool_failed", file_path=file_path, error=str(e))
            return {
                "status": "failed",
                "error": f"Failed to process budget at {file_path}: {e}",
            }
        finally:
            # Clean up temp file
            try:
                if path.exists():
                    path.unlink()
                    logger.debug("budget_upload_tool_temp_deleted", path=file_path)
            except Exception as cleanup_err:
                logger.warning("budget_upload_tool_cleanup_failed", error=str(cleanup_err))
