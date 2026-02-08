from typing import Dict, List
from dataclasses import dataclass


@dataclass
class NodeDefinition:
    label: str
    properties: List[str]
    unique_constraints: List[str]
    indexes: List[str]


@dataclass
class RelationshipDefinition:
    from_node: str
    rel_type: str
    to_node: str
    properties: List[str]


# Node Definitions
NODES: List[NodeDefinition] = [
    NodeDefinition(
        label="Project",
        properties=["id", "name", "budget", "start_date", "end_date", "status"],
        unique_constraints=["id"],
        indexes=["name", "status"]
    ),
    NodeDefinition(
        label="Contractor",
        properties=["id", "name", "license_number", "rating"],
        unique_constraints=["id", "license_number"],
        indexes=["name"]
    ),
    NodeDefinition(
        label="Contract",
        properties=["id", "value", "retention_rate", "start_date", "end_date", "terms"],
        unique_constraints=["id"],
        indexes=["start_date"]
    ),
    NodeDefinition(
        label="Invoice",
        properties=["id", "invoice_number", "date", "amount", "status", "due_date"],
        unique_constraints=["id", "invoice_number"],
        indexes=["date", "status"]
    ),
    NodeDefinition(
        label="LineItem",
        properties=["id", "description", "quantity", "unit_price", "total", "cost_code"],
        unique_constraints=["id"],
        indexes=["cost_code"]
    ),
    NodeDefinition(
        label="BudgetLine",
        properties=["id", "cost_code", "description", "allocated", "spent", "remaining"],
        unique_constraints=["id"],
        indexes=["cost_code"]
    ),
    NodeDefinition(
        label="RiskFactor",
        properties=["id", "type", "severity", "description", "detected_date", "status"],
        unique_constraints=["id"],
        indexes=["severity", "status"]
    ),
]

# Relationship Definitions
RELATIONSHIPS: List[RelationshipDefinition] = [
    RelationshipDefinition("Project", "HAS_BUDGET", "BudgetLine", []),
    RelationshipDefinition("Contractor", "HAS_CONTRACT", "Contract", ["signed_date"]),
    RelationshipDefinition("Contract", "BELONGS_TO", "Project", []),
    RelationshipDefinition("Invoice", "BILLED_AGAINST", "Contract", []),
    RelationshipDefinition("Invoice", "CONTAINS_ITEM", "LineItem", ["line_number"]),
    RelationshipDefinition("LineItem", "MAPS_TO", "BudgetLine", ["variance"]),
    RelationshipDefinition("Invoice", "HAS_RISK", "RiskFactor", ["confidence_score"]),
    RelationshipDefinition("Project", "HAS_RISK", "RiskFactor", []),
]


def generate_schema_cypher() -> str:
    """Generate Cypher script to create schema"""
    queries = []

    # Create constraints (also creates indexes automatically)
    for node in NODES:
        for constraint_prop in node.unique_constraints:
            queries.append(
                f"CREATE CONSTRAINT {node.label}_{constraint_prop}_unique IF NOT EXISTS "
                f"FOR (n:{node.label}) REQUIRE n.{constraint_prop} IS UNIQUE;"
            )

    # Create additional indexes
    for node in NODES:
        for index_prop in node.indexes:
            queries.append(
                f"CREATE INDEX {node.label}_{index_prop}_idx IF NOT EXISTS "
                f"FOR (n:{node.label}) ON (n.{index_prop});"
            )

    return "\n".join(queries)
