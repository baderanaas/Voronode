"""
ContractUploadTool - Extract and store a PDF contract.

Used by UploadAgent to process contract files provided via temp path.
"""

import structlog
from pathlib import Path
from typing import Dict, Any, Optional

logger = structlog.get_logger()


class ContractUploadTool:
    """
    Tool that runs the full contract ingestion pipeline:
    PDF → extract → validate → Neo4j

    Action format: "process|file_path=<path>"
    """

    def run(
        self,
        query: str = "",
        action: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute the contract upload pipeline.

        Args:
            query: Original user query (for context)
            action: "process|file_path=<path>"
            context: Unused (upload is one-pass)

        Returns:
            Dict with status, contract_id, contractor_name, value, summary
        """
        logger.info("contract_upload_tool_run", action=action[:100])

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

        return self._process_contract(file_path)

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

    def _process_contract(self, file_path: str) -> Dict[str, Any]:
        """Run the full contract ingestion pipeline."""
        path = Path(file_path)
        try:
            # --- Step 1: Extract ---
            from backend.ingestion.contract_extractor import ContractExtractor
            extractor = ContractExtractor()
            raw_text = extractor._extract_text_from_pdf(path)
            contract_data = extractor.structure_contract(raw_text)

            # --- Step 2: Validate ---
            warnings = extractor.validate_extracted_contract(contract_data)
            contract = extractor._build_contract_model(contract_data, warnings)

            # --- Step 3: Insert into Neo4j ---
            from backend.services.graph_builder import GraphBuilder
            graph_builder = GraphBuilder()
            contract_id = graph_builder.insert_contract(contract)

            summary = (
                f"Contract {contract.id} with {contract.contractor_name} "
                f"for ${contract.value:,.2f} processed and stored."
            )
            if warnings:
                summary += f" {len(warnings)} extraction warning(s) noted."

            logger.info(
                "contract_upload_tool_success",
                contract_id=contract_id,
                contractor_name=contract.contractor_name,
            )

            return {
                "status": "success",
                "contract_id": contract.id,
                "contractor_name": contract.contractor_name,
                "project_name": contract.project_name,
                "value": float(contract.value),
                "warnings": warnings,
                "summary": summary,
            }

        except Exception as e:
            logger.error("contract_upload_tool_failed", file_path=file_path, error=str(e))
            return {
                "status": "failed",
                "error": f"Failed to process contract at {file_path}: {e}",
            }
        finally:
            # Clean up temp file
            try:
                if path.exists():
                    path.unlink()
                    logger.debug("contract_upload_tool_temp_deleted", path=file_path)
            except Exception as cleanup_err:
                logger.warning("contract_upload_tool_cleanup_failed", error=str(cleanup_err))
