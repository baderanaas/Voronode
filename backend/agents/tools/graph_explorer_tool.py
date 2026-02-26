"""
GraphExplorerTool - Explore relationships in Neo4j graph.

Domain tool for traversing and discovering relationships between entities
(invoices, contractors, projects, contracts, budgets).
"""

import structlog
from typing import Dict, Any, Optional

from backend.graph.client import Neo4jClient

logger = structlog.get_logger()


class GraphExplorerTool:
    """
    Tool for exploring graph relationships.

    Capabilities:
    - Find related entities (contractor's invoices, project's contracts, etc.)
    - Traverse relationships (multi-hop queries)
    - Discover connections
    - Relationship statistics
    """

    def __init__(self):
        """Initialize with Neo4j client."""
        self.neo4j_client = Neo4jClient()

    def run(
        self,
        query: str = "",
        action: str = "",
        context: Optional[Dict[str, Any]] = None,
        entity_id: Optional[str] = None,
        entity_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Explore graph relationships.

        Args:
            query: User's original query
            action: What to explore (e.g., "Find all invoices for contractor X")
            context: Previous results
            entity_id: Specific entity ID to explore from
            entity_type: Type of entity (Invoice, Contractor, Project, etc.)

        Returns:
            {
                "entity": {...},  # Source entity
                "relationships": [...],  # Related entities
                "count": 5,
                "status": "success" | "failed"
            }
        """
        logger.info("graph_explorer_executing", action=action[:100])

        # Determine exploration type from action
        action_lower = action.lower()

        try:
            if "contractor" in action_lower and "invoice" in action_lower:
                return self._find_contractor_invoices(action, context)

            elif "project" in action_lower and "invoice" in action_lower:
                return self._find_project_invoices(action, context)

            elif "project" in action_lower and "contract" in action_lower:
                return self._find_project_contracts(action, context)

            elif "contractor" in action_lower and "contract" in action_lower:
                return self._find_contractor_contracts(action, context)

            elif "project" in action_lower and "budget" in action_lower:
                return self._find_project_budget(action, context)

            else:
                # Generic relationship exploration
                return self._explore_generic(action, entity_id, entity_type)

        except Exception as e:
            logger.error("graph_explorer_failed", error=str(e), action=action)
            return {
                "error": str(e),
                "action": action,
                "status": "failed",
            }

    def _find_contractor_invoices(self, action: str, context: Optional[Dict]) -> Dict[str, Any]:
        """Find all invoices for a contractor."""
        # Extract contractor ID or name from action or context
        contractor_id = self._extract_entity_id(action, context, "contractor")

        if not contractor_id:
            return {
                "error": "Could not identify contractor from context",
                "status": "failed",
            }

        # Query Neo4j
        cypher = f"""
        MATCH (c:Contractor)-[:SUBMITTED]->(i:Invoice)
        WHERE c.id = '{contractor_id}' OR c.name CONTAINS '{contractor_id}'
        RETURN i, c
        LIMIT 100
        """

        results = self.neo4j_client.run_query(cypher)

        return {
            "exploration": "contractor invoices",
            "contractor_id": contractor_id,
            "invoices": results,
            "count": len(results),
            "status": "success",
        }

    def _find_project_invoices(self, action: str, context: Optional[Dict]) -> Dict[str, Any]:
        """Find all invoices for a project."""
        project_id = self._extract_entity_id(action, context, "project")

        if not project_id:
            return {
                "error": "Could not identify project from context",
                "status": "failed",
            }

        cypher = f"""
        MATCH (p:Project)<-[:FOR_PROJECT]-(i:Invoice)
        WHERE p.id = '{project_id}' OR p.name CONTAINS '{project_id}'
        RETURN i, p
        LIMIT 100
        """

        results = self.neo4j_client.run_query(cypher)

        return {
            "exploration": "project invoices",
            "project_id": project_id,
            "invoices": results,
            "count": len(results),
            "status": "success",
        }

    def _find_project_contracts(self, action: str, context: Optional[Dict]) -> Dict[str, Any]:
        """Find all contracts for a project."""
        project_id = self._extract_entity_id(action, context, "project")

        if not project_id:
            return {"error": "Could not identify project", "status": "failed"}

        cypher = f"""
        MATCH (p:Project)<-[:FOR_PROJECT]-(c:Contract)
        WHERE p.id = '{project_id}' OR p.name CONTAINS '{project_id}'
        RETURN c, p
        LIMIT 100
        """

        results = self.neo4j_client.run_query(cypher)

        return {
            "exploration": "project contracts",
            "project_id": project_id,
            "contracts": results,
            "count": len(results),
            "status": "success",
        }

    def _find_contractor_contracts(self, action: str, context: Optional[Dict]) -> Dict[str, Any]:
        """Find all contracts for a contractor."""
        contractor_id = self._extract_entity_id(action, context, "contractor")

        if not contractor_id:
            return {"error": "Could not identify contractor", "status": "failed"}

        cypher = f"""
        MATCH (c:Contractor)<-[:WITH_CONTRACTOR]-(contract:Contract)
        WHERE c.id = '{contractor_id}' OR c.name CONTAINS '{contractor_id}'
        RETURN contract, c
        LIMIT 100
        """

        results = self.neo4j_client.run_query(cypher)

        return {
            "exploration": "contractor contracts",
            "contractor_id": contractor_id,
            "contracts": results,
            "count": len(results),
            "status": "success",
        }

    def _find_project_budget(self, action: str, context: Optional[Dict]) -> Dict[str, Any]:
        """Find budget for a project."""
        project_id = self._extract_entity_id(action, context, "project")

        if not project_id:
            return {"error": "Could not identify project", "status": "failed"}

        cypher = f"""
        MATCH (p:Project)-[:HAS_BUDGET]->(b:Budget)-[:HAS_LINE]->(bl:BudgetLine)
        WHERE p.id = '{project_id}' OR p.name CONTAINS '{project_id}'
        RETURN b, bl, p
        LIMIT 100
        """

        results = self.neo4j_client.run_query(cypher)

        return {
            "exploration": "project budget",
            "project_id": project_id,
            "budget": results,
            "count": len(results),
            "status": "success",
        }

    def _explore_generic(
        self,
        action: str,
        entity_id: Optional[str],
        entity_type: Optional[str],
    ) -> Dict[str, Any]:
        """Generic relationship exploration."""
        if not entity_id or not entity_type:
            return {
                "error": "Generic exploration requires entity_id and entity_type",
                "status": "failed",
            }

        cypher = f"""
        MATCH (n:{entity_type})
        WHERE n.id = '{entity_id}'
        OPTIONAL MATCH (n)-[r]-(related)
        RETURN n, type(r) as relationship_type, related
        LIMIT 50
        """

        results = self.neo4j_client.run_query(cypher)

        return {
            "exploration": "generic relationships",
            "entity_id": entity_id,
            "entity_type": entity_type,
            "relationships": results,
            "count": len(results),
            "status": "success",
        }

    def _extract_entity_id(
        self,
        action: str,
        context: Optional[Dict],
        entity_type: str,
    ) -> Optional[str]:
        """
        Extract entity ID from action or context.

        Args:
            action: Action string
            context: Previous results
            entity_type: Type of entity to extract (contractor, project, etc.)

        Returns:
            Entity ID or name if found, None otherwise
        """
        # Try to extract from action text
        import re

        # Look for ID patterns (e.g., "PRJ-001", "CONT-001", "INV-001")
        id_pattern = r'[A-Z]{3,4}-\d{3,4}'
        id_match = re.search(id_pattern, action)
        if id_match:
            return id_match.group(0)

        # Look for entity name in quotes
        name_pattern = r'"([^"]+)"'
        name_match = re.search(name_pattern, action)
        if name_match:
            return name_match.group(1)

        # Try to extract from context (previous results)
        if context and context.get("previous_results"):
            for result in context["previous_results"]:
                if result.get("status") == "success":
                    # Look for entity_type in results
                    if "results" in result:
                        for record in result["results"]:
                            if f"{entity_type}_id" in record:
                                return record[f"{entity_type}_id"]
                            if "id" in record:
                                return record["id"]
                            if "name" in record:
                                return record["name"]

        return None
