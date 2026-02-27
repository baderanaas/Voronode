"""
CypherQueryTool - Query Neo4j graph database.

Core domain tool for querying invoices, contracts, budgets, projects, and contractors.
Generates and executes Cypher queries based on natural language actions.
"""

import re
import structlog
from typing import Dict, Any, Optional, List
from datetime import date, datetime
from neo4j.time import Date, DateTime, Time
from pydantic import BaseModel, Field

from backend.graph.client import Neo4jClient
from backend.services.llm_client import AnthropicClient
from backend.agents.prompts.prompt_manager import render_prompt

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

    def __init__(self):
        """Initialize with Neo4j client and Anthropic LLM (Claude Haiku 4.5)."""
        self.neo4j_client = Neo4jClient()
        self.llm = AnthropicClient()

    def run(
        self,
        query: str = "",
        action: str = "",
        context: Optional[Dict[str, Any]] = None,
        user_id: str = "default_user",
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
        cypher_query = self._generate_cypher(action, query, context, user_id)

        if not cypher_query:
            return {
                "error": "Failed to generate Cypher query",
                "action": action,
                "status": "failed",
            }

        logger.info("cypher_generated", query=cypher_query[:200])

        # Inject user_id filter in code — never trust the LLM to do it
        cypher_query, params = self._inject_user_filter(cypher_query, user_id)
        logger.info("cypher_user_filter_applied", user_id=user_id)

        # Execute query
        try:
            results = self.neo4j_client.run_query(cypher_query, parameters=params)

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
        user_id: str = "default_user",
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
        context_info = None
        if context and context.get("previous_results"):
            context_info = f"\nPrevious Results: {context['previous_results']}"

        # Render prompt from Jinja2 template
        prompt = render_prompt(
            "cypher_tool/generate_query.j2",
            action=action,
            original_query=original_query,
            context_info=context_info,
        )

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
                        response.get("query")
                        or response.get("cypher")
                        or response.get("cypher_query")
                        or list(response.values())[0]
                        if response
                        else ""
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

    # Labels whose nodes carry a user_id property
    _USER_SCOPED_LABELS = {"Invoice", "Contract", "Budget", "BudgetLine"}

    def _inject_user_filter(self, cypher: str, user_id: str) -> tuple[str, dict]:
        """
        Programmatically inject user_id filtering into an LLM-generated Cypher query.

        Uses Neo4j parameterized queries so the user_id value is never concatenated
        into the query string (prevents injection). Returns the modified query and
        the parameters dict to pass to run_query().
        """ 
        params: dict = {}

        # Find all (alias:Label) patterns for user-scoped node types
        aliases = {
            m.group(1)
            for m in re.finditer(r"\((\w+):(\w+)", cypher)
            if m.group(2) in self._USER_SCOPED_LABELS
        }

        if not aliases:
            return cypher, params

        params["_user_id"] = user_id
        conditions = " AND ".join(f"{a}.user_id = $_user_id" for a in sorted(aliases))

        first_with = re.search(r"\bWITH\b", cypher, re.IGNORECASE)
        boundary = first_with.start() if first_with else len(cypher)

        where_m = re.search(r"\bWHERE\b", cypher, re.IGNORECASE)
        if where_m and where_m.start() < boundary:
            pos = where_m.end()
            cypher = cypher[:pos] + f" {conditions} AND" + cypher[pos:]
        else:
            if first_with:
                pos = boundary
            else:
                pos = len(cypher)
                for keyword in ("RETURN", "ORDER", "LIMIT"):
                    kw_m = re.search(rf"\b{keyword}\b", cypher, re.IGNORECASE)
                    if kw_m:
                        pos = kw_m.start()
                        break
            cypher = cypher[:pos] + f"WHERE {conditions} " + cypher[pos:]

        return cypher, params
