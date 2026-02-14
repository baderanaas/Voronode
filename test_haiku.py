from backend.tools.cypher_query_tool import CypherQueryTool

# Initialize the tool (will use Haiku now)
tool = CypherQueryTool()

# Define complex test queries
test_queries = [
    {
        "name": "Simple Filter - High Value Invoices",
        "query": "Show me all invoices over $50,000",
        "action": "Find all invoices where amount is greater than 50000",
    },
    {
        "name": "Aggregation - Total by Contractor",
        "query": "What's the total invoice amount per contractor?",
        "action": "Calculate the total invoice amount for each contractor, sorted by highest total",
    },
    {
        "name": "Budget Variance Analysis",
        "query": "Which projects are over budget?",
        "action": "Find all projects with their budget, total invoiced amount, and variance. Show which are over budget.",
    },
    {
        "name": "Multi-hop - Contractor Performance",
        "query": "Find all line items from contractor CONT-001 on project PRJ-001",
        "action": "Get all line items from invoices submitted by contractor CONT-001 for project PRJ-001",
    },
    {
        "name": "Complex Aggregation - Cost Code Analysis",
        "query": "What are the top 5 cost codes by spending?",
        "action": "Find the top 5 cost codes by total spending across all line items",
    },
    {
        "name": "Date Range Filter",
        "query": "Show invoices from January 2025",
        "action": "Find all invoices with dates between 2025-01-01 and 2025-01-31",
    },
    {
        "name": "Contract Compliance Check",
        "query": "Which invoices don't have associated contracts?",
        "action": "Find all invoices that don't have a FOR_CONTRACT relationship",
    },
]

print("\n" + "="*80)
print("CLAUDE HAIKU 4.5 - CYPHER QUERY GENERATION TEST SUITE")
print("="*80 + "\n")

results_summary = []

for i, test in enumerate(test_queries, 1):
    print(f"\n{'─'*80}")
    print(f"TEST {i}/{len(test_queries)}: {test['name']}")
    print(f"{'─'*80}")
    print(f"Query: {test['query']}")
    print(f"Action: {test['action']}")

    result = tool.run(
        query=test["query"],
        action=test["action"],
    )

    status = result.get("status")
    cypher = result.get("cypher_query")
    count = result.get("count", 0)
    error = result.get("error", "")

    print(f"\n✓ Status: {status.upper()}")
    print(f"✓ Generated Cypher:")
    print(f"  {cypher}")

    if status == "success":
        print(f"✓ Results Count: {count}")
        results_summary.append({"test": test['name'], "status": "✓ PASS", "count": count})
    else:
        print(f"✗ Error: {error[:200]}...")
        results_summary.append({"test": test['name'], "status": "✗ FAIL", "error": error[:100]})

# Summary
print(f"\n\n{'='*80}")
print("TEST SUMMARY")
print(f"{'='*80}\n")

passed = sum(1 for r in results_summary if "PASS" in r["status"])
failed = sum(1 for r in results_summary if "FAIL" in r["status"])

for i, r in enumerate(results_summary, 1):
    print(f"{i}. {r['status']} - {r['test']}")
    if "FAIL" in r["status"]:
        print(f"   Error: {r.get('error', 'Unknown')}")

print(f"\n{'─'*80}")
print(f"Total: {len(test_queries)} | Passed: {passed} | Failed: {failed}")
print(f"Success Rate: {(passed/len(test_queries)*100):.1f}%")
print(f"{'='*80}\n")
