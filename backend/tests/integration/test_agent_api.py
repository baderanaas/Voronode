"""
Test Multi-Agent Orchestrator via API endpoint.

Usage:
1. Start FastAPI server: uvicorn backend.main:app --reload
2. Run this script: python test_agent_api.py
"""

import requests
import json

API_URL = "http://localhost:8000/api/chat"


def test_chat(query: str, session_id: str = "test-session"):
    """Send a chat query to the API."""
    print(f"\n{'='*60}")
    print(f"Query: {query}")
    print('='*60)

    payload = {
        "message": query,
        "session_id": session_id,
    }

    try:
        response = requests.post(API_URL, json=payload, timeout=30)
        response.raise_for_status()

        data = response.json()

        print(f"\n[SUCCESS] Status: {response.status_code}")
        print(f"💬 Response: {data.get('response', 'No response')}")
        print(f"📊 Format: {data.get('display_format', 'text')}")

        if data.get('data'):
            print(f"📈 Data: {json.dumps(data['data'], indent=2)}")

        if data.get('metadata'):
            print(f"ℹ️  Metadata: {json.dumps(data['metadata'], indent=2)}")

        return data

    except requests.exceptions.ConnectionError:
        print("[ERROR] Error: Could not connect to API server.")
        print("   Make sure the FastAPI server is running:")
        print("   uvicorn backend.main:app --reload")
    except requests.exceptions.Timeout:
        print("[ERROR] Error: Request timed out")
    except Exception as e:
        print(f"[ERROR] Error: {e}")


def main():
    """Test the chat API."""
    print("Multi-Agent Chat API Test")
    print("="*60)

    # Test queries
    test_cases = [
        "Hello!",
        "What can you help me with?",
        "What's the weather?",  # Out of scope
        # Add more test cases as needed
    ]

    for query in test_cases:
        test_chat(query)

    print("\n" + "="*60)
    print("[SUCCESS] All tests completed!")


if __name__ == "__main__":
    main()
