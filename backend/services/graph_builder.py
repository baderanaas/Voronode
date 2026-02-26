"""Graph builder service - inserts invoices and contracts into Neo4j knowledge graph."""

import json
import uuid
from typing import Optional, Dict, Any, List
import structlog

from backend.core.models import Invoice, LineItem, Contract
from backend.graph.client import Neo4jClient

logger = structlog.get_logger()


class GraphBuilder:
    """Insert invoices and related entities into Neo4j graph."""

    def __init__(self):
        self.neo4j_client = Neo4jClient()

    def insert_invoice(self, invoice: Invoice, user_id: str = "default_user") -> str:
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
            invoice_id = self._create_invoice_node(invoice, contractor_id, user_id)
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

    def _create_invoice_node(
        self, invoice: Invoice, contractor_id: str, user_id: str = "default_user"
    ) -> str:
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
            i.extraction_confidence = $extraction_confidence,
            i.user_id = $user_id

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
            "user_id": user_id,
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

    def insert_contract(self, contract: Contract, user_id: str = "default_user") -> str:
        """
        Insert contract into Neo4j with all relationships.

        Pipeline:
        1. Ensure contractor exists
        2. Ensure project exists
        3. Create contract node (idempotent MERGE)
        4. Create relationships

        Args:
            contract: Contract model to insert

        Returns:
            Contract ID
        """
        logger.info(
            "starting_contract_insertion",
            contract_id=contract.id,
            contractor_id=contract.contractor_id,
        )

        try:
            # Step 1: Ensure contractor exists
            contractor_name = contract.contractor_name or contract.contractor_id
            contractor_id = self._ensure_contractor(contractor_name)
            logger.info("contractor_resolved", contractor_id=contractor_id)

            # Step 2: Ensure project exists
            project_id = self._ensure_project(
                contract.project_id, contract.project_name
            )
            logger.info("project_resolved", project_id=project_id)

            # Step 3: Create contract node
            # Neo4j doesn't support nested maps, so serialize unit_price_schedule as JSON
            unit_price_json = json.dumps(
                {k: float(v) for k, v in contract.unit_price_schedule.items()}
            )

            query = """
            MERGE (ct:Contract {contract_id: $contract_id})
            ON CREATE SET ct.id = $id,
                          ct.contractor_id = $contractor_id,
                          ct.contractor_name = $contractor_name,
                          ct.project_id = $project_id,
                          ct.project_name = $project_name,
                          ct.value = $value,
                          ct.retention_rate = $retention_rate,
                          ct.start_date = date($start_date),
                          ct.end_date = date($end_date),
                          ct.terms = $terms,
                          ct.unit_price_schedule = $unit_price_schedule,
                          ct.approved_cost_codes = $approved_cost_codes,
                          ct.extracted_at = datetime($extracted_at),
                          ct.extraction_confidence = $extraction_confidence,
                          ct.user_id = $user_id,
                          ct.created_at = datetime()
            ON MATCH SET ct.contractor_name = $contractor_name,
                         ct.project_name = $project_name,
                         ct.value = $value,
                         ct.retention_rate = $retention_rate,
                         ct.start_date = date($start_date),
                         ct.end_date = date($end_date),
                         ct.terms = $terms,
                         ct.unit_price_schedule = $unit_price_schedule,
                         ct.approved_cost_codes = $approved_cost_codes,
                         ct.extracted_at = datetime($extracted_at),
                         ct.extraction_confidence = $extraction_confidence,
                         ct.user_id = $user_id,
                         ct.updated_at = datetime()

            WITH ct
            MATCH (c:Contractor {id: $resolved_contractor_id})
            MERGE (c)-[:HAS_CONTRACT]->(ct)

            WITH ct
            MATCH (p:Project {id: $resolved_project_id})
            MERGE (ct)-[:FOR_PROJECT]->(p)

            RETURN ct.contract_id as contract_id
            """

            params = {
                "id": contract.id,
                "contract_id": contract.id,
                "contractor_id": contract.contractor_id,
                "contractor_name": contract.contractor_name,
                "project_id": contract.project_id,
                "project_name": contract.project_name,
                "value": float(contract.value),
                "retention_rate": float(contract.retention_rate),
                "start_date": str(contract.start_date),
                "end_date": str(contract.end_date),
                "terms": contract.terms,
                "unit_price_schedule": unit_price_json,
                "approved_cost_codes": contract.approved_cost_codes,
                "extracted_at": contract.extracted_at.isoformat() if contract.extracted_at else None,
                "extraction_confidence": contract.extraction_confidence,
                "user_id": user_id,
                "resolved_contractor_id": contractor_id,
                "resolved_project_id": project_id,
            }

            result = self.neo4j_client.run_query(query, params)

            if not result:
                raise ValueError("Failed to create contract node")

            logger.info(
                "contract_insertion_complete",
                contract_id=contract.id,
            )

            return contract.id

        except Exception as e:
            logger.error(
                "contract_insertion_failed",
                contract_id=contract.id,
                error=str(e),
            )
            raise ValueError(f"Failed to insert contract into graph: {e}")

    def _ensure_project(self, project_id: str, project_name: Optional[str] = None) -> str:
        """
        Find project by ID, or create placeholder if not found.

        Args:
            project_id: Project ID
            project_name: Optional project name

        Returns:
            Project ID (existing or newly created)
        """
        query = """
        MATCH (p:Project)
        WHERE p.id = $id
        RETURN p.id as id
        LIMIT 1
        """

        result = self.neo4j_client.run_query(query, {"id": project_id})

        if result:
            return result[0]["id"]

        # Create placeholder project
        create_query = """
        MERGE (p:Project {id: $id})
        SET p.name = $name,
            p.budget = 0,
            p.start_date = date(),
            p.end_date = date(),
            p.status = 'active',
            p.created_from = 'contract_extraction',
            p.created_at = datetime()
        RETURN p.id as id
        """

        params = {
            "id": project_id,
            "name": project_name or project_id,
        }

        result = self.neo4j_client.run_query(create_query, params)

        logger.info(
            "placeholder_project_created",
            project_id=project_id,
            name=project_name,
        )

        return project_id

    def get_contract_by_id(self, contract_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve contract from Neo4j.

        Args:
            contract_id: Contract ID

        Returns:
            Contract data dict, or None if not found
        """
        query = """
        MATCH (ct:Contract {contract_id: $contract_id})
        OPTIONAL MATCH (c:Contractor)-[:HAS_CONTRACT]->(ct)
        OPTIONAL MATCH (ct)-[:FOR_PROJECT]->(p:Project)
        RETURN ct,
               c.name as contractor_name,
               p.name as project_name
        """

        result = self.neo4j_client.run_query(query, {"contract_id": contract_id})

        if not result:
            return None

        record = result[0]
        node = record["ct"]

        # Deserialize unit_price_schedule from JSON string
        unit_price_schedule = node.get("unit_price_schedule", "{}")
        if isinstance(unit_price_schedule, str):
            unit_price_schedule = json.loads(unit_price_schedule)

        approved_cost_codes = node.get("approved_cost_codes", [])

        return {
            "id": node.get("contract_id"),
            "contractor_id": node.get("contractor_id"),
            "contractor_name": record.get("contractor_name") or node.get("contractor_name"),
            "project_id": node.get("project_id"),
            "project_name": record.get("project_name") or node.get("project_name"),
            "value": node.get("value"),
            "retention_rate": node.get("retention_rate"),
            "start_date": str(node.get("start_date")) if node.get("start_date") else None,
            "end_date": str(node.get("end_date")) if node.get("end_date") else None,
            "terms": node.get("terms"),
            "unit_price_schedule": unit_price_schedule,
            "approved_cost_codes": approved_cost_codes,
            "extraction_confidence": node.get("extraction_confidence"),
        }

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

    def insert_budget(
        self,
        budget: "Budget",
        budget_lines: List["BudgetLine"],
        user_id: str = "default_user",
    ) -> str:
        """
        Insert budget and budget lines into Neo4j.

        Pipeline:
        1. Ensure project exists
        2. Create Budget node (idempotent MERGE)
        3. Create BudgetLine nodes
        4. Create relationships

        Args:
            budget: Budget model
            budget_lines: List of BudgetLine models

        Returns:
            Budget ID
        """
        from backend.core.models import Budget, BudgetLine

        logger.info(
            "starting_budget_insertion",
            budget_id=budget.id,
            project_id=budget.project_id,
            line_count=len(budget_lines),
        )

        try:
            # Step 1: Ensure project exists
            project_id = self._ensure_project(budget.project_id, budget.project_name)
            logger.info("project_resolved", project_id=project_id)

            # Step 2: Create Budget node
            budget_query = """
            MERGE (b:Budget {id: $id})
            ON CREATE SET b.budget_id = $budget_id,
                          b.project_id = $project_id,
                          b.project_name = $project_name,
                          b.total_allocated = $total_allocated,
                          b.total_spent = $total_spent,
                          b.total_remaining = $total_remaining,
                          b.line_count = $line_count,
                          b.extracted_at = datetime($extracted_at),
                          b.validation_warnings = $validation_warnings,
                          b.status = $status,
                          b.user_id = $user_id,
                          b.created_at = datetime()
            ON MATCH SET b.project_name = $project_name,
                         b.total_allocated = $total_allocated,
                         b.total_spent = $total_spent,
                         b.total_remaining = $total_remaining,
                         b.line_count = $line_count,
                         b.extracted_at = datetime($extracted_at),
                         b.validation_warnings = $validation_warnings,
                         b.status = $status,
                         b.user_id = $user_id,
                         b.updated_at = datetime()

            WITH b
            MATCH (p:Project {id: $resolved_project_id})
            MERGE (p)-[:HAS_BUDGET]->(b)

            RETURN b.id as budget_id
            """

            budget_params = {
                "id": budget.id,
                "budget_id": budget.id,
                "project_id": budget.project_id,
                "project_name": budget.project_name,
                "total_allocated": float(budget.total_allocated),
                "total_spent": float(budget.total_spent),
                "total_remaining": float(budget.total_remaining),
                "line_count": budget.line_count,
                "extracted_at": budget.extracted_at.isoformat() if budget.extracted_at else None,
                "validation_warnings": budget.validation_warnings,
                "status": budget.status,
                "user_id": user_id,
                "resolved_project_id": project_id,
            }

            result = self.neo4j_client.run_query(budget_query, budget_params)

            if not result:
                raise ValueError("Failed to create budget node")

            # Step 3: Insert budget lines
            for line in budget_lines:
                self._insert_budget_line(line, budget.id, project_id, user_id)

            logger.info(
                "budget_insertion_complete",
                budget_id=budget.id,
                lines_inserted=len(budget_lines),
            )

            return budget.id

        except Exception as e:
            logger.error(
                "budget_insertion_failed",
                budget_id=budget.id,
                error=str(e),
            )
            raise ValueError(f"Failed to insert budget into graph: {e}")

    def _insert_budget_line(
        self,
        line: "BudgetLine",
        budget_id: str,
        project_id: str,
        user_id: str = "default_user",
    ):
        """Insert a single budget line into Neo4j."""
        query = """
        MERGE (bl:BudgetLine {id: $id})
        ON CREATE SET bl.budget_line_id = $budget_line_id,
                      bl.project_id = $project_id,
                      bl.cost_code = $cost_code,
                      bl.description = $description,
                      bl.allocated = $allocated,
                      bl.spent = $spent,
                      bl.remaining = $remaining,
                      bl.user_id = $user_id,
                      bl.created_at = datetime()
        ON MATCH SET bl.allocated = $allocated,
                     bl.spent = $spent,
                     bl.remaining = $remaining,
                     bl.updated_at = datetime()

        WITH bl
        MATCH (b:Budget {id: $budget_id})
        MERGE (b)-[:HAS_LINE]->(bl)

        WITH bl
        MATCH (p:Project {id: $project_id})
        MERGE (p)-[:HAS_BUDGET_LINE]->(bl)

        RETURN bl.id as line_id
        """

        params = {
            "id": line.id,
            "budget_line_id": line.id,
            "budget_id": budget_id,
            "project_id": project_id,
            "cost_code": line.cost_code,
            "description": line.description,
            "allocated": float(line.allocated),
            "spent": float(line.spent),
            "remaining": float(line.remaining),
            "user_id": user_id,
        }

        self.neo4j_client.run_query(query, params)

        logger.debug(
            "budget_line_inserted",
            line_id=line.id,
            cost_code=line.cost_code,
        )

    def get_budget_by_id(self, budget_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve budget with all budget lines from Neo4j.

        Args:
            budget_id: Budget ID

        Returns:
            Budget data dict with budget_lines array, or None if not found
        """
        query = """
        MATCH (b:Budget {id: $budget_id})
        OPTIONAL MATCH (p:Project)-[:HAS_BUDGET]->(b)
        OPTIONAL MATCH (b)-[:HAS_LINE]->(bl:BudgetLine)
        RETURN b,
               p.name as project_name,
               collect(bl) as budget_lines
        """

        result = self.neo4j_client.run_query(query, {"budget_id": budget_id})

        if not result:
            return None

        record = result[0]
        budget_node = record["b"]
        budget_lines = record["budget_lines"]

        return {
            "id": budget_node.get("id"),
            "project_id": budget_node.get("project_id"),
            "project_name": record.get("project_name") or budget_node.get("project_name"),
            "total_allocated": budget_node.get("total_allocated"),
            "total_spent": budget_node.get("total_spent"),
            "total_remaining": budget_node.get("total_remaining"),
            "line_count": budget_node.get("line_count"),
            "status": budget_node.get("status"),
            "budget_lines": [
                {
                    "id": line.get("id"),
                    "cost_code": line.get("cost_code"),
                    "description": line.get("description"),
                    "allocated": line.get("allocated"),
                    "spent": line.get("spent"),
                    "remaining": line.get("remaining"),
                }
                for line in budget_lines
                if line is not None
            ],
        }

    def get_budgets_by_project(self, project_id: str) -> List[Dict[str, Any]]:
        """
        Get all budgets for a project.

        Args:
            project_id: Project ID

        Returns:
            List of budget data dicts
        """
        query = """
        MATCH (p:Project {id: $project_id})-[:HAS_BUDGET]->(b:Budget)
        OPTIONAL MATCH (b)-[:HAS_LINE]->(bl:BudgetLine)
        RETURN b,
               collect(bl) as budget_lines
        ORDER BY b.created_at DESC
        """

        results = self.neo4j_client.run_query(query, {"project_id": project_id})

        budgets = []
        for record in results:
            budget_node = record["b"]
            budget_lines = record["budget_lines"]

            budgets.append({
                "id": budget_node.get("id"),
                "project_id": budget_node.get("project_id"),
                "project_name": budget_node.get("project_name"),
                "total_allocated": budget_node.get("total_allocated"),
                "total_spent": budget_node.get("total_spent"),
                "total_remaining": budget_node.get("total_remaining"),
                "line_count": budget_node.get("line_count"),
                "status": budget_node.get("status"),
                "budget_lines": [
                    {
                        "id": line.get("id"),
                        "cost_code": line.get("cost_code"),
                        "description": line.get("description"),
                        "allocated": line.get("allocated"),
                        "spent": line.get("spent"),
                        "remaining": line.get("remaining"),
                    }
                    for line in budget_lines
                    if line is not None
                ],
            })

        return budgets
