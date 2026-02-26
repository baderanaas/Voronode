"""
Test Neo4j date serialization fix.
"""

import sys
import os

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, project_root)

from backend.agents.orchestrator import create_multi_agent_graph

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')


def main():
    print("Testing Neo4j Date Serialization Fix")
    print("=" * 60)

    # This query should return invoices with date fields
    query = "Show me all invoices"

    print(f"\nQuery: {query}")
    print("=" * 60)

    try:
        graph = create_multi_agent_graph()

        initial_state = {
            "user_query": query,
            "conversation_history": [],
            "retry_count": 0,
        }

        config = {"configurable": {"thread_id": "test-serialization"}}

        print("\nExecuting query...")
        final_state = graph.invoke(initial_state, config)

        print(f"\n[SUCCESS] SUCCESS! No serialization error!")
        print(f"\n📍 Route: {final_state.get('route')}")
        print(f"💬 Response:\n{final_state.get('final_response', '')[:200]}...")

        if final_state.get('display_data'):
            print(f"\n📊 Data sample:")
            data = final_state['display_data']
            if 'rows' in data and len(data['rows']) > 0:
                first_row = data['rows'][0]
                print(f"  First row: {first_row}")
                # Check if date fields are strings now
                for key, value in first_row.items():
                    if 'date' in key.lower():
                        print(f"  [SUCCESS] {key}: {value} (type: {type(value).__name__})")

    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("Test complete!")


if __name__ == "__main__":
    main()
