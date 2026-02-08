import pytest
from backend.graph.client import Neo4jClient
from backend.vector.client import ChromaDBClient


@pytest.fixture
def neo4j_client():
    """Neo4j client for tests"""
    client = Neo4jClient()
    yield client
    client.close()


@pytest.fixture
def chroma_client():
    """ChromaDB client for tests"""
    return ChromaDBClient()
