"""
Risk Feed Dashboard

Real-time monitoring of invoice processing and risk alerts.
"""

import streamlit as st
import sys
import time
from pathlib import Path
from datetime import datetime

# Add paths
frontend_path = Path(__file__).parent.parent
sys.path.insert(0, str(frontend_path))

from utils.api_client import APIClient
from utils.formatters import (
    format_currency,
    format_datetime,
    get_status_emoji,
)
from components.anomaly_badge import render_anomaly_badge, get_severity_level
from utils.logger import get_logger

logger = get_logger(__name__)

st.title("🚨 Risk Feed")
st.markdown("Real-time monitoring of invoice processing and anomaly alerts.")

# Initialize API client
api = APIClient()
api.token = st.session_state.get("token")

# Refresh controls
col1, col2, col3 = st.columns([1, 1, 4])

with col1:
    if st.button("🔄 Refresh"):
        st.session_state.pop("_risk_stats", None)
        st.session_state.pop("_risk_stats_at", None)
        api.clear_cache()
        st.rerun()

with col2:
    auto_refresh = st.checkbox("Auto-refresh (5s)")

if auto_refresh:
    import time

    time.sleep(5)
    st.rerun()

st.markdown("---")

# Metrics Dashboard
st.markdown("## 📊 System Overview")

try:
    # Get graph stats (session-state cache, 60s TTL)
    _now = time.monotonic()
    if (
        st.session_state.get("_risk_stats") is None
        or (_now - st.session_state.get("_risk_stats_at", 0)) >= 60
    ):
        st.session_state["_risk_stats"] = api.get_graph_stats()
        st.session_state["_risk_stats_at"] = _now
    graph_stats = st.session_state["_risk_stats"]

    # Get workflow stats
    all_workflows = api.list_workflows()
    quarantined_workflows = api.list_quarantined_workflows()

    # Calculate metrics
    total_invoices = graph_stats.get("invoice_count", 0)
    total_projects = graph_stats.get("project_count", 0)
    total_contracts = graph_stats.get("contract_count", 0)
    total_workflows = len(all_workflows)
    quarantined_count = len(quarantined_workflows)

    # Count by status
    completed_count = sum(1 for w in all_workflows if w.get("status") == "completed")
    failed_count = sum(1 for w in all_workflows if w.get("status") == "failed")
    processing_count = sum(1 for w in all_workflows if w.get("status") == "processing")

    # Display metrics
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("Total Invoices", total_invoices)

    with col2:
        st.metric("Active Projects", total_projects)

    with col3:
        st.metric("Contracts", total_contracts)

    with col4:
        st.metric("Workflows", total_workflows)

    with col5:
        st.metric("In Quarantine", quarantined_count, delta=f"{quarantined_count} pending")

    # Processing metrics
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("✅ Completed", completed_count)

    with col2:
        st.metric("⚙️ Processing", processing_count)

    with col3:
        st.metric("⚠️ Quarantined", quarantined_count)

    with col4:
        st.metric("❌ Failed", failed_count)

except Exception as e:
    logger.error("risk_metrics_load_failed", error=e)
    st.error(f"Failed to load metrics: {e}")

st.markdown("---")

# Recent Activity Feed
st.markdown("## 📋 Recent Activity")

try:
    # Get recent workflows
    recent_workflows = api.list_workflows()[:20]

    if not recent_workflows:
        st.info("No workflows yet. Upload an invoice to get started!")
    else:
        # Filter controls
        col1, col2 = st.columns([1, 3])

        with col1:
            status_filter = st.selectbox(
                "Filter by Status",
                ["All", "completed", "quarantined", "processing", "failed"],
            )

        # Apply filter
        if status_filter != "All":
            filtered_workflows = [
                w for w in recent_workflows if w.get("status") == status_filter
            ]
        else:
            filtered_workflows = recent_workflows

        st.info(f"Showing {len(filtered_workflows)} workflows")

        # Display workflows
        for workflow in filtered_workflows:
            workflow_id = workflow.get("document_id", "N/A")
            status = workflow.get("status", "unknown")
            created_at = workflow.get("created_at", "N/A")

            # Get full details to show anomalies
            try:
                workflow_details = api.get_workflow(workflow_id)
                state = workflow_details.get("state", {})
                anomalies = state.get("anomalies", [])
                invoice_data = state.get("extracted_data", {})  # Fixed: was "invoice"

                with st.container():
                    # Header row
                    col1, col2, col3, col4 = st.columns([3, 2, 2, 1])

                    with col1:
                        emoji = get_status_emoji(status)
                        st.markdown(f"### {emoji} `{workflow_id[:12]}...`")

                    with col2:
                        st.metric("Status", status.upper())

                    with col3:
                        if created_at != "N/A":
                            st.caption(format_datetime(created_at))

                    with col4:
                        if st.button("Details", key=f"details_{workflow_id}"):
                            st.session_state[f"expand_{workflow_id}"] = True

                    # Invoice summary
                    if invoice_data:
                        invoice_num = invoice_data.get("invoice_number", "N/A")
                        vendor = invoice_data.get("vendor_name", "N/A")
                        total = invoice_data.get("total_amount", 0)

                        st.text(
                            f"Invoice: {invoice_num} | Vendor: {vendor} | "
                            f"Amount: {format_currency(total)}"
                        )

                    # Anomalies
                    if anomalies:
                        severity = get_severity_level(anomalies)

                        # Color code based on severity
                        if severity == "critical":
                            st.error(f"🚨 {len(anomalies)} CRITICAL anomalies detected")
                        elif severity == "high":
                            st.warning(f"⚠️ {len(anomalies)} HIGH severity anomalies")
                        else:
                            st.info(f"ℹ️ {len(anomalies)} anomalies detected")

                        # Show anomalies in expander
                        if st.session_state.get(f"expand_{workflow_id}", False):
                            with st.expander("View Anomalies", expanded=True):
                                for anomaly in anomalies[:5]:  # Show first 5
                                    render_anomaly_badge(anomaly, compact=False)

                                if len(anomalies) > 5:
                                    st.caption(f"... and {len(anomalies) - 5} more")
                    else:
                        st.success("✅ No anomalies")

                    st.markdown("---")

            except Exception as e:
                st.error(f"Failed to load workflow {workflow_id}: {e}")

except Exception as e:
    st.error(f"Failed to load activity feed: {e}")

# Sidebar with alerts
with st.sidebar:
    st.markdown("### 🚨 Active Alerts")

    try:
        # Count high-severity quarantined items
        quarantined = api.list_quarantined_workflows()
        high_priority = []

        for workflow in quarantined:
            try:
                details = api.get_workflow(workflow.get("document_id"))
                anomalies = details.get("state", {}).get("anomalies", [])
                severity = get_severity_level(anomalies)

                if severity in ["critical", "high"]:
                    high_priority.append(
                        {
                            "workflow_id": workflow.get("document_id"),
                            "severity": severity,
                            "count": len(anomalies),
                        }
                    )
            except:
                pass

        if high_priority:
            st.error(f"⚠️ {len(high_priority)} high-priority items in quarantine")

            for item in high_priority[:3]:  # Show top 3
                st.markdown(
                    f"**{item['severity'].upper()}**: {item['count']} anomalies\n"
                    f"`{item['workflow_id'][:12]}...`"
                )

            if st.button("Go to Quarantine Queue"):
                st.switch_page("pages/2_Quarantine_Queue.py")
        else:
            st.success("✅ No high-priority alerts")

    except Exception as e:
        st.warning("Could not load alerts")

    st.markdown("---")
    st.markdown("### 📈 Quick Actions")

    if st.button("📤 Upload Invoice", use_container_width=True):
        st.switch_page("pages/3_Upload_Invoice.py")

    if st.button("🔍 Explore Graph", use_container_width=True):
        st.switch_page("pages/4_Graph_Explorer.py")

    if st.button("📊 View Analytics", use_container_width=True):
        st.switch_page("pages/5_Analytics.py")
