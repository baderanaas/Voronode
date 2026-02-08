"""
Demonstration of Phase 3 LangGraph Workflow Features

This script shows how to:
1. Upload an invoice using the graph workflow
2. Check quarantine queue
3. Resume quarantined workflows with human feedback
4. Monitor workflow status
"""

import time
import requests
from pathlib import Path
from typing import Dict, Any


BASE_URL = "http://localhost:8081/api"


def upload_invoice_with_workflow(pdf_path: Path) -> Dict[str, Any]:
    """Upload invoice using LangGraph workflow."""
    print(f"\n{'='*60}")
    print(f"📄 Uploading invoice: {pdf_path.name}")
    print(f"{'='*60}")

    with open(pdf_path, "rb") as f:
        response = requests.post(
            f"{BASE_URL}/invoices/upload-graph",
            files={"file": (pdf_path.name, f, "application/pdf")},
        )

    result = response.json()

    print(f"\n✅ Upload Response:")
    print(f"   Status: {result.get('success')}")
    print(f"   Message: {result.get('message')}")
    print(f"   Workflow ID: {result.get('workflow_id')}")
    print(f"   Invoice Number: {result.get('invoice_number')}")
    print(f"   Amount: ${result.get('amount')}")
    print(f"   Risk Level: {result.get('risk_level')}")
    print(f"   Retry Count: {result.get('retry_count')}")
    print(f"   Requires Review: {result.get('requires_review')}")
    print(f"   Processing Time: {result.get('processing_time_seconds')}s")

    if result.get('validation_anomalies'):
        print(f"\n⚠️  Validation Anomalies:")
        for anomaly in result['validation_anomalies']:
            print(f"   - [{anomaly['severity']}] {anomaly['message']}")

    return result


def check_quarantine_queue() -> list:
    """Check for quarantined workflows."""
    print(f"\n{'='*60}")
    print(f"🔍 Checking Quarantine Queue")
    print(f"{'='*60}")

    response = requests.get(f"{BASE_URL}/workflows/quarantined")
    quarantined = response.json()

    if quarantined:
        print(f"\n📋 Found {len(quarantined)} quarantined workflow(s):")
        for wf in quarantined:
            print(f"\n   Document ID: {wf['document_id']}")
            print(f"   Status: {wf['status']}")
            print(f"   Risk Level: {wf['risk_level']}")
            print(f"   Retry Count: {wf['retry_count']}")
            print(f"   Pause Reason: {wf['pause_reason']}")
            print(f"   Created: {wf['created_at']}")

            if wf.get('anomalies'):
                print(f"   Anomalies:")
                for anomaly in wf['anomalies']:
                    print(f"     - [{anomaly['severity']}] {anomaly['message']}")
    else:
        print("\n✅ No quarantined workflows")

    return quarantined


def resume_workflow(workflow_id: str, approved: bool = True, corrections: Dict = None, notes: str = None):
    """Resume a quarantined workflow."""
    print(f"\n{'='*60}")
    print(f"▶️  Resuming Workflow: {workflow_id}")
    print(f"{'='*60}")

    payload = {
        "approved": approved,
        "corrections": corrections or {},
        "notes": notes,
    }

    print(f"\n📝 Feedback:")
    print(f"   Approved: {approved}")
    if corrections:
        print(f"   Corrections: {corrections}")
    if notes:
        print(f"   Notes: {notes}")

    response = requests.post(
        f"{BASE_URL}/workflows/{workflow_id}/resume",
        json=payload,
    )

    result = response.json()

    print(f"\n✅ Resume Response:")
    print(f"   Success: {result.get('success')}")
    print(f"   Message: {result.get('message')}")
    print(f"   Final Status: {result.get('risk_level')}")
    print(f"   Invoice ID: {result.get('invoice_id')}")

    return result


def get_workflow_status(workflow_id: str) -> Dict[str, Any]:
    """Get current workflow status."""
    response = requests.get(f"{BASE_URL}/workflows/{workflow_id}/status")
    return response.json()


def monitor_workflow(workflow_id: str, timeout: int = 60):
    """Monitor workflow status until completion."""
    print(f"\n{'='*60}")
    print(f"⏳ Monitoring Workflow: {workflow_id}")
    print(f"{'='*60}")

    start_time = time.time()

    while time.time() - start_time < timeout:
        status = get_workflow_status(workflow_id)

        print(f"\r   Status: {status['status']} | Risk: {status['risk_level']} | Retries: {status['retry_count']}   ", end="")

        if status['status'] in ['completed', 'failed', 'quarantined']:
            print(f"\n\n✅ Workflow finished: {status['status']}")
            return status

        time.sleep(2)

    print(f"\n\n⏰ Timeout reached")
    return None


# Example Usage
if __name__ == "__main__":
    print("\n" + "="*60)
    print("🚀 Phase 3: LangGraph Workflow Demonstration")
    print("="*60)

    # Example 1: Upload a clean invoice (will complete automatically)
    print("\n" + "="*60)
    print("EXAMPLE 1: Clean Invoice (Low Risk)")
    print("="*60)

    # Note: Replace with actual PDF path
    # result = upload_invoice_with_workflow(Path("backend/tests/fixtures/invoices/INV-2024-0001.pdf"))

    # if not result.get('requires_review'):
    #     print("\n✅ Invoice processed successfully without human intervention")

    # Example 2: Check quarantine queue
    print("\n" + "="*60)
    print("EXAMPLE 2: Check Quarantine Queue")
    print("="*60)

    quarantined = check_quarantine_queue()

    # Example 3: Resume quarantined workflow (if any exist)
    if quarantined:
        print("\n" + "="*60)
        print("EXAMPLE 3: Resume Quarantined Workflow")
        print("="*60)

        workflow_id = quarantined[0]['document_id']

        # Option A: Approve as-is
        # resume_workflow(
        #     workflow_id,
        #     approved=True,
        #     notes="Verified with contractor, amounts are correct"
        # )

        # Option B: Apply corrections
        # resume_workflow(
        #     workflow_id,
        #     approved=False,
        #     corrections={
        #         "total_amount": 10000.00,
        #         "line_items": [...]
        #     },
        #     notes="Corrected total amount based on contractor invoice"
        # )

    # Example 4: Compare old vs new endpoints
    print("\n" + "="*60)
    print("EXAMPLE 4: Endpoint Comparison")
    print("="*60)

    print("\n📊 Legacy Endpoint: /api/invoices/upload")
    print("   - Sequential pipeline")
    print("   - No conditional routing")
    print("   - No retry logic")
    print("   - No human-in-the-loop")

    print("\n📊 New Endpoint: /api/invoices/upload-graph")
    print("   - LangGraph orchestration")
    print("   - Conditional routing by risk")
    print("   - Automatic retries with critic")
    print("   - Human-in-the-loop for high-risk")
    print("   - Complete state persistence")

    print("\n" + "="*60)
    print("✅ Demo Complete")
    print("="*60)
    print("\nFor full documentation, see: PHASE3_IMPLEMENTATION.md")
