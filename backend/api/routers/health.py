"""Health check endpoint."""

from datetime import datetime, timezone

import structlog
from fastapi import APIRouter

from backend.api.schemas import HealthResponse
from backend.graph.client import Neo4jClient
from backend.vector.client import ChromaDBClient

router = APIRouter(tags=["health"])
logger = structlog.get_logger()

_chroma_client = ChromaDBClient()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Check service connectivity."""
    neo4j_client = Neo4jClient()
    services_status = {
        "neo4j": neo4j_client.verify_connectivity(),
        "chromadb": _chroma_client.verify_connectivity(),
    }
    overall_status = "healthy" if all(services_status.values()) else "degraded"
    logger.info("health_check", status=overall_status, services=services_status)
    return HealthResponse(
        status=overall_status,
        services=services_status,
        timestamp=datetime.now(timezone.utc),
    )
