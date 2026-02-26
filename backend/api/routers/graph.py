"""Graph database query endpoints."""

import structlog
from fastapi import APIRouter, HTTPException

from backend.graph.client import Neo4jClient

router = APIRouter(prefix="/graph", tags=["graph"])
logger = structlog.get_logger()


@router.get("/stats")
async def get_graph_stats():
    """Get Neo4j graph database statistics."""
    logger.info("graph_stats_requested")
    try:
        neo4j_client = Neo4jClient()
        node_results = neo4j_client.run_query(
            "MATCH (n) RETURN labels(n)[0] as label, count(*) as count"
        )
        rel_results = neo4j_client.run_query(
            "MATCH ()-[r]->() RETURN count(r) as count"
        )
        stats = {
            "total_nodes": sum(r["count"] for r in node_results),
            "total_relationships": rel_results[0]["count"] if rel_results else 0,
        }
        for result in node_results:
            stats[f"{result['label'].lower()}_count"] = result["count"]
        logger.info("graph_stats_retrieved", stats=stats)
        return stats
    except Exception as e:
        logger.error("graph_stats_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get graph stats: {e}")


@router.post("/query")
async def query_graph(query: dict):
    """Execute a custom Cypher query on Neo4j."""
    cypher_query = query.get("query")
    if not cypher_query:
        raise HTTPException(status_code=400, detail="Missing 'query' in request body")
    logger.info("graph_query_requested", query=cypher_query[:100])
    try:
        neo4j_client = Neo4jClient()
        results = neo4j_client.run_query(cypher_query)
        logger.info("graph_query_executed", record_count=len(results))
        return {"records": results, "count": len(results)}
    except Exception as e:
        logger.error("graph_query_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Query execution failed: {e}")
