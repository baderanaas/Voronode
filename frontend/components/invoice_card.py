"""
Invoice Card Component

Reusable component for displaying invoice information.
"""

import streamlit as st
from typing import Dict, Any
import sys
from pathlib import Path

# Add utils to path
utils_path = Path(__file__).parent.parent / "utils"
sys.path.insert(0, str(utils_path))

from formatters import (
    format_currency,
    format_date,
    format_datetime,
    truncate_text,
)


def render_invoice_card(invoice_data: Dict[str, Any], expanded: bool = False):
    """
    Render an invoice card with key information.

    Args:
        invoice_data: Invoice data dictionary
        expanded: Whether to show full details
    """
    with st.container():
        # Header row
        col1, col2, col3, col4 = st.columns([2, 2, 2, 1])

        with col1:
            invoice_num = invoice_data.get("invoice_number", "N/A")
            st.markdown(f"**Invoice:** `{invoice_num}`")

        with col2:
            total = invoice_data.get("total_amount", 0)
            st.markdown(f"**Amount:** {format_currency(total)}")

        with col3:
            invoice_date = invoice_data.get("invoice_date", "N/A")
            if invoice_date != "N/A":
                formatted_date = format_date(invoice_date)
                st.markdown(f"**Date:** {formatted_date}")
            else:
                st.markdown(f"**Date:** N/A")

        with col4:
            status = invoice_data.get("status", "unknown")
            status_colors = {
                "approved": "🟢",
                "pending": "🟡",
                "rejected": "🔴",
                "quarantined": "🟠",
            }
            st.markdown(f"{status_colors.get(status, '⚪')} {status.title()}")

        # Expandable details
        if expanded:
            st.markdown("---")

            # Vendor and contract info
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**Vendor Information**")
                vendor = invoice_data.get("vendor_name", "N/A")
                st.text(f"Name: {vendor}")

                contractor = invoice_data.get("contractor_id", "N/A")
                st.text(f"Contractor ID: {contractor}")

            with col2:
                st.markdown("**Contract Details**")
                contract_id = invoice_data.get("contract_id", "N/A")
                st.text(f"Contract ID: {contract_id}")

                project_id = invoice_data.get("project_id", "N/A")
                st.text(f"Project ID: {project_id}")

            # Line items
            line_items = invoice_data.get("line_items", [])
            if line_items:
                st.markdown("**Line Items**")
                for idx, item in enumerate(line_items, 1):
                    description = item.get("description", "N/A")
                    quantity = item.get("quantity", 0)
                    unit_price = item.get("unit_price", 0)
                    amount = item.get("amount", 0)

                    st.text(
                        f"{idx}. {truncate_text(description, 40)} | "
                        f"Qty: {quantity} × {format_currency(unit_price)} = "
                        f"{format_currency(amount)}"
                    )

            # Payment terms
            payment_terms = invoice_data.get("payment_terms", {})
            if payment_terms:
                st.markdown("**Payment Terms**")
                col1, col2, col3 = st.columns(3)

                with col1:
                    due_date = payment_terms.get("due_date", "N/A")
                    if due_date != "N/A":
                        st.text(f"Due: {format_date(due_date)}")
                    else:
                        st.text("Due: N/A")

                with col2:
                    retention = payment_terms.get("retention_amount", 0)
                    st.text(f"Retention: {format_currency(retention)}")

                with col3:
                    net_payable = payment_terms.get("net_payable", 0)
                    st.text(f"Net Payable: {format_currency(net_payable)}")

            # Metadata
            created_at = invoice_data.get("created_at")
            updated_at = invoice_data.get("updated_at")
            if created_at or updated_at:
                st.markdown("**Metadata**")
                col1, col2 = st.columns(2)

                with col1:
                    if created_at:
                        st.caption(f"Created: {format_datetime(created_at)}")

                with col2:
                    if updated_at:
                        st.caption(f"Updated: {format_datetime(updated_at)}")


def render_invoice_summary(invoice_data: Dict[str, Any]):
    """
    Render a compact invoice summary (single line).

    Args:
        invoice_data: Invoice data dictionary
    """
    invoice_num = invoice_data.get("invoice_number", "N/A")
    total = format_currency(invoice_data.get("total_amount", 0))
    vendor = truncate_text(invoice_data.get("vendor_name", "N/A"), 30)
    invoice_date = invoice_data.get("invoice_date", "N/A")

    if invoice_date != "N/A":
        date_str = format_date(invoice_date)
    else:
        date_str = "N/A"

    st.markdown(
        f"**{invoice_num}** | {vendor} | {total} | {date_str}"
    )
