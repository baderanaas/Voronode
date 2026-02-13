"""
Quick interactive test for Multi-Agent Orchestrator.

Run: python test_agent.py
"""

import sys
from backend.agents.multi_agent.orchestrator import create_multi_agent_graph

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')


def test_query(query: str, thread_id: str = "test"):
    """Test a single query through the orchestrator."""
    print(f"\n{'='*60}")
    print(f"Query: {query}")
    print('='*60)

    # Create graph
    graph = create_multi_agent_graph()

    # Initial state
    initial_state = {
        "user_query": query,
        "conversation_history": [],
        "retry_count": 0,
    }

    # Execute with thread config
    config = {"configurable": {"thread_id": thread_id}}
    final_state = graph.invoke(initial_state, config)

    # Print results
    print(f"\n📍 Route: {final_state.get('route')}")
    if final_state.get('execution_mode'):
        print(f"⚙️  Mode: {final_state.get('execution_mode')}")
    if final_state.get('retry_count', 0) > 0:
        print(f"🔄 Retries: {final_state.get('retry_count')}")

    print(f"\n💬 Response:")
    print(final_state.get('final_response', 'No response'))

    print(f"\n📊 Display Format: {final_state.get('display_format', 'text')}")

    if final_state.get('display_data'):
        print(f"📈 Data: {final_state['display_data']}")

    return final_state

def main():
    """Run test queries."""
    print("Multi-Agent Orchestrator Test")
    print("=" * 60)

    # Test different query types
    test_cases = [
        # Generic response
        "Hello!",

        # Out of scope
        "What's the weather today?",

        # Simple execution (would need tools implemented)
        # "Show me all invoices",

        # Complex query (would need tools implemented)
        # "Which contractor has the highest variance?",
    ]

    for query in test_cases:
        try:
            test_query(query)
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "="*60)
    print("✅ Testing complete!")


if __name__ == "__main__":
    main()
