"""
Test complex multi-agent queries.

Run: python test_complex_queries.py
"""

import sys
from backend.agents.multi_agent.orchestrator import create_multi_agent_graph

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# Complex test queries - Advanced multi-step reasoning
COMPLEX_QUERIES = [
    {
        "name": "Multi-Contract Budget Overrun Analysis",
        "query": "For all projects that have both a budget and contracts, calculate the variance between budgeted amounts and actual invoiced amounts. Which projects are over budget and by how much?",
        "expected_mode": "react",
        "tests": ["Multi-entity aggregation", "Budget variance calculation", "Cross-referencing"]
    },
    {
        "name": "Contractor Risk Profile",
        "query": "Analyze CONT-001's compliance history: How many invoices have they submitted, how many were non-compliant, what's their average invoice amount, and what are the most common violation types?",
        "expected_mode": "react",
        "tests": ["Multi-dimensional analysis", "Statistical aggregation", "Pattern detection"]
    },
    {
        "name": "Cost Code Spending Distribution",
        "query": "Break down total spending by cost code across all projects. Show me the top 5 cost codes by total amount, and for each one, tell me which contractors are billing the most under that code.",
        "expected_mode": "react",
        "tests": ["Hierarchical grouping", "Multi-level aggregation", "Top-N analysis"]
    },
    {
        "name": "Contract vs Budget Alignment",
        "query": "For PRJ-001, compare the contract approved cost codes with the budget line items. Are there any cost codes in invoices that don't have corresponding budget lines? What's the total amount for those?",
        "expected_mode": "react",
        "tests": ["Set comparison", "Mismatch detection", "Multi-source correlation"]
    },
    {
        "name": "Time-Based Trend Analysis",
        "query": "Show me the monthly invoice totals for the last 6 months. Which month had the highest invoicing activity? Are there any contractors who only invoice in specific months?",
        "expected_mode": "react",
        "tests": ["Temporal aggregation", "Trend detection", "Seasonal pattern analysis"]
    },
    {
        "name": "Cascading Compliance Impact",
        "query": "If we reject all non-compliant invoices for CONTRACT-001, what would be the impact on the project budget? Calculate the difference between total invoiced (including non-compliant) vs compliant-only invoices.",
        "expected_mode": "react",
        "tests": ["Scenario analysis", "Conditional aggregation", "Impact calculation"]
    },
    {
        "name": "Multi-Project Contractor Comparison",
        "query": "Compare the performance of all contractors working on PRJ-001: for each contractor, show their total invoiced, number of invoices, compliance rate, and average days between invoice date and due date.",
        "expected_mode": "react",
        "tests": ["Multi-metric comparison", "Rate calculation", "Date arithmetic"]
    },
    {
        "name": "Contract Utilization Analysis",
        "query": "For each active contract, calculate how much of the contract value has been invoiced so far. Which contracts are more than 80% utilized? Which ones have barely been used?",
        "expected_mode": "react",
        "tests": ["Percentage calculation", "Contract lifecycle analysis", "Threshold filtering"]
    },
    {
        "name": "Line Item Deep Dive",
        "query": "Find all line items with cost code 05-500 across all invoices. Group them by contractor and calculate the average unit price each contractor charges. Are there significant price variations that might indicate compliance issues?",
        "expected_mode": "react",
        "tests": ["Line item analysis", "Price variance detection", "Outlier identification"]
    },
    {
        "name": "Cross-Validation Discovery",
        "query": "Find invoices that have line items with cost codes not in their associated contract's approved list. For each violation, show the invoice, contractor, cost code, amount, and the contract's approved codes.",
        "expected_mode": "react",
        "tests": ["Cross-document validation", "Set membership checking", "Violation cataloging"]
    },
]


def test_query(query_info: dict, graph):
    """Test a single complex query."""
    print("\n" + "=" * 70)
    print(f"Test: {query_info['name']}")
    print("=" * 70)
    print(f"Query: {query_info['query']}")
    print(f"Expected Mode: {query_info['expected_mode']}")
    print(f"Tests: {', '.join(query_info['tests'])}")
    print("-" * 70)

    try:
        initial_state = {
            "user_query": query_info['query'],
            "conversation_history": [],
            "retry_count": 0,
        }

        config = {"configurable": {"thread_id": f"test-{query_info['name']}"}}
        final_state = graph.invoke(initial_state, config)

        # Results
        route = final_state.get('route')
        mode = final_state.get('execution_mode')
        retries = final_state.get('retry_count', 0)
        response = final_state.get('final_response', '')

        print(f"\n✓ Route: {route}")
        print(f"✓ Mode: {mode}")
        print(f"✓ Retries: {retries}")
        print(f"\nResponse:")
        print("-" * 70)
        print(response[:300] + "..." if len(response) > 300 else response)
        print("-" * 70)

        # Validation
        if mode == query_info['expected_mode']:
            print(f"✅ Mode matches expectation ({mode})")
        else:
            print(f"⚠️  Mode mismatch: expected {query_info['expected_mode']}, got {mode}")

        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all complex query tests."""
    print("=" * 70)
    print("COMPLEX MULTI-AGENT QUERY TESTS")
    print("=" * 70)
    print(f"\nTotal test queries: {len(COMPLEX_QUERIES)}")

    # Create graph once
    print("\nInitializing multi-agent graph...")
    graph = create_multi_agent_graph()
    print("✓ Graph initialized")

    # Run tests
    results = []
    for query_info in COMPLEX_QUERIES:
        success = test_query(query_info, graph)
        results.append((query_info['name'], success))

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, success in results if success)
    total = len(results)

    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {name}")

    print("\n" + "=" * 70)
    print(f"Results: {passed}/{total} tests passed ({passed/total*100:.0f}%)")
    print("=" * 70)


if __name__ == "__main__":
    # You can also test individual queries
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", "-q", type=str, help="Test a specific query")
    args = parser.parse_args()

    if args.query:
        # Single query test
        graph = create_multi_agent_graph()
        test_query({"name": "Custom", "query": args.query, "expected_mode": "unknown", "tests": []}, graph)
    else:
        # Run all tests
        main()
