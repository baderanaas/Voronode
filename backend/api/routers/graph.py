"""Graph database query endpoints."""

import re
from backend.core.logging import get_logger
from fastapi import APIRouter, Depends, HTTPException

from backend.auth.dependencies import get_current_user
from backend.core.cache import TTLCache
from backend.graph.client import Neo4jClient

router = APIRouter(prefix="/graph", tags=["graph"])

_stats_cache = TTLCache(ttl=60)
logger = get_logger(__name__)

# Labels whose nodes carry a user_id property (mirrors CypherQueryTool)
_USER_SCOPED_LABELS = {"Invoice", "Contract", "Budget", "BudgetLine"}


def _inject_user_filter(cypher: str, user_id: str) -> tuple[str, dict]:
    """
    Inject a parameterised user_id WHERE clause into a Cypher query so that
    the graph query endpoint always operates within the caller's data scope.

    Mirrors the logic in CypherQueryTool._inject_user_filter.
    """
    params: dict = {}

    aliases = {
        m.group(1)
        for m in re.finditer(r"\((\w+):(\w+)", cypher)
        if m.group(2) in _USER_SCOPED_LABELS
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


@router.get("/stats")
async def get_graph_stats(current_user: dict = Depends(get_current_user)):
    """Get Neo4j graph database statistics scoped to the current user."""
    user_id = current_user["id"]

    cached = _stats_cache.get(user_id)
    if cached is not None:
        logger.debug("graph_stats_cache_hit", user_id=user_id)
        return cached

    logger.debug("graph_stats_requested", user_id=user_id)
    try:
        neo4j_client = Neo4jClient()

        # Count user-scoped nodes per label
        node_results = neo4j_client.run_query(
            """
            MATCH (n)
            WHERE (n:Invoice OR n:Contract OR n:Budget OR n:BudgetLine)
              AND n.user_id = $user_id
            RETURN labels(n)[0] AS label, count(*) AS count
            """,
            parameters={"user_id": user_id},
        )

        # Count nodes not requiring isolation (Contractor, Project, LineItem)
        unscoped_results = neo4j_client.run_query(
            """
            MATCH (n)
            WHERE n:Contractor OR n:Project OR n:LineItem
            RETURN labels(n)[0] AS label, count(*) AS count
            """
        )

        # Count relationships touching the user's Invoice nodes
        rel_results = neo4j_client.run_query(
            """
            MATCH (i:Invoice)-[r]-()
            WHERE i.user_id = $user_id
            RETURN count(r) AS count
            """,
            parameters={"user_id": user_id},
        )

        all_results = node_results + unscoped_results
        stats = {
            "total_nodes": sum(r["count"] for r in node_results),
            "total_relationships": rel_results[0]["count"] if rel_results else 0,
        }
        for result in all_results:
            label = result["label"]
            if label:
                stats[f"{label.lower()}_count"] = result["count"]

        _stats_cache.set(user_id, stats)
        return stats
    except Exception as e:
        logger.error("graph_stats_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get graph stats: {e}")


@router.post("/query")
async def query_graph(query: dict, current_user: dict = Depends(get_current_user)):
    """
    Execute a Cypher query on Neo4j.

    User_id filtering is injected automatically for user-scoped node labels
    (Invoice, Contract, Budget, BudgetLine) so results are always isolated
    to the caller's data.
    """
    cypher_query = query.get("query")
    if not cypher_query:
        raise HTTPException(status_code=400, detail="Missing 'query' in request body")

    user_id = current_user["id"]
    logger.debug("graph_query_requested", query=cypher_query[:100], user_id=user_id)

    try:
        cypher_query, params = _inject_user_filter(cypher_query, user_id)
        neo4j_client = Neo4jClient()
        results = neo4j_client.run_query(cypher_query, parameters=params)
        logger.debug("graph_query_executed", record_count=len(results))
        return {"records": results, "count": len(results)}
    except Exception as e:
        logger.error("graph_query_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Query execution failed: {e}")
