"""
ComplianceCheckTool - Contract compliance validation.

Domain tool for checking invoice compliance against contract terms.
Validates retention, unit prices, cost codes, and billing caps.
"""

import structlog
from typing import Dict, Any, Optional
from datetime import datetime

from backend.ingestion.compliance_auditor import ContractComplianceAuditor
from backend.graph.client import Neo4jClient
from backend.services.graph_builder import GraphBuilder
from backend.core.models import Invoice, LineItem

logger = structlog.get_logger()


class ComplianceCheckTool:
    """
    Tool for checking contract compliance.

    Capabilities:
    - Validate invoice against contract terms
    - Check retention calculations
    - Verify unit prices against schedule
    - Validate cost code scope
    - Check billing caps
    """

    def __init__(self):
        """Initialize with Neo4j client, GraphBuilder, and ContractComplianceAuditor."""
        self.neo4j_client = Neo4jClient()
        self.graph_builder = GraphBuilder()
        self.auditor = ContractComplianceAuditor(self.neo4j_client)

    def run(
        self,
        query: str = "",
        action: str = "",
        context: Optional[Dict[str, Any]] = None,
        invoice_id: Optional[str] = None,
        contract_id: Optional[str] = None,
        user_id: str = "default_user",
    ) -> Dict[str, Any]:
        """
        Check compliance.

        Args:
            query: User's original query
            action: Compliance check to perform
            context: Previous results
            invoice_id: Specific invoice to check
            contract_id: Specific contract to check against

        Returns:
            {
                "invoice_id": "...",
                "contract_id": "...",
                "violations": [...],
                "compliant": true/false,
                "status": "success" | "failed"
            }
        """
        logger.info("compliance_check_executing", action=action[:100])

        # Extract invoice and contract IDs
        if not invoice_id:
            invoice_id = self._extract_id(action, context, "invoice")

        if not contract_id:
            contract_id = self._extract_id(action, context, "contract")

        if not invoice_id:
            return {
                "error": "Could not identify invoice for compliance check",
                "status": "failed",
            }

        try:
            # Fetch invoice — enforce user_id so a user can't check another user's invoice
            cypher = """
            MATCH (i:Invoice {id: $invoice_id})
            WHERE i.user_id = $user_id
            OPTIONAL MATCH (c:Contractor)-[:ISSUED]->(i)
            OPTIONAL MATCH (i)-[:BILLED_AGAINST]->(con:Contract)
            OPTIONAL MATCH (i)-[:CONTAINS_ITEM]->(li:LineItem)
            RETURN i,
                   c.contractor_id as contractor_id,
                   con.contract_id as contract_id,
                   collect({
                       id: li.id,
                       description: li.description,
                       cost_code: li.cost_code,
                       quantity: li.quantity,
                       unit_price: li.unit_price,
                       total: li.total
                   }) as line_items
            """

            result = self.neo4j_client.run_query(cypher, {"invoice_id": invoice_id, "user_id": user_id})

            if not result or not result[0]:
                return {
                    "error": f"Invoice {invoice_id} not found",
                    "invoice_id": invoice_id,
                    "status": "failed",
                }

            record = result[0]
            invoice_node = record["i"]

            # Override contract_id if provided
            fetched_contract_id = contract_id or record.get("contract_id")

            # Convert to Invoice Pydantic model
            line_items = [
                LineItem(**item) for item in record.get("line_items", []) if item.get("id")
            ]

            invoice = Invoice(
                id=invoice_node["id"],
                invoice_number=invoice_node["invoice_number"],
                date=str(invoice_node["date"]),
                due_date=str(invoice_node["due_date"]) if invoice_node.get("due_date") else None,
                contractor_id=record.get("contractor_id") or "UNKNOWN",
                contract_id=fetched_contract_id,
                amount=invoice_node["amount"],
                status=invoice_node.get("status", "pending"),
                line_items=line_items,
            )

            # Run compliance audit
            anomalies = self.auditor.audit_invoice(invoice)

            is_compliant = len(anomalies) == 0

            # Convert anomalies to dicts
            violations = [
                {
                    "type": a.type,
                    "severity": a.severity,
                    "message": a.message,
                    "contract_id": a.contract_id,
                    "invoice_id": a.invoice_id,
                    "metadata": a.metadata,
                }
                for a in anomalies
            ]

            logger.info(
                "compliance_check_complete",
                invoice_id=invoice_id,
                violations_count=len(violations),
                compliant=is_compliant,
            )

            return {
                "invoice_id": invoice_id,
                "contract_id": invoice.contract_id,
                "violations": violations,
                "violation_count": len(violations),
                "compliant": is_compliant,
                "status": "success",
            }

        except Exception as e:
            logger.error("compliance_check_failed", error=str(e), invoice_id=invoice_id)
            return {
                "error": str(e),
                "invoice_id": invoice_id,
                "status": "failed",
            }

    def _extract_id(
        self,
        action: str,
        context: Optional[Dict],
        id_type: str,
    ) -> Optional[str]:
        """
        Extract invoice or contract ID from action or context.

        Args:
            action: Action string
            context: Previous results
            id_type: Type of ID to extract ("invoice" or "contract")

        Returns:
            ID if found, None otherwise
        """
        import re

        # Look for ID patterns
        if id_type == "invoice":
            id_pattern = r'INV-\d{4}-\d{4}'
        elif id_type == "contract":
            id_pattern = r'CONTRACT-\d{3}'
        else:
            id_pattern = r'[A-Z]+-\d{3,4}'

        id_match = re.search(id_pattern, action)
        if id_match:
            return id_match.group(0)

        # Try to extract from context
        if context and context.get("previous_results"):
            for result in context["previous_results"]:
                if result.get("status") == "success":
                    if "results" in result:
                        for record in result["results"]:
                            if f"{id_type}_id" in record:
                                return record[f"{id_type}_id"]
                            if "id" in record and id_type in str(record.get("id", "")).lower():
                                return record["id"]

        return None
