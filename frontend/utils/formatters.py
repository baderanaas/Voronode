"""
Data Formatting Utilities

Helper functions for displaying data in the Streamlit UI.
"""

from datetime import datetime
from typing import Any, Dict, List
from decimal import Decimal


def format_currency(amount: float | Decimal | str) -> str:
    """Format amount as currency."""
    try:
        value = float(amount) if not isinstance(amount, float) else amount
        return f"${value:,.2f}"
    except (ValueError, TypeError):
        return "$0.00"


def format_percentage(value: float | Decimal | str) -> str:
    """Format value as percentage."""
    try:
        pct = float(value) if not isinstance(value, float) else value
        return f"{pct:.1f}%"
    except (ValueError, TypeError):
        return "0.0%"


def format_datetime(dt: str | datetime) -> str:
    """Format datetime for display."""
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except ValueError:
            return dt

    return dt.strftime("%Y-%m-%d %H:%M:%S")


def format_date(dt: str | datetime) -> str:
    """Format date only."""
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except ValueError:
            return dt

    return dt.strftime("%Y-%m-%d")


def format_duration(seconds: float) -> str:
    """Format duration in seconds to human-readable string."""
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def get_severity_color(severity: str) -> str:
    """Get color for severity level."""
    colors = {
        "low": "#90EE90",      # Light green
        "medium": "#FFD700",   # Gold
        "high": "#FF6B6B",     # Light red
        "critical": "#DC143C", # Crimson
    }
    return colors.get(severity.lower(), "#808080")


def get_status_emoji(status: str) -> str:
    """Get emoji for workflow status."""
    emojis = {
        "processing": "⚙️",
        "completed": "✅",
        "quarantined": "⚠️",
        "failed": "❌",
        "pending": "⏳",
    }
    return emojis.get(status.lower(), "❓")


def format_anomaly_type(anomaly_type: str) -> str:
    """Format anomaly type for display."""
    # Convert snake_case to Title Case
    return anomaly_type.replace("_", " ").title()


def truncate_text(text: str, max_length: int = 50) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def format_file_size(size_bytes: int) -> str:
    """Format file size in bytes to human-readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def format_list(items: List[Any], separator: str = ", ") -> str:
    """Format list as comma-separated string."""
    return separator.join(str(item) for item in items)


def format_dict_table(data: Dict[str, Any]) -> str:
    """Format dictionary as markdown table."""
    if not data:
        return "No data"

    lines = ["| Key | Value |", "|-----|-------|"]
    for key, value in data.items():
        # Format key
        formatted_key = key.replace("_", " ").title()

        # Format value based on type
        if isinstance(value, (float, Decimal)) and "amount" in key.lower():
            formatted_value = format_currency(value)
        elif isinstance(value, (float, Decimal)) and "rate" in key.lower():
            formatted_value = format_percentage(value)
        elif isinstance(value, datetime):
            formatted_value = format_datetime(value)
        elif isinstance(value, list):
            formatted_value = format_list(value)
        else:
            formatted_value = str(value)

        lines.append(f"| {formatted_key} | {formatted_value} |")

    return "\n".join(lines)


def get_anomaly_icon(anomaly_type: str) -> str:
    """Get icon for anomaly type."""
    icons = {
        "duplicate": "📋",
        "price_spike": "📈",
        "missing_contract": "📄",
        "date_mismatch": "📅",
        "amount_discrepancy": "💰",
        "retention_violation": "⚖️",
        "price_mismatch": "💲",
        "billing_cap_exceeded": "🚫",
        "scope_violation": "🔍",
    }
    return icons.get(anomaly_type, "⚠️")
