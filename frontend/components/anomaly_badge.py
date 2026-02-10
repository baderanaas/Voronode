"""
Anomaly Badge Component

Display anomaly information with severity-based styling.
"""

import streamlit as st
from typing import Dict, Any, List
import sys
from pathlib import Path

# Add utils to path
utils_path = Path(__file__).parent.parent / "utils"
sys.path.insert(0, str(utils_path))

from formatters import (
    get_severity_color,
    format_anomaly_type,
    get_anomaly_icon,
)


def render_anomaly_badge(anomaly: Dict[str, Any], compact: bool = False):
    """
    Render an anomaly badge with severity color.

    Args:
        anomaly: Anomaly data dictionary with 'type', 'severity', 'message'
        compact: Whether to show compact version
    """
    anomaly_type = anomaly.get("type", "unknown")
    severity = anomaly.get("severity", "medium")
    message = anomaly.get("message", "No details")

    # Get styling
    color = get_severity_color(severity)
    icon = get_anomaly_icon(anomaly_type)
    formatted_type = format_anomaly_type(anomaly_type)

    if compact:
        # Compact badge (just icon and type)
        st.markdown(
            f'<span style="background-color: {color}; color: black; '
            f'padding: 0.2rem 0.5rem; border-radius: 0.3rem; '
            f'font-size: 0.9rem; font-weight: 500;">'
            f'{icon} {formatted_type}</span>',
            unsafe_allow_html=True,
        )
    else:
        # Full badge with message
        st.markdown(
            f'<div style="background-color: {color}; '
            f'padding: 0.75rem; border-radius: 0.5rem; '
            f'margin: 0.5rem 0; border-left: 4px solid {color};">'
            f'<strong>{icon} {formatted_type}</strong> '
            f'<span style="color: #333; margin-left: 0.5rem;">({severity.upper()})</span><br>'
            f'<span style="color: #555;">{message}</span>'
            f"</div>",
            unsafe_allow_html=True,
        )


def render_anomaly_list(anomalies: List[Dict[str, Any]], title: str = "Anomalies"):
    """
    Render a list of anomalies.

    Args:
        anomalies: List of anomaly dictionaries
        title: Section title
    """
    if not anomalies:
        st.info("✅ No anomalies detected")
        return

    st.markdown(f"### {title}")
    st.markdown(f"Found **{len(anomalies)}** anomalies:")

    for anomaly in anomalies:
        render_anomaly_badge(anomaly, compact=False)


def render_anomaly_summary(anomalies: List[Dict[str, Any]]):
    """
    Render a compact summary of anomalies by severity.

    Args:
        anomalies: List of anomaly dictionaries
    """
    if not anomalies:
        st.success("✅ No anomalies")
        return

    # Count by severity
    severity_counts = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    for anomaly in anomalies:
        severity = anomaly.get("severity", "medium").lower()
        severity_counts[severity] = severity_counts.get(severity, 0) + 1

    # Display counts
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if severity_counts["critical"] > 0:
            st.metric("Critical", severity_counts["critical"], delta_color="inverse")

    with col2:
        if severity_counts["high"] > 0:
            st.metric("High", severity_counts["high"], delta_color="inverse")

    with col3:
        if severity_counts["medium"] > 0:
            st.metric("Medium", severity_counts["medium"])

    with col4:
        if severity_counts["low"] > 0:
            st.metric("Low", severity_counts["low"])


def get_severity_level(anomalies: List[Dict[str, Any]]) -> str:
    """
    Get the highest severity level from a list of anomalies.

    Args:
        anomalies: List of anomaly dictionaries

    Returns:
        Highest severity level (critical, high, medium, low)
    """
    if not anomalies:
        return "none"

    severity_order = ["critical", "high", "medium", "low"]

    for severity in severity_order:
        if any(a.get("severity", "").lower() == severity for a in anomalies):
            return severity

    return "low"
