"""
Quarantine Queue Page

Most critical page - allows users to review and approve/reject quarantined invoices.
"""

import streamlit as st
import sys
from pathlib import Path
from typing import Dict, Any

# Add paths
frontend_path = Path(__file__).parent.parent
sys.path.insert(0, str(frontend_path))

from utils.api_client import APIClient
from utils.formatters import format_currency, format_date, format_datetime
from components.invoice_card import render_invoice_card
from components.anomaly_badge import render_anomaly_list, render_anomaly_summary
from components.workflow_status import render_workflow_status

st.title("⚠️ Quarantine Queue")
st.markdown("Review and approve invoices that require human oversight.")

# Initialize API client
api = APIClient()

# Add refresh button
col1, col2, col3 = st.columns([1, 1, 4])
with col1:
    if st.button("🔄 Refresh Queue"):
        api.clear_cache()
        st.rerun()

with col2:
    auto_refresh = st.checkbox("Auto-refresh (10s)")

# Auto-refresh logic
if auto_refresh:
    import time

    time.sleep(10)
    st.rerun()

try:
    # Fetch quarantined workflows
    quarantined = api.list_quarantined_workflows()

    if not quarantined:
        st.success("✅ No invoices in quarantine!")
        st.info("All invoices have been processed successfully or are awaiting processing.")
        st.stop()

    st.info(f"📋 **{len(quarantined)}** workflows require review")

    # Display each quarantined workflow
    for idx, workflow in enumerate(quarantined):
        workflow_id = workflow.get("document_id", "Unknown")

        with st.expander(f"🔍 Workflow {idx + 1}: {workflow_id}", expanded=(idx == 0)):
            # Get full workflow details
            try:
                workflow_details = api.get_workflow(workflow_id)
            except Exception as e:
                st.error(f"Failed to load workflow details: {e}")
                continue

            # Extract invoice data and anomalies
            state = workflow_details.get("state", {})
            invoice_data = state.get("extracted_data", {})  # Fixed: was "invoice"
            anomalies = state.get("anomalies", [])
            quarantine_reason = state.get("pause_reason") or state.get("quarantine_reason", "Unknown")

            # Debug: Show what keys are in the state
            with st.expander("🔍 Debug: Raw State Keys", expanded=False):
                st.write("State keys:", list(state.keys()))
                st.write("Has extracted_data:", "extracted_data" in state)
                st.write("Has invoice:", "invoice" in state)
                if "extracted_data" in state:
                    st.write("Extracted data keys:", list(state["extracted_data"].keys()) if isinstance(state["extracted_data"], dict) else "Not a dict")
                st.write("Raw text length:", len(state.get("raw_text", "")) if state.get("raw_text") else 0)
                st.write("Error history:", state.get("error_history", []))

            # Display workflow status
            st.markdown("### Workflow Status")
            col1, col2 = st.columns(2)

            with col1:
                status = workflow_details.get("status", "unknown")
                st.metric("Status", status.upper())

            with col2:
                created_at = workflow_details.get("created_at", "N/A")
                if created_at != "N/A":
                    st.metric("Created", format_datetime(created_at))

            # Quarantine reason
            st.warning(f"**Quarantine Reason:** {quarantine_reason}")

            # Display anomalies
            st.markdown("---")
            render_anomaly_summary(anomalies)

            if anomalies:
                with st.expander("📋 View All Anomalies"):
                    render_anomaly_list(anomalies, title="Detected Anomalies")

            # Display invoice details
            st.markdown("---")
            st.markdown("### Invoice Details")

            if invoice_data:
                render_invoice_card(invoice_data, expanded=True)
            else:
                st.warning("No invoice data available")

            # Corrections editor
            st.markdown("---")
            st.markdown("### Review & Actions")

            # Tabs for approve/reject/correct
            tab1, tab2, tab3 = st.tabs(["✅ Approve", "❌ Reject", "✏️ Correct & Retry"])

            with tab1:
                st.markdown("**Approve this invoice as-is**")
                st.info(
                    "Approving will proceed with the workflow using the current invoice data. "
                    "The invoice will be inserted into the knowledge graph."
                )

                notes_approve = st.text_area(
                    "Approval Notes (optional)",
                    key=f"approve_notes_{workflow_id}",
                    placeholder="e.g., Verified with project manager, amount confirmed",
                )

                if st.button(
                    "✅ Approve Invoice",
                    key=f"approve_{workflow_id}",
                    type="primary",
                ):
                    with st.spinner("Approving workflow..."):
                        try:
                            result = api.resume_workflow(
                                workflow_id=workflow_id,
                                action="approve",
                                notes=notes_approve,
                            )
                            st.success("✅ Invoice approved successfully!")
                            st.json(result)
                            api.clear_cache()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to approve: {e}")

            with tab2:
                st.markdown("**Reject this invoice**")
                st.warning(
                    "Rejecting will mark the invoice as invalid and stop the workflow. "
                    "The invoice will NOT be inserted into the knowledge graph."
                )

                notes_reject = st.text_area(
                    "Rejection Reason (required)",
                    key=f"reject_notes_{workflow_id}",
                    placeholder="e.g., Invalid vendor, out of scope, duplicate invoice",
                )

                if st.button("❌ Reject Invoice", key=f"reject_{workflow_id}"):
                    if not notes_reject:
                        st.error("Please provide a rejection reason")
                    else:
                        with st.spinner("Rejecting workflow..."):
                            try:
                                result = api.resume_workflow(
                                    workflow_id=workflow_id,
                                    action="reject",
                                    notes=notes_reject,
                                )
                                st.success("❌ Invoice rejected")
                                st.json(result)
                                api.clear_cache()
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to reject: {e}")

            with tab3:
                st.markdown("**Apply corrections and retry processing**")
                st.info(
                    "Provide corrected values for specific fields. The workflow will "
                    "re-validate with the corrected data."
                )

                # Correction form
                st.markdown("#### Common Corrections")

                corrections = {}

                col1, col2 = st.columns(2)

                with col1:
                    new_total = st.number_input(
                        "Total Amount",
                        value=float(invoice_data.get("total_amount", 0)),
                        key=f"correct_total_{workflow_id}",
                    )
                    if new_total != float(invoice_data.get("total_amount", 0)):
                        corrections["total_amount"] = new_total

                    new_contract = st.text_input(
                        "Contract ID",
                        value=invoice_data.get("contract_id", ""),
                        key=f"correct_contract_{workflow_id}",
                    )
                    if new_contract != invoice_data.get("contract_id", ""):
                        corrections["contract_id"] = new_contract

                with col2:
                    new_invoice_num = st.text_input(
                        "Invoice Number",
                        value=invoice_data.get("invoice_number", ""),
                        key=f"correct_invoice_num_{workflow_id}",
                    )
                    if new_invoice_num != invoice_data.get("invoice_number", ""):
                        corrections["invoice_number"] = new_invoice_num

                    new_vendor = st.text_input(
                        "Vendor Name",
                        value=invoice_data.get("vendor_name", ""),
                        key=f"correct_vendor_{workflow_id}",
                    )
                    if new_vendor != invoice_data.get("vendor_name", ""):
                        corrections["vendor_name"] = new_vendor

                # Advanced corrections (JSON editor)
                with st.expander("🔧 Advanced: Edit Full Invoice JSON"):
                    import json

                    invoice_json = st.text_area(
                        "Invoice JSON",
                        value=json.dumps(invoice_data, indent=2),
                        height=300,
                        key=f"invoice_json_{workflow_id}",
                    )

                    try:
                        custom_corrections = json.loads(invoice_json)
                        if custom_corrections != invoice_data:
                            corrections = custom_corrections
                    except json.JSONDecodeError as e:
                        st.error(f"Invalid JSON: {e}")

                # Show corrections summary
                if corrections:
                    st.markdown("**Corrections to Apply:**")
                    st.json(corrections)

                notes_correct = st.text_area(
                    "Correction Notes",
                    key=f"correct_notes_{workflow_id}",
                    placeholder="Describe the corrections made",
                )

                if st.button(
                    "✏️ Apply Corrections & Retry",
                    key=f"correct_{workflow_id}",
                    type="primary",
                ):
                    if not corrections:
                        st.warning("No corrections specified")
                    else:
                        with st.spinner("Applying corrections and retrying..."):
                            try:
                                result = api.resume_workflow(
                                    workflow_id=workflow_id,
                                    action="correct",
                                    corrections=corrections,
                                    notes=notes_correct,
                                )
                                st.success("✏️ Corrections applied, workflow resumed")
                                st.json(result)
                                api.clear_cache()
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to apply corrections: {e}")

            st.markdown("---")

except Exception as e:
    st.error(f"❌ Error loading quarantine queue: {e}")
    st.info("Make sure the FastAPI backend is running on http://localhost:8080")
