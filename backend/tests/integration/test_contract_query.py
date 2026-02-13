"""
Test the CONTRACT-001 compliance query with the fixed schema.
"""

import sys
from backend.agents.multi_agent.orchestrator import create_multi_agent_graph

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

print("=" * 60)
print("Testing CONTRACT-001 Invoice Compliance Check")
print("=" * 60)

query = "Can you check if the invoices match the specifications made in CONTRACT-001?"

print(f"\nQuery: {query}\n")

try:
    graph = create_multi_agent_graph()

    initial_state = {
        "user_query": query,
        "conversation_history": [],
        "retry_count": 0,
    }

    config = {"configurable": {"thread_id": "test-contract"}}

    print("Executing query through multi-agent system...")
    print("-" * 60)

    final_state = graph.invoke(initial_state, config)

    print(f"\n📍 Route: {final_state.get('route')}")
    print(f"⚙️  Execution Mode: {final_state.get('execution_mode')}")
    print(f"🔄 Retries: {final_state.get('retry_count', 0)}")

    print(f"\n💬 Response:")
    print("-" * 60)
    print(final_state.get('final_response', 'No response'))
    print("-" * 60)

    print(f"\n📊 Display Format: {final_state.get('display_format')}")

    if final_state.get('display_data'):
        data = final_state['display_data']
        if 'rows' in data:
            print(f"\n📈 Data ({len(data['rows'])} rows):")
            for i, row in enumerate(data['rows'][:3], 1):  # Show first 3
                print(f"  {i}. {row}")

    print("\n" + "=" * 60)
    print("✅ Test complete!")

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
