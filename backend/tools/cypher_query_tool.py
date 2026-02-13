"""
CypherQueryTool - Query Neo4j graph database.

Core domain tool for querying invoices, contracts, budgets, projects, and contractors.
Generates and executes Cypher queries based on natural language actions.
"""

import structlog
from typing import Dict, Any, Optional, List
from datetime import date, datetime
from neo4j.time import Date, DateTime, Time
from pydantic import BaseModel, Field

from backend.graph.client import Neo4jClient
from backend.services.llm_client import OpenAIClient

logger = structlog.get_logger()


class CypherQueryResponse(BaseModel):
    """Pydantic model for structuring LLM-generated Cypher queries."""

    query: str = Field(
        ...,
        description="Cypher query string",
        min_length=1,
    )


class CypherQueryTool:
    """
    Tool for querying Neo4j graph database with Cypher.

    Capabilities:
    - Generate Cypher queries from natural language
    - Execute queries on Neo4j
    - Format results for consumption
    - Handle graph schema knowledge
    """

    # Graph schema reference for LLM
    SCHEMA_DESCRIPTION = """
    Neo4j Graph Schema:

    Nodes:
    - Invoice (invoice_id, invoice_number, date, due_date, amount, status)
    - LineItem (line_item_id, description, cost_code, quantity, unit_price, total)
    - Contract (contract_id, contractor_id, project_id, value, retention_rate, start_date, end_date, approved_cost_codes, unit_price_schedule)
    - Contractor (contractor_id, name, license_number, rating)
    - Project (project_id, name, budget, start_date, end_date, status)
    - Budget (budget_id, project_id, total_allocated, total_spent, total_remaining)
    - BudgetLine (line_id, cost_code, description, allocated, spent, remaining)

    Relationships:
    - (Contractor)-[:SUBMITTED]->(Invoice)
    - (Invoice)-[:FOR_PROJECT]->(Project)
    - (Invoice)-[:FOR_CONTRACT]->(Contract)
    - (Invoice)-[:HAS_ITEM]->(LineItem)
    - (Contract)-[:FOR_PROJECT]->(Project)
    - (Contract)-[:WITH_CONTRACTOR]->(Contractor)
    - (Project)-[:HAS_BUDGET]->(Budget)
    - (Budget)-[:HAS_LINE]->(BudgetLine)

    IMPORTANT:
    - Use contract_id (not id) for Contract nodes
    - Use invoice_id or invoice_number for Invoice nodes
    - Use contractor_id for Contractor nodes
    - Use project_id for Project nodes
    """

    def __init__(self):
        """Initialize with Neo4j client and OpenAI LLM (GPT-4o-mini)."""
        self.neo4j_client = Neo4jClient()
        self.llm = OpenAIClient()

    def run(
        self,
        query: str = "",
        action: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate and execute Cypher query.

        Args:
            query: User's original query
            action: Specific action (e.g., "Find invoices over $50k")
            context: Previous results for ReAct mode

        Returns:
            {
                "cypher_query": "<generated Cypher>",
                "results": [...],  # Query results
                "count": 5,
                "status": "success" | "failed"
            }
        """
        logger.info("cypher_tool_executing", action=action[:100])

        # Generate Cypher query from action
        cypher_query = self._generate_cypher(action, query, context)

        if not cypher_query:
            return {
                "error": "Failed to generate Cypher query",
                "action": action,
                "status": "failed",
            }

        logger.info("cypher_generated", query=cypher_query[:200])

        # Execute query
        try:
            results = self.neo4j_client.run_query(cypher_query)

            # Serialize Neo4j types to JSON-compatible types
            serialized_results = self._serialize_neo4j_types(results)

            logger.info("cypher_executed", result_count=len(serialized_results))

            return {
                "cypher_query": cypher_query,
                "results": serialized_results,
                "count": len(serialized_results),
                "status": "success",
            }

        except Exception as e:
            logger.error("cypher_execution_failed", error=str(e), query=cypher_query)
            return {
                "error": str(e),
                "cypher_query": cypher_query,
                "action": action,
                "status": "failed",
            }

    def _serialize_neo4j_types(self, data: Any) -> Any:
        """
        Recursively convert Neo4j types to JSON-serializable types.

        Args:
            data: Data from Neo4j (can be dict, list, or primitive)

        Returns:
            JSON-serializable version of the data
        """
        if isinstance(data, (Date, date)):
            return data.isoformat()
        elif isinstance(data, (DateTime, datetime)):
            return data.isoformat()
        elif isinstance(data, Time):
            return data.isoformat()
        elif isinstance(data, dict):
            return {k: self._serialize_neo4j_types(v) for k, v in data.items()}
        elif isinstance(data, (list, tuple)):
            return [self._serialize_neo4j_types(item) for item in data]
        else:
            return data

    def _generate_cypher(
        self,
        action: str,
        original_query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Generate Cypher query from natural language action.

        Args:
            action: What to query (e.g., "Find invoices over $50k")
            original_query: User's original question
            context: Previous results for ReAct mode

        Returns:
            Cypher query string
        """
        # Build context from previous results if in ReAct mode
        context_info = ""
        if context and context.get("previous_results"):
            context_info = f"\nPrevious Results: {context['previous_results']}"

        prompt = f"""
        Generate a Cypher query for Neo4j based on this action.

        Action: "{action}"
        Original User Query: "{original_query}"
        {context_info}

        {self.SCHEMA_DESCRIPTION}

        Guidelines:
        1. Return ONLY the Cypher query, no explanation
        2. Use MATCH patterns appropriate for the schema
        3. Include WHERE clauses for filtering
        4. Use WITH for intermediate aggregations, then RETURN at the end
        5. Add LIMIT if querying many records (default: 100)
        6. Use proper Cypher syntax (case-sensitive)
        7. For amounts, use numeric comparisons (e.g., i.amount > 50000)
        8. For dates, use date() function (e.g., i.date > date('2025-01-01'))
        9. Use OPTIONAL MATCH for relationships that might not exist

        CRITICAL: Never use RETURN followed by WITH. The correct order is:
        - MATCH ... WITH ... RETURN ... (correct)
        - MATCH ... RETURN ... (correct)
        - MATCH ... RETURN ... WITH ... (WRONG - will cause syntax error)

        Common patterns:
        - Find invoices: MATCH (i:Invoice) WHERE i.amount > 50000 RETURN i LIMIT 100
        - Find with contractor: MATCH (c:Contractor)-[:SUBMITTED]->(i:Invoice) WHERE c.contractor_id = 'CONT-001' RETURN i, c
        - Find with project: MATCH (i:Invoice)-[:FOR_PROJECT]->(p:Project) WHERE p.project_id = 'PRJ-001' RETURN i, p
        - Aggregations: MATCH (c:Contractor)-[:SUBMITTED]->(i:Invoice)-[:HAS_ITEM]->(li:LineItem) WITH li.cost_code AS costCode, SUM(i.amount) AS total RETURN costCode, total ORDER BY total DESC LIMIT 5
        - Sort: ORDER BY i.amount DESC
        - Limit: LIMIT 100

        Return ONLY a JSON object with the Cypher query in this exact format:
        {{
            "query": "MATCH (i:Invoice) WHERE i.amount > 50000 RETURN i LIMIT 100"
        }}
        """

        try:
            # Get LLM to generate Cypher with Pydantic validation
            response = self.llm.extract_json(
                prompt,
                temperature=0.1,
                schema=CypherQueryResponse,
            )

            # Response is already validated by LLM client if schema was provided
            # The schema parameter ensures Pydantic validation before returning
            if isinstance(response, dict) and "query" in response:
                cypher = response["query"]
                logger.info("cypher_validation_passed", query_length=len(cypher))
            else:
                # Fallback: try to extract query
                logger.warning("unexpected_response_format", response=response)
                if isinstance(response, dict):
                    cypher = (
                        response.get("query") or
                        response.get("cypher") or
                        response.get("cypher_query") or
                        list(response.values())[0] if response else ""
                    )
                else:
                    cypher = str(response)

            # Clean up the query
            cypher = cypher.strip()
            cypher = cypher.replace("```cypher", "").replace("```", "")
            cypher = cypher.strip()

            return cypher

        except Exception as e:
            logger.error("cypher_generation_failed", error=str(e))
            return ""
