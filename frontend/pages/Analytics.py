"""
Analytics Dashboard

Pre-built dashboards for budget variance, contractor spend, and invoice aging.
All data is scoped to the authenticated user.
"""

import sys
import time
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

frontend_path = Path(__file__).parent.parent
sys.path.insert(0, str(frontend_path))

from utils.api_client import APIClient
from utils.formatters import format_currency

_CACHE_TTL = 60  # seconds


def _load_dashboard(api: APIClient) -> dict:
    """Return analytics data from session-state cache, re-fetching when stale."""
    now = time.monotonic()
    cached_at = st.session_state.get("_analytics_cached_at", 0)
    cached_data = st.session_state.get("_analytics_data")
    if cached_data is not None and (now - cached_at) < _CACHE_TTL:
        return cached_data
    data = api.get_analytics_dashboard()
    st.session_state["_analytics_data"] = data
    st.session_state["_analytics_cached_at"] = now
    return data


st.title("Analytics Dashboard")
st.markdown("Budget variance, contractor spend, and invoice aging — scoped to your data.")

api = APIClient()
api.token = st.session_state.get("token")

if st.button("Refresh"):
    st.session_state.pop("_analytics_data", None)
    st.session_state.pop("_analytics_cached_at", None)
    st.rerun()

st.divider()

# ── Load data ─────────────────────────────────────────────────────────────────
try:
    data = _load_dashboard(api)
except Exception as e:
    st.error(f"Failed to load analytics: {e}")
    st.stop()

summary = data.get("summary", {})
contractor_spend = data.get("contractor_spend", [])
invoice_aging = data.get("invoice_aging", {})
budget_summary = data.get("budget_summary", [])

# ── Summary KPIs ──────────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Invoices", summary.get("total_invoices", 0))
col2.metric("Total Invoice Value", format_currency(summary.get("total_invoice_value", 0)))
col3.metric("Contractors", summary.get("contractor_count", 0))
col4.metric("Budgets", summary.get("budget_count", 0))

st.divider()

# ── Budget Variance ───────────────────────────────────────────────────────────
st.subheader("Budget Variance by Project")

if budget_summary:
    projects = [b["project_name"] for b in budget_summary]
    allocated = [b["total_allocated"] for b in budget_summary]
    spent = [b["total_spent"] for b in budget_summary]
    variance_pcts = [b["variance_pct"] for b in budget_summary]

    # Colour spent bars: red = over budget, green = under
    spent_colors = ["#DC143C" if v > 0 else "#50C878" for v in variance_pcts]

    fig = go.Figure()
    fig.add_trace(go.Bar(name="Allocated", x=projects, y=allocated, marker_color="#4A90E2"))
    fig.add_trace(go.Bar(name="Spent", x=projects, y=spent, marker_color=spent_colors))
    fig.update_layout(
        barmode="group",
        xaxis_title="Project",
        yaxis_title="Amount ($)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=30),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Variance summary table
    import pandas as pd

    df = pd.DataFrame(
        [
            {
                "Project": b["project_name"],
                "Allocated": b["total_allocated"],
                "Spent": b["total_spent"],
                "Variance $": b["variance_amount"],
                "Variance %": b["variance_pct"],
                "Status": "Over" if b["variance_pct"] > 0 else "Under",
            }
            for b in budget_summary
        ]
    )
    st.dataframe(
        df.style.format(
            {
                "Allocated": "${:,.0f}",
                "Spent": "${:,.0f}",
                "Variance $": "${:,.0f}",
                "Variance %": "{:.1f}%",
            }
        ).map(
            lambda v: "color: #DC143C" if v == "Over" else "color: #50C878",
            subset=["Status"],
        ),
        use_container_width=True,
        hide_index=True,
    )

    # Cost-code drilldown (expander per project)
    for b in budget_summary:
        if not b["lines"]:
            continue
        with st.expander(f"{b['project_name']} — cost code breakdown"):
            line_df = pd.DataFrame(b["lines"])
            st.dataframe(
                line_df.style.format(
                    {
                        "allocated": "${:,.0f}",
                        "spent": "${:,.0f}",
                        "variance_amount": "${:,.0f}",
                        "variance_pct": "{:.1f}%",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )
else:
    st.info("No budget data available. Upload a budget file to see variance analysis.")

st.divider()

# ── Contractor Spend ──────────────────────────────────────────────────────────
st.subheader("Contractor Spend")

if contractor_spend:
    names = [r["contractor"] for r in contractor_spend]
    totals = [r["total_spend"] for r in contractor_spend]
    counts = [r["invoice_count"] for r in contractor_spend]

    fig = go.Figure(
        go.Bar(
            x=totals,
            y=names,
            orientation="h",
            marker_color="#4A90E2",
            text=[f"{format_currency(t)} ({c} inv.)" for t, c in zip(totals, counts)],
            textposition="outside",
        )
    )
    fig.update_layout(
        xaxis_title="Total Spend ($)",
        yaxis=dict(autorange="reversed"),
        margin=dict(l=10, r=120, t=20, b=40),
        height=max(300, len(names) * 40),
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No contractor spend data available. Upload invoices to see this dashboard.")

st.divider()

# ── Invoice Aging ─────────────────────────────────────────────────────────────
st.subheader("Invoice Aging")

buckets = invoice_aging.get("buckets", {})
amounts = invoice_aging.get("amounts", {})
bucket_labels = ["0-30", "31-60", "61-90", "90+"]
bucket_colors = ["#50C878", "#FFD700", "#FFA500", "#DC143C"]

if any(buckets.get(b, 0) > 0 for b in bucket_labels):
    col_count, col_amount = st.columns(2)

    with col_count:
        fig = go.Figure(
            go.Bar(
                x=bucket_labels,
                y=[buckets.get(b, 0) for b in bucket_labels],
                marker_color=bucket_colors,
                text=[buckets.get(b, 0) for b in bucket_labels],
                textposition="outside",
            )
        )
        fig.update_layout(
            title="Invoice Count by Age (days)",
            xaxis_title="Days Since Invoice",
            yaxis_title="# Invoices",
            margin=dict(t=40),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_amount:
        fig = go.Figure(
            go.Bar(
                x=bucket_labels,
                y=[amounts.get(b, 0) for b in bucket_labels],
                marker_color=bucket_colors,
                text=[format_currency(amounts.get(b, 0)) for b in bucket_labels],
                textposition="outside",
            )
        )
        fig.update_layout(
            title="Invoice Value by Age (days)",
            xaxis_title="Days Since Invoice",
            yaxis_title="Amount ($)",
            margin=dict(t=40),
        )
        st.plotly_chart(fig, use_container_width=True)

    # Aging risk callout
    overdue_count = buckets.get("61-90", 0) + buckets.get("90+", 0)
    overdue_value = amounts.get("61-90", 0.0) + amounts.get("90+", 0.0)
    if overdue_count > 0:
        st.warning(
            f"{overdue_count} invoice(s) older than 60 days, "
            f"totalling **{format_currency(overdue_value)}** — consider follow-up."
        )
else:
    st.info("No invoice data available. Upload invoices to see aging analysis.")
