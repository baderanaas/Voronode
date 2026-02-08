from neo4j import GraphDatabase
from typing import List, Dict, Any, Optional
from backend.core.config import settings
import structlog

logger = structlog.get_logger()


class Neo4jClient:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password)
        )

    def close(self):
        self.driver.close()

    def verify_connectivity(self) -> bool:
        """Test connection to Neo4j"""
        try:
            with self.driver.session() as session:
                result = session.run("RETURN 1 as num")
                return result.single()["num"] == 1
        except Exception as e:
            logger.error("neo4j_connection_failed", error=str(e))
            return False

    def run_query(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict]:
        """Execute Cypher query and return results"""
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

    def run_migration(self, cypher_file_path: str):
        """Execute migration script"""
        with open(cypher_file_path, 'r') as f:
            queries = f.read().split(';')

        with self.driver.session() as session:
            for query in queries:
                query = query.strip()
                if query:
                    session.run(query)
                    logger.info("migration_query_executed", query=query[:100])
