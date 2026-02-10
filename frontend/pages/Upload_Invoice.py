"""
Upload Invoice Page

Upload PDF invoices and track processing through the workflow.
"""

import streamlit as st
import sys
from pathlib import Path
import time

# Add paths
frontend_path = Path(__file__).parent.parent
sys.path.insert(0, str(frontend_path))

from utils.api_client import APIClient
from utils.formatters import format_file_size
from components.invoice_card import render_invoice_card
from components.anomaly_badge import render_anomaly_list, get_severity_level
from components.workflow_status import render_workflow_progress, render_workflow_status

# Page config
st.set_page_config(
    page_title="Upload Invoice - Voronode",
    page_icon="📤",
    layout="wide",
)

st.title("📤 Upload Invoice")
st.markdown("Upload PDF invoices for automated processing and risk analysis.")

# Initialize API client
api = APIClient()

# File uploader
st.markdown("### Select Invoice PDF")
uploaded_file = st.file_uploader(
    "Choose a PDF file",
    type=["pdf"],
    help="Upload a construction invoice in PDF format",
)

if uploaded_file is not None:
    # Display file info
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Filename", uploaded_file.name)

    with col2:
        st.metric("Size", format_file_size(uploaded_file.size))

    with col3:
        st.metric("Type", uploaded_file.type)

    # Process button
    if st.button("🚀 Process Invoice", type="primary", use_container_width=True):
        # Upload and process
        with st.spinner("Uploading and processing invoice..."):
            progress_bar = st.progress(0)
            status_text = st.empty()

            try:
                # Upload file
                status_text.text("Uploading file...")
                progress_bar.progress(10)

                file_content = uploaded_file.getvalue()
                result = api.upload_invoice_stream(file_content, uploaded_file.name)

                progress_bar.progress(30)
                status_text.text("Processing with LangGraph workflow...")

                workflow_id = result.get("workflow_id")
                st.session_state["current_workflow_id"] = workflow_id

                # Poll for workflow completion
                max_attempts = 60  # 60 seconds
                attempt = 0

                while attempt < max_attempts:
                    workflow_status = api.get_workflow(workflow_id)
                    status = workflow_status.get("status", "unknown")

                    # Update progress based on workflow state
                    progress = 30 + (attempt / max_attempts) * 60
                    progress_bar.progress(int(progress) / 100)
                    status_text.text(f"Status: {status} - {workflow_status.get('current_node', 'N/A')}")

                    if status in ["completed", "quarantined", "failed"]:
                        break

                    time.sleep(1)
                    attempt += 1

                progress_bar.progress(100)
                status_text.text("Processing complete!")

                # Display results
                st.markdown("---")
                st.markdown("## Processing Results")

                state = workflow_status.get("state", {})
                invoice_data = state.get("extracted_data", {})  # Fixed: was "invoice"
                anomalies = state.get("anomalies", [])
                final_status = workflow_status.get("status", "unknown")

                # Status indicator
                if final_status == "completed":
                    st.success("✅ Invoice processed successfully!")
                elif final_status == "quarantined":
                    st.warning("⚠️ Invoice quarantined - requires human review")
                    st.info("Go to **Quarantine Queue** to review and approve this invoice.")
                elif final_status == "failed":
                    st.error("❌ Processing failed")
                else:
                    st.info(f"Status: {final_status}")

                # Workflow details
                with st.expander("📊 Workflow Details", expanded=False):
                    render_workflow_status(workflow_status, show_timeline=True)

                # Invoice data
                st.markdown("### Extracted Invoice Data")

                if invoice_data:
                    render_invoice_card(invoice_data, expanded=True)
                else:
                    st.warning("No invoice data extracted")

                # Anomalies
                if anomalies:
                    st.markdown("---")
                    severity = get_severity_level(anomalies)

                    if severity in ["critical", "high"]:
                        st.error(f"⚠️ {len(anomalies)} anomalies detected (Severity: {severity.upper()})")
                    else:
                        st.warning(f"⚠️ {len(anomalies)} anomalies detected (Severity: {severity.upper()})")

                    render_anomaly_list(anomalies, title="Detected Anomalies")
                else:
                    st.success("✅ No anomalies detected")

                # Actions
                st.markdown("---")
                st.markdown("### Next Steps")

                col1, col2, col3 = st.columns(3)

                with col1:
                    if st.button("📤 Upload Another Invoice"):
                        st.rerun()

                with col2:
                    if final_status == "quarantined":
                        if st.button("⚠️ Go to Quarantine Queue"):
                            st.switch_page("pages/2_Quarantine_Queue.py")

                with col3:
                    if st.button("📊 View Analytics"):
                        st.switch_page("pages/5_Analytics.py")

            except Exception as e:
                progress_bar.progress(0)
                status_text.text("")
                st.error(f"❌ Error processing invoice: {e}")
                st.info("Make sure the FastAPI backend is running on http://localhost:8080")

else:
    # Show instructions when no file is uploaded
    st.info("👆 Upload a PDF invoice to get started")

    st.markdown("### What happens when you upload?")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("""
        **Automated Processing:**
        1. 📄 PDF text extraction
        2. 🤖 LLM-based data structuring
        3. ✅ Validation & anomaly detection
        4. ⚖️ Contract compliance audit
        5. 📊 Knowledge graph insertion
        """)

    with col2:
        st.markdown("""
        **Risk Detection:**
        - Duplicate invoices
        - Price spikes
        - Missing contracts
        - Retention violations
        - Billing cap violations
        - Out-of-scope charges
        """)

    # Show recent workflows
    st.markdown("---")
    st.markdown("### Recent Workflows")

    try:
        recent_workflows = api.list_workflows()[:5]

        if recent_workflows:
            for workflow in recent_workflows:
                workflow_id = workflow.get("document_id", "N/A")
                status = workflow.get("status", "unknown")
                created_at = workflow.get("created_at", "N/A")

                col1, col2, col3, col4 = st.columns([3, 2, 2, 2])

                with col1:
                    st.text(f"ID: {workflow_id[:16]}...")

                with col2:
                    status_colors = {
                        "completed": "🟢",
                        "quarantined": "🟡",
                        "failed": "🔴",
                        "processing": "🔵",
                    }
                    st.text(f"{status_colors.get(status, '⚪')} {status}")

                with col3:
                    from utils.formatters import format_datetime

                    if created_at != "N/A":
                        st.text(format_datetime(created_at))

                with col4:
                    if st.button("View", key=f"view_{workflow_id}"):
                        st.session_state["selected_workflow"] = workflow_id
                        # Show details in expander
                        with st.expander(f"Workflow {workflow_id}", expanded=True):
                            full_workflow = api.get_workflow(workflow_id)
                            render_workflow_status(full_workflow, show_timeline=True)

        else:
            st.info("No workflows yet. Upload your first invoice to get started!")

    except Exception as e:
        st.warning(f"Could not load recent workflows: {e}")

# Sidebar with tips
with st.sidebar:
    st.markdown("### 💡 Tips")
    st.markdown("""
    - PDF quality matters - clear text works best
    - Multi-page invoices are supported
    - Processing typically takes 5-15 seconds
    - High-risk invoices go to quarantine
    """)

    st.markdown("### 📊 Quick Stats")
    try:
        stats = api.get_graph_stats()
        st.metric("Total Invoices", stats.get("invoice_count", 0))
        st.metric("Projects", stats.get("project_count", 0))
        st.metric("Contracts", stats.get("contract_count", 0))
    except:
        st.info("Stats unavailable")
