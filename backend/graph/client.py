from neo4j import GraphDatabase
from neo4j.graph import Node, Relationship
from typing import List, Dict, Any, Optional
from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)


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

    def _serialize_neo4j_value(self, value):
        """Convert Neo4j types to JSON-serializable types."""
        if isinstance(value, Node):
            # Neo4j Node - include both element_id and properties
            props = dict(value)
            return {
                "_element_id": value.element_id,  # Neo4j internal ID
                "_labels": list(value.labels),  # Node labels
                **props,  # Node properties (includes 'id' field)
            }
        elif isinstance(value, Relationship):
            # Neo4j Relationship
            props = dict(value)
            return {
                "_relationship": True,
                "type": value.type,
                "start": value.start_node.element_id,
                "end": value.end_node.element_id,
                **props,  # Relationship properties
            }
        elif isinstance(value, list):
            return [self._serialize_neo4j_value(item) for item in value]
        elif isinstance(value, dict):
            return {k: self._serialize_neo4j_value(v) for k, v in value.items()}
        else:
            return value

    def run_query(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict]:
        """Execute Cypher query and return results with Neo4j objects serialized."""
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            records = []
            for record in result:
                # Serialize each value in the record
                serialized_record = {}
                for key in record.keys():
                    value = record[key]
                    serialized_record[key] = self._serialize_neo4j_value(value)
                records.append(serialized_record)
            return records

    def run_migration(self, cypher_file_path: str):
        """Execute migration script"""
        with open(cypher_file_path, 'r') as f:
            queries = f.read().split(';')

        with self.driver.session() as session:
            for query in queries:
                query = query.strip()
                if query:
                    session.run(query)
