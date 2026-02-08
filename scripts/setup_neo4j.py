"""Initialize Neo4j graph schema"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.graph.client import Neo4jClient
from backend.core.config import settings
import structlog

logger = structlog.get_logger()


def main():
    logger.info("initializing_neo4j_schema")

    client = Neo4jClient()

    # Verify connectivity
    if not client.verify_connectivity():
        logger.error("cannot_connect_to_neo4j")
        sys.exit(1)

    logger.info("neo4j_connected")

    # Run migration
    migration_path = (
        Path(__file__).parent.parent / "backend/graph/migrations/v1_initial.cypher"
    )
    client.run_migration(str(migration_path))

    logger.info("schema_created_successfully")

    # Verify constraints were created
    constraints = client.run_query("SHOW CONSTRAINTS")
    logger.info("constraints_created", count=len(constraints))

    client.close()


if __name__ == "__main__":
    main()
