"""
Example: Using the Streaming Chat Endpoint

This script demonstrates how to consume the streaming chat endpoint
using Server-Sent Events (SSE).

Usage:
    python examples/chat_stream_example.py
"""

import requests
import json
import time


def stream_chat_request(message: str, base_url: str = "http://localhost:8000"):
    """
    Send a chat request and consume the streaming response.

    Args:
        message: User's question
        base_url: API base URL

    Yields:
        Event dictionaries from the stream
    """
    url = f"{base_url}/api/chat/stream"

    payload = {
        "message": message,
        "conversation_history": [],
        "session_id": f"example-{int(time.time())}",
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }

    print(f"📤 Sending request: {message}")
    print(f"🔗 URL: {url}\n")

    response = requests.post(url, json=payload, headers=headers, stream=True)

    if response.status_code != 200:
        print(f"❌ Error: {response.status_code}")
        print(response.text)
        return

    print("📡 Streaming events:\n")
    print("-" * 80)

    for line in response.iter_lines():
        if not line:
            continue

        # Decode line
        line = line.decode("utf-8")

        # SSE format: "data: {json}\n\n"
        if line.startswith("data: "):
            event_json = line[6:]  # Remove "data: " prefix

            try:
                event = json.loads(event_json)
                yield event

                # Pretty print event
                print(f"\n🔔 Event: {event['event']}")
                print(f"   Timestamp: {event.get('timestamp', 'N/A')}")

                if event["event"] == "planner":
                    data = event["data"]
                    print(f"   Route: {data.get('route')}")
                    print(f"   Execution Mode: {data.get('execution_mode')}")
                    print(f"   Retry Count: {data.get('retry_count', 0)}")

                elif event["event"] == "executor":
                    data = event["data"]
                    print(f"   Mode: {data.get('mode')}")
                    print(f"   Status: {data.get('status')}")

                    if data.get("mode") == "one_way":
                        results = data.get("results", [])
                        print(f"   Results: {len(results)} steps completed")
                        for i, result in enumerate(results, 1):
                            print(f"     Step {i}: {result.get('tool')} - {result.get('status')}")
                    else:
                        print(f"   Current Step: {data.get('current_step')}")
                        step_result = data.get("step_result", {})
                        print(f"   Tool: {step_result.get('tool')} - {step_result.get('status')}")

                elif event["event"] == "planner_react":
                    data = event["data"]
                    print(f"   Continue: {data.get('continue')}")
                    if data.get("continue"):
                        next_step = data.get("next_step", {})
                        print(f"   Next Tool: {next_step.get('tool')}")
                        print(f"   Next Action: {next_step.get('action', '')[:50]}...")

                elif event["event"] == "validator":
                    data = event["data"]
                    print(f"   Valid: {data.get('valid')}")
                    if not data.get("valid"):
                        print(f"   Issues: {data.get('issues')}")
                        print(f"   Retry Suggestion: {data.get('retry_suggestion')}")

                elif event["event"] == "responder":
                    data = event["data"]
                    print(f"   Display Format: {data.get('display_format')}")
                    response_text = data.get("response", "")
                    print(f"   Response Preview: {response_text[:100]}...")

                elif event["event"] == "complete":
                    data = event["data"]
                    print(f"   Processing Time: {data.get('processing_time_seconds')}s")
                    print("\n✅ Processing complete!")

                elif event["event"] == "error":
                    data = event["data"]
                    print(f"   Error: {data.get('error')}")
                    print("\n❌ Processing failed!")

            except json.JSONDecodeError as e:
                print(f"⚠️  Failed to parse event JSON: {e}")
                print(f"   Raw line: {line}")

    print("-" * 80)


def main():
    """Run example queries."""
    examples = [
        "What is the total value of all projects?",
        "Show me the top 3 most expensive invoices",
        "Calculate the budget variance for project PROJ-001",
    ]

    print("=" * 80)
    print("Chat Streaming Example")
    print("=" * 80)
    print()

    for i, message in enumerate(examples, 1):
        print(f"\n{'=' * 80}")
        print(f"Example {i}/{len(examples)}")
        print(f"{'=' * 80}\n")

        # Collect all events
        events = list(stream_chat_request(message))

        # Find final response
        responder_events = [e for e in events if e["event"] == "responder"]
        if responder_events:
            final_response = responder_events[-1]["data"]["response"]
            print("\n📝 Final Response:")
            print("-" * 80)
            print(final_response)
            print("-" * 80)

        print("\n⏱️  Waiting 2 seconds before next example...\n")
        time.sleep(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
    except requests.exceptions.ConnectionError:
        print("\n❌ Error: Could not connect to API server")
        print("   Make sure the API server is running on http://localhost:8000")
    except Exception as e:
        print(f"\n❌ Error: {e}")
