"""
Integration tests for Claude Haiku 4.5 Cypher query generation.

Tests the AnthropicClient + CypherQueryTool integration with complex queries.
"""

import pytest
from backend.agents.tools.cypher_query_tool import CypherQueryTool


class TestCypherHaikuIntegration:
    """Test suite for Claude Haiku Cypher generation."""

    @pytest.fixture
    def tool(self):
        """Initialize CypherQueryTool with Haiku."""
        return CypherQueryTool()

    def test_simple_filter_high_value_invoices(self, tool):
        """Test simple WHERE clause filtering."""
        result = tool.run(
            query="Show me all invoices over $50,000",
            action="Find all invoices where amount is greater than 50000",
        )

        assert result["status"] == "success"
        assert "MATCH" in result["cypher_query"]
        assert "WHERE" in result["cypher_query"]
        assert "i.amount > 50000" in result["cypher_query"]
        assert "GROUP BY" not in result["cypher_query"]  # Should not use SQL syntax

    def test_aggregation_total_by_contractor(self, tool):
        """Test aggregation without GROUP BY (Cypher implicit grouping)."""
        result = tool.run(
            query="What's the total invoice amount per contractor?",
            action="Calculate the total invoice amount for each contractor, sorted by highest total",
        )

        assert result["status"] == "success"
        assert "SUM" in result["cypher_query"]
        assert "GROUP BY" not in result["cypher_query"]  # Critical: no SQL GROUP BY
        assert "ORDER BY" in result["cypher_query"]

    def test_budget_variance_analysis(self, tool):
        """Test complex multi-hop with calculations."""
        result = tool.run(
            query="Which projects are over budget?",
            action="Find all projects with their budget, total invoiced amount, and variance. Show which are over budget.",
        )

        assert result["status"] == "success"
        cypher = result["cypher_query"]
        assert "MATCH" in cypher
        assert "HAS_BUDGET" in cypher or "FOR_PROJECT" in cypher
        assert "SUM" in cypher
        assert "GROUP BY" not in cypher  # Critical: Cypher has no GROUP BY

    def test_multi_hop_contractor_performance(self, tool):
        """Test multi-hop relationship traversal."""
        result = tool.run(
            query="Find all line items from contractor CONT-001 on project PRJ-001",
            action="Get all line items from invoices submitted by contractor CONT-001 for project PRJ-001",
        )

        assert result["status"] == "success"
        cypher = result["cypher_query"]
        assert "MATCH" in cypher
        assert "LineItem" in cypher or "HAS_ITEM" in cypher
        assert "CONT-001" in cypher
        assert "PRJ-001" in cypher

    def test_complex_aggregation_cost_code_analysis(self, tool):
        """Test TOP N aggregation with ORDER BY."""
        result = tool.run(
            query="What are the top 5 cost codes by spending?",
            action="Find the top 5 cost codes by total spending across all line items",
        )

        assert result["status"] == "success"
        cypher = result["cypher_query"]
        assert "SUM" in cypher or "sum" in cypher.lower()
        assert "ORDER BY" in cypher
        assert "LIMIT 5" in cypher
        assert "GROUP BY" not in cypher

    def test_date_range_filter(self, tool):
        """Test date() function usage."""
        result = tool.run(
            query="Show invoices from January 2025",
            action="Find all invoices with dates between 2025-01-01 and 2025-01-31",
        )

        assert result["status"] == "success"
        cypher = result["cypher_query"]
        assert "date(" in cypher.lower()
        assert "2025-01" in cypher

    def test_optional_relationship_contract_compliance(self, tool):
        """Test OPTIONAL MATCH for missing relationships."""
        result = tool.run(
            query="Which invoices don't have associated contracts?",
            action="Find all invoices that don't have a FOR_CONTRACT relationship",
        )

        assert result["status"] == "success"
        cypher = result["cypher_query"]
        # Should use OPTIONAL MATCH or WHERE NOT EXISTS
        assert ("OPTIONAL MATCH" in cypher or "NOT EXISTS" in cypher or
                "WHERE NOT" in cypher or "IS NULL" in cypher)

    def test_no_sql_syntax_in_queries(self, tool):
        """Ensure no SQL syntax leaks into Cypher queries."""
        test_cases = [
            ("Aggregate by project", "Sum all invoices grouped by project"),
            ("Count invoices", "Count invoices per contractor"),
            ("Average amounts", "Calculate average invoice amount per project"),
        ]

        for query, action in test_cases:
            result = tool.run(query=query, action=action)

            # Require that a Cypher query was generated (regardless of execution success)
            cypher = result.get("cypher_query", "")
            assert cypher, f"No Cypher query generated for action: {action}"

            # Should NOT contain SQL-specific syntax
            assert "GROUP BY" not in cypher, f"Query contains GROUP BY: {cypher}"
            assert "HAVING" not in cypher, f"Query contains HAVING: {cypher}"
            assert "SELECT" not in cypher, f"Query contains SELECT: {cypher}"
            assert "FROM" not in cypher, f"Query contains FROM: {cypher}"
            assert "JOIN" not in cypher, f"Query contains JOIN: {cypher}"


class TestCypherSyntaxValidation:
    """Test Cypher syntax correctness."""

    @pytest.fixture
    def tool(self):
        """Initialize CypherQueryTool with Haiku."""
        return CypherQueryTool()

    def test_proper_statement_order(self, tool):
        """Test that MATCH/WITH/RETURN are in correct order."""
        result = tool.run(
            query="Calculate total spending",
            action="Calculate total invoice amount across all invoices",
        )

        cypher = result["cypher_query"]

        # Find positions of key statements
        match_pos = cypher.find("MATCH")
        return_pos = cypher.find("RETURN")
        with_pos = cypher.find("WITH")

        # MATCH should come before RETURN
        if match_pos != -1 and return_pos != -1:
            assert match_pos < return_pos, "MATCH should come before RETURN"

        # If WITH exists, it should be between MATCH and RETURN
        if with_pos != -1:
            assert match_pos < with_pos < return_pos, "WITH should be between MATCH and RETURN"

    def test_limit_clause_present(self, tool):
        """Test that queries include LIMIT to prevent huge result sets."""
        result = tool.run(
            query="Show all invoices",
            action="Find all invoices in the database",
        )

        cypher = result["cypher_query"]
        assert "LIMIT" in cypher, "Query should include LIMIT clause"


if __name__ == "__main__":
    # Allow running as script for quick testing
    pytest.main([__file__, "-v", "--tb=short"])
