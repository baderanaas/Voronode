"""
Test clarification vs generic_response routing.
"""

import sys
import os

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, project_root)

from backend.agents.multi_agent.orchestrator import create_multi_agent_graph

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')


def test_query(query: str, description: str):
    """Test a query and show the route and response."""
    print(f"\n{'='*60}")
    print(f"{description}")
    print(f"Query: {query}")
    print('='*60)

    graph = create_multi_agent_graph()

    initial_state = {
        "user_query": query,
        "conversation_history": [],
        "retry_count": 0,
    }

    config = {"configurable": {"thread_id": "test"}}
    final_state = graph.invoke(initial_state, config)

    route = final_state.get('route')
    response = final_state.get('final_response', 'No response')

    print(f"\n[Route] Route: {route}")
    print(f"[Response] Response:\n{response}")

    return route, response


def main():
    print("Testing Generic Response vs Clarification Routing")
    print("=" * 60)

    # Test cases
    test_cases = [
        ("Hello!", "Test 1: Generic Response (Greeting)"),
        ("What's the weather?", "Test 2: Generic Response (Out of Scope)"),
        ("Show me the invoice", "Test 3: Clarification (Ambiguous Query)"),
        ("What's the variance?", "Test 4: Clarification (Missing Context)"),
    ]

    results = []
    for query, description in test_cases:
        try:
            route, response = test_query(query, description)
            results.append((description, route, response))
        except Exception as e:
            print(f"[ERROR] Error: {e}")
            import traceback
            traceback.print_exc()

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    for desc, route, response in results:
        print(f"\n{desc}")
        print(f"  Route: {route}")
        print(f"  Response: {response[:80]}...")

        # Verify expected behavior
        if "Greeting" in desc or "Out of Scope" in desc:
            expected = "generic_response"
            if route == expected and "AI assistant for financial data analysis" in response:
                print(f"  [OK] Correct! (hardcoded message)")
            else:
                print(f"  [ERROR] Expected {expected}, got {route}")

        elif "Clarification" in desc:
            expected = "clarification"
            if route == expected and "AI assistant for financial data analysis" not in response:
                print(f"  [OK] Correct! (planner's question)")
            else:
                print(f"  [ERROR] Expected {expected}, got {route}")

    print("\n" + "="*60)
    print("[OK] Testing complete!")


if __name__ == "__main__":
    main()
