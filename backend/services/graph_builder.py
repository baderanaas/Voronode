"""Graph builder service - inserts invoices into Neo4j knowledge graph."""

import uuid
from typing import Optional, Dict, Any
import structlog

from backend.core.models import Invoice, LineItem
from backend.graph.client import Neo4jClient

logger = structlog.get_logger()


class GraphBuilder:
    """Insert invoices and related entities into Neo4j graph."""

    def __init__(self):
        self.neo4j_client = Neo4jClient()

    def insert_invoice(self, invoice: Invoice) -> str:
        """
        Insert invoice into Neo4j with all relationships.

        Pipeline:
        1. Ensure contractor exists (or create placeholder)
        2. Create invoice node (idempotent MERGE)
        3. Create line items with relationships
        4. Link to contract if available
        5. Link to budget lines by cost code

        Args:
            invoice: Invoice model to insert

        Returns:
            Invoice ID (Neo4j node ID)

        Raises:
            ValueError: If insertion fails
        """
        logger.info(
            "starting_graph_insertion",
            invoice_number=invoice.invoice_number,
            contractor_id=invoice.contractor_id,
        )

        try:
            # Step 1: Ensure contractor exists
            contractor_id = self._ensure_contractor(invoice.contractor_id)
            logger.info("contractor_resolved", contractor_id=contractor_id)

            # Step 2: Create invoice node
            invoice_id = self._create_invoice_node(invoice, contractor_id)
            logger.info("invoice_node_created", invoice_id=invoice_id)

            # Step 3: Create line items
            for item in invoice.line_items:
                self._create_line_item(invoice_id, item)

            logger.info(
                "graph_insertion_complete",
                invoice_id=invoice_id,
                line_items=len(invoice.line_items),
            )

            return invoice_id

        except Exception as e:
            logger.error(
                "graph_insertion_failed",
                invoice_number=invoice.invoice_number,
                error=str(e),
            )
            raise ValueError(f"Failed to insert invoice into graph: {e}")

    def _ensure_contractor(self, name_or_id: str) -> str:
        """
        Find contractor by name or ID, or create placeholder if not found.

        Args:
            name_or_id: Contractor name or ID from extraction

        Returns:
            Contractor ID (existing or newly created)
        """
        # Try to find existing contractor by name
        query = """
        MATCH (c:Contractor)
        WHERE c.name = $name OR c.id = $name
        RETURN c.id as id
        LIMIT 1
        """

        result = self.neo4j_client.run_query(query, {"name": name_or_id})

        if result:
            return result[0]["id"]

        # Create placeholder contractor
        contractor_id = str(uuid.uuid4())
        placeholder_license = f"PENDING-{uuid.uuid4()}"

        create_query = """
        MERGE (c:Contractor {id: $id})
        SET c.name = $name,
            c.license_number = $license_number,
            c.created_from = 'invoice_extraction',
            c.created_at = datetime()
        RETURN c.id as id
        """

        params = {
            "id": contractor_id,
            "name": name_or_id,
            "license_number": placeholder_license,
        }

        result = self.neo4j_client.run_query(create_query, params)

        logger.info(
            "placeholder_contractor_created",
            contractor_id=contractor_id,
            name=name_or_id,
        )

        return contractor_id

    def _create_invoice_node(self, invoice: Invoice, contractor_id: str) -> str:
        """
        Create or update invoice node with MERGE (idempotent).

        Args:
            invoice: Invoice model
            contractor_id: Resolved contractor ID

        Returns:
            Invoice ID
        """
        query = """
        MERGE (i:Invoice {invoice_number: $invoice_number})
        ON CREATE SET i.id = $id,
                      i.date = date($date),
                      i.amount = $amount,
                      i.status = $status,
                      i.created_at = datetime()
        ON MATCH SET i.date = date($date),
                     i.amount = $amount,
                     i.status = $status,
                     i.updated_at = datetime()
        SET i.due_date = CASE WHEN $due_date IS NOT NULL THEN date($due_date) ELSE null END,
            i.extracted_at = datetime($extracted_at),
            i.extraction_confidence = $extraction_confidence

        WITH i
        MATCH (c:Contractor {id: $contractor_id})
        MERGE (c)-[:ISSUED]->(i)

        WITH i
        OPTIONAL MATCH (con:Contract {id: $contract_id})
        FOREACH (x IN CASE WHEN con IS NOT NULL THEN [1] ELSE [] END |
            MERGE (i)-[:BILLED_AGAINST]->(con)
        )

        RETURN i.id as id
        """

        params = {
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "date": str(invoice.date),
            "due_date": str(invoice.due_date) if invoice.due_date else None,
            "amount": float(invoice.amount),
            "status": invoice.status,
            "extracted_at": invoice.extracted_at.isoformat() if invoice.extracted_at else None,
            "extraction_confidence": invoice.extraction_confidence,
            "contractor_id": contractor_id,
            "contract_id": invoice.contract_id,
        }

        result = self.neo4j_client.run_query(query, params)

        if not result:
            raise ValueError("Failed to create invoice node")

        return result[0]["id"]

    def _create_line_item(self, invoice_id: str, item: LineItem) -> None:
        """
        Create line item node and relationships.

        Links:
        - Invoice CONTAINS_ITEM LineItem
        - LineItem MAPS_TO BudgetLine (if cost code matches)

        Args:
            invoice_id: Parent invoice ID
            item: LineItem model
        """
        query = """
        MERGE (li:LineItem {id: $id})
        SET li.description = $description,
            li.cost_code = $cost_code,
            li.quantity = $quantity,
            li.unit_price = $unit_price,
            li.total = $total,
            li.updated_at = datetime()

        WITH li
        MATCH (i:Invoice {id: $invoice_id})
        MERGE (i)-[:CONTAINS_ITEM]->(li)

        WITH li
        OPTIONAL MATCH (bl:BudgetLine {cost_code: $cost_code})
        FOREACH (x IN CASE WHEN bl IS NOT NULL THEN [1] ELSE [] END |
            MERGE (li)-[:MAPS_TO]->(bl)
        )
        """

        params = {
            "id": item.id,
            "description": item.description,
            "cost_code": item.cost_code,
            "quantity": float(item.quantity),
            "unit_price": float(item.unit_price),
            "total": float(item.total),
            "invoice_id": invoice_id,
        }

        self.neo4j_client.run_query(query, params)

        logger.debug(
            "line_item_created",
            line_item_id=item.id,
            cost_code=item.cost_code,
        )

    def get_invoice_by_id(self, invoice_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve invoice with line items from Neo4j.

        Args:
            invoice_id: Invoice ID

        Returns:
            Invoice data with nested line items, or None if not found
        """
        query = """
        MATCH (i:Invoice {id: $invoice_id})
        OPTIONAL MATCH (i)-[:CONTAINS_ITEM]->(li:LineItem)
        OPTIONAL MATCH (c:Contractor)-[:ISSUED]->(i)
        RETURN i,
               c.name as contractor_name,
               collect({
                   id: li.id,
                   description: li.description,
                   cost_code: li.cost_code,
                   quantity: li.quantity,
                   unit_price: li.unit_price,
                   total: li.total
               }) as line_items
        """

        result = self.neo4j_client.run_query(query, {"invoice_id": invoice_id})

        if not result:
            return None

        record = result[0]
        invoice_node = record["i"]

        # Convert Neo4j node to dict
        invoice_data = {
            "id": invoice_node["id"],
            "invoice_number": invoice_node["invoice_number"],
            "date": str(invoice_node["date"]),
            "due_date": str(invoice_node["due_date"]) if invoice_node.get("due_date") else None,
            "amount": invoice_node["amount"],
            "status": invoice_node["status"],
            "contractor_name": record["contractor_name"],
            "line_items": [
                item for item in record["line_items"] if item["id"] is not None
            ],
        }

        return invoice_data
