"""
InvoiceUploadTool - Extract, validate, and store a PDF invoice.

Used by UploadAgent to process invoice files provided via temp path.
"""

import os
from backend.core.logging import get_logger
from pathlib import Path
from typing import Dict, Any, Optional

logger = get_logger(__name__)


class InvoiceUploadTool:
    """
    Tool that runs the full invoice ingestion pipeline:
    PDF → extract → validate → Neo4j → ChromaDB (non-fatal)

    Action format: "process|file_path=<path>"
    """

    def run(
        self,
        query: str = "",
        action: str = "",
        context: Optional[Dict[str, Any]] = None,
        user_id: str = "default_user",
    ) -> Dict[str, Any]:
        """
        Execute the invoice upload pipeline.

        Args:
            query: Original user query (for context)
            action: "process|file_path=<path>"
            context: Unused (upload is one-pass)

        Returns:
            Dict with status, invoice_id, invoice_number, amount, requires_review, summary
        """
        logger.debug("invoice_upload_tool_run", action=action[:100])

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

        return self._process_invoice(file_path, user_id)

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

    def _process_invoice(
        self, file_path: str, user_id: str = "default_user"
    ) -> Dict[str, Any]:
        """Run the full invoice ingestion pipeline."""
        path = Path(file_path)
        try:
            # --- Step 1: Extract ---
            from backend.ingestion.extractor import InvoiceExtractor
            extractor = InvoiceExtractor()
            invoice = extractor.extract_invoice_from_pdf(path)

            # --- Step 2: Validate ---
            from backend.ingestion.validator import InvoiceValidator
            validator = InvoiceValidator()
            anomalies = validator.validate_invoice(invoice)

            high_severity_count = sum(1 for a in anomalies if a.severity == "high")
            requires_review = high_severity_count > 0

            # --- Step 3: Insert into Neo4j ---
            from backend.services.graph_builder import GraphBuilder
            graph_builder = GraphBuilder()
            invoice_id = graph_builder.insert_invoice(invoice, user_id=user_id)

            # --- Step 4: Embed in ChromaDB (non-fatal) ---
            try:
                from backend.vector.client import ChromaDBClient
                chroma = ChromaDBClient()
                invoice_text = (
                    f"Invoice: {invoice.invoice_number}\n"
                    f"Date: {invoice.date}\n"
                    f"Contractor: {invoice.contractor_id}\n"
                    f"Amount: ${invoice.amount}\n"
                    "Line Items:\n"
                )
                for item in invoice.line_items:
                    invoice_text += f"- {item.cost_code}: {item.description} (${item.total})\n"

                chroma.add_document(
                    collection_name="invoices",
                    doc_id=invoice_id,
                    text=invoice_text,
                    metadata={
                        "invoice_number": invoice.invoice_number,
                        "date": str(invoice.date),
                        "amount": float(invoice.amount),
                        "contractor_id": invoice.contractor_id,
                    },
                )
                logger.debug("invoice_upload_tool_embedded", invoice_id=invoice_id)
            except Exception as embed_err:
                logger.warning("invoice_upload_tool_embed_failed", error=str(embed_err))

            summary = (
                f"Invoice {invoice.invoice_number} for ${invoice.amount:,.2f} "
                f"processed and stored (ID: {invoice_id})."
            )
            if requires_review:
                summary += f" {high_severity_count} high-severity anomalies detected — requires review."
            elif anomalies:
                summary += f" {len(anomalies)} minor anomaly(ies) noted."

            logger.debug(
                "invoice_upload_tool_success",
                invoice_id=invoice_id,
                invoice_number=invoice.invoice_number,
                requires_review=requires_review,
            )

            return {
                "status": "success",
                "invoice_id": invoice_id,
                "invoice_number": invoice.invoice_number,
                "amount": float(invoice.amount),
                "requires_review": requires_review,
                "anomaly_count": len(anomalies),
                "summary": summary,
            }

        except Exception as e:
            logger.error("invoice_upload_tool_failed", file_path=file_path, error=str(e))
            return {
                "status": "failed",
                "error": f"Failed to process invoice at {file_path}: {e}",
            }
        finally:
            # Clean up temp file
            try:
                if path.exists():
                    path.unlink()
                    logger.debug("invoice_upload_tool_temp_deleted", path=file_path)
            except Exception as cleanup_err:
                logger.warning("invoice_upload_tool_cleanup_failed", error=str(cleanup_err))
