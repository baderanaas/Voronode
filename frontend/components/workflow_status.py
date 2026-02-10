"""
Workflow Status Component

Display workflow status with progress indicators.
"""

import streamlit as st
from typing import Dict, Any
import sys
from pathlib import Path

# Add utils to path
utils_path = Path(__file__).parent.parent / "utils"
sys.path.insert(0, str(utils_path))

from formatters import get_status_emoji, format_datetime


def render_workflow_status(workflow: Dict[str, Any], show_timeline: bool = True):
    """
    Render workflow status with visual progress indicator.

    Args:
        workflow: Workflow data dictionary
        show_timeline: Whether to show detailed timeline
    """
    status = workflow.get("status", "unknown")
    workflow_id = workflow.get("document_id", "N/A")

    # Status header
    emoji = get_status_emoji(status)
    st.markdown(f"## {emoji} Workflow: `{workflow_id}`")

    # Status badge
    status_colors = {
        "processing": "#4A90E2",
        "completed": "#50C878",
        "quarantined": "#FFA500",
        "failed": "#DC143C",
        "pending": "#808080",
    }

    color = status_colors.get(status.lower(), "#808080")
    st.markdown(
        f'<div style="background-color: {color}; color: white; '
        f'padding: 0.5rem 1rem; border-radius: 0.5rem; '
        f'text-align: center; font-weight: bold; margin: 1rem 0;">'
        f'{status.upper()}</div>',
        unsafe_allow_html=True,
    )

    # Progress information
    current_node = workflow.get("current_node", "Unknown")
    st.info(f"📍 Current Node: **{current_node}**")

    # Timeline
    if show_timeline:
        timeline = workflow.get("timeline", [])
        if timeline:
            st.markdown("### Timeline")

            for event in timeline:
                event_type = event.get("event", "unknown")
                timestamp = event.get("timestamp", "N/A")
                node = event.get("node", "N/A")

                formatted_time = format_datetime(timestamp) if timestamp != "N/A" else "N/A"

                # Event icon
                event_icons = {
                    "start": "🚀",
                    "node_enter": "▶️",
                    "node_exit": "✓",
                    "quarantine": "⚠️",
                    "error": "❌",
                    "complete": "🏁",
                }
                icon = event_icons.get(event_type, "•")

                st.markdown(f"{icon} **{event_type}** - {node} - {formatted_time}")


def render_workflow_progress(workflow: Dict[str, Any]):
    """
    Render a compact workflow progress bar.

    Args:
        workflow: Workflow data dictionary
    """
    status = workflow.get("status", "unknown")

    # Define workflow stages
    stages = ["extract", "validate", "compliance_audit", "insert_graph", "complete"]
    current_node = workflow.get("current_node", "")

    # Determine progress
    if status.lower() == "completed":
        progress = 100
    elif status.lower() == "failed":
        progress = 0
    elif current_node in stages:
        progress = ((stages.index(current_node) + 1) / len(stages)) * 100
    else:
        progress = 10

    # Display progress bar
    st.progress(progress / 100)
    st.caption(f"Progress: {progress:.0f}% - Current: {current_node}")


def render_workflow_actions(workflow_id: str):
    """
    Render action buttons for workflow management.

    Args:
        workflow_id: Workflow ID
    """
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("🔄 Refresh Status", key=f"refresh_{workflow_id}"):
            st.rerun()

    with col2:
        if st.button("📋 View Details", key=f"details_{workflow_id}"):
            st.session_state[f"show_details_{workflow_id}"] = True

    with col3:
        if st.button("❌ Cancel", key=f"cancel_{workflow_id}"):
            st.warning("Cancel functionality not yet implemented")


def render_compact_workflow_status(workflow: Dict[str, Any]):
    """
    Render a single-line workflow status.

    Args:
        workflow: Workflow data dictionary
    """
    workflow_id = workflow.get("document_id", "N/A")
    status = workflow.get("status", "unknown")
    current_node = workflow.get("current_node", "N/A")
    emoji = get_status_emoji(status)

    created_at = workflow.get("created_at", "N/A")
    time_str = format_datetime(created_at) if created_at != "N/A" else "N/A"

    st.markdown(
        f"{emoji} `{workflow_id[:8]}...` | **{status}** | {current_node} | {time_str}"
    )
