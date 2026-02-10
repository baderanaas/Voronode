"""
Analytics Dashboard

Processing metrics, trends, and anomaly distribution.
"""

import streamlit as st
import sys
from pathlib import Path
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from collections import Counter

# Add paths
frontend_path = Path(__file__).parent.parent
sys.path.insert(0, str(frontend_path))

from utils.api_client import APIClient
from utils.formatters import format_currency, format_duration, format_datetime

# Page config
st.set_page_config(
    page_title="Analytics - Voronode",
    page_icon="📊",
    layout="wide",
)

st.title("📊 Analytics Dashboard")
st.markdown("Processing metrics, trends, and insights.")

# Initialize API client
api = APIClient()

# Refresh button
if st.button("🔄 Refresh Data"):
    api.clear_cache()
    st.rerun()

st.markdown("---")

# Get data
try:
    workflows = api.list_workflows()
    graph_stats = api.get_graph_stats()
except Exception as e:
    st.error(f"Failed to load data: {e}")
    st.stop()

# Processing Metrics
st.markdown("## ⚙️ Processing Metrics")

col1, col2, col3, col4 = st.columns(4)

# Calculate metrics
total_workflows = len(workflows)
completed = sum(1 for w in workflows if w.get("status") == "completed")
quarantined = sum(1 for w in workflows if w.get("status") == "quarantined")
failed = sum(1 for w in workflows if w.get("status") == "failed")

success_rate = (completed / total_workflows * 100) if total_workflows > 0 else 0
quarantine_rate = (quarantined / total_workflows * 100) if total_workflows > 0 else 0

with col1:
    st.metric("Total Workflows", total_workflows)

with col2:
    st.metric("Success Rate", f"{success_rate:.1f}%")

with col3:
    st.metric("Quarantine Rate", f"{quarantine_rate:.1f}%", delta=f"{quarantined} items")

with col4:
    st.metric("Failed", failed)

st.markdown("---")

# Status Distribution
st.markdown("## 📊 Workflow Status Distribution")

status_counts = Counter(w.get("status", "unknown") for w in workflows)

if status_counts:
    fig = px.pie(
        values=list(status_counts.values()),
        names=list(status_counts.keys()),
        title="Workflow Status Distribution",
        color_discrete_map={
            "completed": "#50C878",
            "quarantined": "#FFA500",
            "failed": "#DC143C",
            "processing": "#4A90E2",
        },
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No workflow data available")

st.markdown("---")

# Anomaly Analysis
st.markdown("## ⚠️ Anomaly Analysis")

try:
    # Collect all anomalies from workflows
    all_anomalies = []

    for workflow in workflows:
        try:
            details = api.get_workflow(workflow.get("document_id"))
            anomalies = details.get("state", {}).get("anomalies", [])
            all_anomalies.extend(anomalies)
        except:
            pass

    if all_anomalies:
        # Anomaly count
        st.metric("Total Anomalies Detected", len(all_anomalies))

        # Anomaly type distribution
        anomaly_types = Counter(a.get("type", "unknown") for a in all_anomalies)

        col1, col2 = st.columns(2)

        with col1:
            # Bar chart
            fig = px.bar(
                x=list(anomaly_types.keys()),
                y=list(anomaly_types.values()),
                title="Anomaly Type Frequency",
                labels={"x": "Anomaly Type", "y": "Count"},
                color=list(anomaly_types.values()),
                color_continuous_scale="reds",
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            # Severity distribution
            severity_counts = Counter(a.get("severity", "unknown") for a in all_anomalies)

            fig = px.pie(
                values=list(severity_counts.values()),
                names=list(severity_counts.keys()),
                title="Severity Distribution",
                color_discrete_map={
                    "low": "#90EE90",
                    "medium": "#FFD700",
                    "high": "#FF6B6B",
                    "critical": "#DC143C",
                },
            )
            st.plotly_chart(fig, use_container_width=True)

        # Top anomalies
        st.markdown("### Most Common Anomalies")

        for anomaly_type, count in anomaly_types.most_common(5):
            formatted_type = anomaly_type.replace("_", " ").title()
            st.text(f"{formatted_type}: {count} occurrences")

    else:
        st.success("✅ No anomalies detected across all workflows!")

except Exception as e:
    st.error(f"Failed to analyze anomalies: {e}")

st.markdown("---")

# Processing Time Analysis
st.markdown("## ⏱️ Processing Time Analysis")

try:
    # Calculate processing times (if we have timestamps)
    processing_times = []

    for workflow in workflows:
        try:
            details = api.get_workflow(workflow.get("document_id"))
            timeline = details.get("timeline", [])

            if len(timeline) >= 2:
                start_time = datetime.fromisoformat(
                    timeline[0].get("timestamp").replace("Z", "+00:00")
                )
                end_time = datetime.fromisoformat(
                    timeline[-1].get("timestamp").replace("Z", "+00:00")
                )
                duration = (end_time - start_time).total_seconds()
                processing_times.append(duration)
        except:
            pass

    if processing_times:
        avg_time = sum(processing_times) / len(processing_times)
        min_time = min(processing_times)
        max_time = max(processing_times)

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Average Time", format_duration(avg_time))

        with col2:
            st.metric("Fastest", format_duration(min_time))

        with col3:
            st.metric("Slowest", format_duration(max_time))

        # Histogram
        fig = px.histogram(
            x=processing_times,
            nbins=20,
            title="Processing Time Distribution",
            labels={"x": "Time (seconds)", "y": "Count"},
        )
        st.plotly_chart(fig, use_container_width=True)

    else:
        st.info("No processing time data available")

except Exception as e:
    st.warning(f"Could not calculate processing times: {e}")

st.markdown("---")

# Financial Metrics
st.markdown("## 💰 Financial Metrics")

try:
    # Aggregate invoice amounts
    total_invoice_value = 0
    invoice_count = 0

    for workflow in workflows:
        try:
            details = api.get_workflow(workflow.get("document_id"))
            invoice_data = details.get("state", {}).get("invoice", {})
            total_amount = invoice_data.get("total_amount", 0)

            if total_amount:
                total_invoice_value += float(total_amount)
                invoice_count += 1
        except:
            pass

    if invoice_count > 0:
        avg_invoice_value = total_invoice_value / invoice_count

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Total Invoice Value", format_currency(total_invoice_value))

        with col2:
            st.metric("Processed Invoices", invoice_count)

        with col3:
            st.metric("Average Invoice", format_currency(avg_invoice_value))

        # Invoice value distribution
        invoice_amounts = []

        for workflow in workflows:
            try:
                details = api.get_workflow(workflow.get("document_id"))
                invoice_data = details.get("state", {}).get("invoice", {})
                total_amount = invoice_data.get("total_amount", 0)

                if total_amount:
                    invoice_amounts.append(float(total_amount))
            except:
                pass

        if invoice_amounts:
            fig = px.histogram(
                x=invoice_amounts,
                nbins=20,
                title="Invoice Amount Distribution",
                labels={"x": "Amount ($)", "y": "Count"},
            )
            st.plotly_chart(fig, use_container_width=True)

    else:
        st.info("No financial data available")

except Exception as e:
    st.warning(f"Could not calculate financial metrics: {e}")

st.markdown("---")

# Trend Analysis
st.markdown("## 📈 Trend Analysis")

try:
    # Group workflows by date
    workflow_dates = []

    for workflow in workflows:
        created_at = workflow.get("created_at")
        if created_at:
            try:
                dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                workflow_dates.append(dt.date())
            except:
                pass

    if workflow_dates:
        date_counts = Counter(workflow_dates)

        # Sort by date
        sorted_dates = sorted(date_counts.items())
        dates = [d[0] for d in sorted_dates]
        counts = [d[1] for d in sorted_dates]

        fig = px.line(
            x=dates,
            y=counts,
            title="Workflow Volume Over Time",
            labels={"x": "Date", "y": "Workflows"},
            markers=True,
        )
        st.plotly_chart(fig, use_container_width=True)

    else:
        st.info("No date data available for trend analysis")

except Exception as e:
    st.warning(f"Could not generate trend analysis: {e}")

# Sidebar
with st.sidebar:
    st.markdown("### 📊 Quick Stats")

    try:
        st.metric("Total Nodes", graph_stats.get("total_nodes", 0))
        st.metric("Total Invoices", graph_stats.get("invoice_count", 0))
        st.metric("Active Projects", graph_stats.get("project_count", 0))
    except:
        st.info("Stats unavailable")

    st.markdown("---")
    st.markdown("### 📅 Date Range")

    if workflows:
        try:
            dates = []
            for w in workflows:
                created = w.get("created_at")
                if created:
                    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    dates.append(dt)

            if dates:
                min_date = min(dates)
                max_date = max(dates)

                st.text(f"From: {min_date.strftime('%Y-%m-%d')}")
                st.text(f"To: {max_date.strftime('%Y-%m-%d')}")
                st.text(f"Days: {(max_date - min_date).days}")
        except:
            pass
