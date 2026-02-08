from backend.graph.schema import generate_schema_cypher, NODES, RELATIONSHIPS


def test_schema_generation():
    """Test Cypher schema generation"""
    cypher = generate_schema_cypher()

    assert "CREATE CONSTRAINT" in cypher
    assert "CREATE INDEX" in cypher
    assert "Project_id_unique" in cypher


def test_node_definitions():
    """Verify all required nodes are defined"""
    node_labels = [node.label for node in NODES]

    required = ["Project", "Contractor", "Contract", "Invoice", "BudgetLine", "RiskFactor"]
    for label in required:
        assert label in node_labels


def test_relationship_definitions():
    """Verify key relationships exist"""
    rel_types = [(r.from_node, r.rel_type, r.to_node) for r in RELATIONSHIPS]

    assert ("Invoice", "BILLED_AGAINST", "Contract") in rel_types
    assert ("Contract", "BELONGS_TO", "Project") in rel_types
    assert ("Invoice", "HAS_RISK", "RiskFactor") in rel_types


def test_neo4j_connection(neo4j_client):
    """Test database connectivity"""
    assert neo4j_client.verify_connectivity() is True
