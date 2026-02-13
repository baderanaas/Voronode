"""Test script to verify Gemini API integration."""

import sys
import os

# Add backend to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from backend.services.llm_client import GeminiClient
import structlog

# Configure basic logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer()
    ]
)

def test_gemini_client():
    """Test GeminiClient for structured JSON extraction."""

    print("=" * 60)
    print("Testing Gemini 2.5 Pro Integration")
    print("=" * 60)

    try:
        # Initialize client
        print("\n1. Initializing GeminiClient...")
        client = GeminiClient()
        print(f"   [OK] Client initialized with model: {client.model}")

        # Test simple JSON extraction
        print("\n2. Testing simple JSON extraction...")
        prompt = """
        You are a planner agent. Analyze this user query and return a JSON response.

        User query: "What invoices do we have for Project Alpha?"

        Return JSON with these fields:
        - route: "execution_plan"
        - execution_mode: "one_way" or "react"
        - reasoning: why you chose this mode
        - intent: what the user wants
        """

        result = client.extract_json(prompt, temperature=0.2)

        print(f"   [OK] Response received:")
        print(f"     Route: {result.get('route')}")
        print(f"     Mode: {result.get('execution_mode')}")
        print(f"     Intent: {result.get('intent')}")
        print(f"     Reasoning: {result.get('reasoning')[:80]}...")

        # Test with higher temperature (more creative)
        print("\n3. Testing with higher temperature (0.7)...")
        prompt2 = """
        Classify this construction query:
        "Show me all overdue invoices with high risk scores"

        Return JSON:
        {
            "category": "query type",
            "complexity": "simple/medium/complex",
            "data_sources": ["list of needed data sources"],
            "requires_calculations": true/false
        }
        """

        result2 = client.extract_json(prompt2, temperature=0.7)

        print(f"   [OK] Response received:")
        print(f"     Category: {result2.get('category')}")
        print(f"     Complexity: {result2.get('complexity')}")
        print(f"     Data sources: {result2.get('data_sources')}")
        print(f"     Requires calculations: {result2.get('requires_calculations')}")

        print("\n" + "=" * 60)
        print("[SUCCESS] All tests passed! Gemini 2.5 Pro is working correctly.")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_planner_agent():
    """Test PlannerAgent with Gemini backend."""

    print("\n" + "=" * 60)
    print("Testing PlannerAgent with Gemini 2.5 Pro")
    print("=" * 60)

    try:
        from backend.agents.multi_agent.planner_agent import PlannerAgent

        print("\n1. Initializing PlannerAgent...")
        planner = PlannerAgent()
        print(f"   [OK] Planner initialized with LLM model: {planner.llm.model}")

        print("\n2. Testing query analysis...")
        result = planner.analyze(
            user_message="Show me all invoices for Acme Construction",
            history=[]
        )

        print(f"   [OK] Analysis complete:")
        print(f"     Route: {result.get('route')}")
        print(f"     Execution mode: {result.get('execution_mode')}")
        print(f"     Reasoning: {result.get('reasoning', 'N/A')[:100]}...")

        print("\n" + "=" * 60)
        print("[SUCCESS] PlannerAgent works with Gemini 2.5 Pro!")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Test 1: GeminiClient directly
    if test_gemini_client():
        # Test 2: PlannerAgent integration
        test_planner_agent()
