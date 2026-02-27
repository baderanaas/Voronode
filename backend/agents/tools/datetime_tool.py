"""
DateTimeTool - Current date/time and relative date calculations.

Critical tool for financial queries which are often time-sensitive.
Examples: "last month", "overdue", "this quarter", "30 days ago"
"""

import re
from backend.core.logging import get_logger
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from typing import Dict, Any

logger = get_logger(__name__)


class DateTimeTool:
    """
    Tool for date/time operations.

    Provides:
    - Current date and time
    - Relative date calculations (X days ago, last month, etc.)
    - Date ranges (this month, last quarter, etc.)
    - Timestamp formatting
    """

    def run(self, query: str = "", action: str = "", **kwargs) -> Dict[str, Any]:
        """
        Execute datetime operations.

        Args:
            query: User's original query (for context)
            action: Specific action to perform (e.g., "Get current date", "Calculate 30 days ago")
            **kwargs: Additional context (not used for datetime operations)

        Returns:
            Dictionary with date/time information
        """
        # Combine query and action for parsing
        text = f"{query} {action}".lower()
        now = datetime.now()

        logger.info("datetime_tool_executing", action=action[:50])

        # Pattern: "current date" or "today"
        if any(keyword in text for keyword in ["current date", "today", "what day"]):
            result = {
                "date": now.strftime("%Y-%m-%d"),
                "day_of_week": now.strftime("%A"),
                "timestamp": now.isoformat(),
                "formatted": now.strftime("%B %d, %Y"),
            }
            logger.info("datetime_current_date", date=result["date"])
            return result

        # Pattern: "current time" or "what time"
        if any(keyword in text for keyword in ["current time", "what time"]):
            result = {
                "time": now.strftime("%H:%M:%S"),
                "timestamp": now.isoformat(),
                "formatted": now.strftime("%I:%M %p"),
            }
            logger.info("datetime_current_time", time=result["time"])
            return result

        # Pattern: "X days ago"
        days_ago_match = re.search(r'(\d+)\s+days?\s+ago', text)
        if days_ago_match:
            days = int(days_ago_match.group(1))
            past_date = now - timedelta(days=days)
            result = {
                "date": past_date.strftime("%Y-%m-%d"),
                "days_ago": days,
                "formatted": past_date.strftime("%B %d, %Y"),
            }
            logger.info("datetime_days_ago", days=days, date=result["date"])
            return result

        # Pattern: "X weeks ago"
        weeks_ago_match = re.search(r'(\d+)\s+weeks?\s+ago', text)
        if weeks_ago_match:
            weeks = int(weeks_ago_match.group(1))
            past_date = now - timedelta(weeks=weeks)
            result = {
                "date": past_date.strftime("%Y-%m-%d"),
                "weeks_ago": weeks,
                "formatted": past_date.strftime("%B %d, %Y"),
            }
            logger.info("datetime_weeks_ago", weeks=weeks, date=result["date"])
            return result

        # Pattern: "last month" or "previous month"
        if any(keyword in text for keyword in ["last month", "previous month"]):
            first_day_this_month = now.replace(day=1)
            last_day_last_month = first_day_this_month - timedelta(days=1)
            first_day_last_month = last_day_last_month.replace(day=1)
            result = {
                "start_date": first_day_last_month.strftime("%Y-%m-%d"),
                "end_date": last_day_last_month.strftime("%Y-%m-%d"),
                "month": last_day_last_month.strftime("%B %Y"),
            }
            logger.info("datetime_last_month", month=result["month"])
            return result

        # Pattern: "this month"
        if "this month" in text:
            first_day = now.replace(day=1)
            result = {
                "start_date": first_day.strftime("%Y-%m-%d"),
                "end_date": now.strftime("%Y-%m-%d"),
                "month": now.strftime("%B %Y"),
            }
            logger.info("datetime_this_month", month=result["month"])
            return result

        # Pattern: "last quarter"
        if "last quarter" in text:
            current_quarter = (now.month - 1) // 3 + 1
            if current_quarter == 1:
                last_quarter_start = datetime(now.year - 1, 10, 1)
                last_quarter_end = datetime(now.year - 1, 12, 31)
            else:
                quarter_start_month = (current_quarter - 2) * 3 + 1
                last_quarter_start = datetime(now.year, quarter_start_month, 1)
                last_quarter_end = datetime(now.year, quarter_start_month + 2, 1) - timedelta(days=1)

            result = {
                "start_date": last_quarter_start.strftime("%Y-%m-%d"),
                "end_date": last_quarter_end.strftime("%Y-%m-%d"),
                "quarter": f"Q{current_quarter - 1 if current_quarter > 1 else 4} {last_quarter_start.year}",
            }
            logger.info("datetime_last_quarter", quarter=result["quarter"])
            return result

        # Pattern: "this quarter"
        if "this quarter" in text:
            current_quarter = (now.month - 1) // 3 + 1
            quarter_start_month = (current_quarter - 1) * 3 + 1
            quarter_start = datetime(now.year, quarter_start_month, 1)

            result = {
                "start_date": quarter_start.strftime("%Y-%m-%d"),
                "end_date": now.strftime("%Y-%m-%d"),
                "quarter": f"Q{current_quarter} {now.year}",
            }
            logger.info("datetime_this_quarter", quarter=result["quarter"])
            return result

        # Pattern: "last year"
        if "last year" in text:
            last_year = now.year - 1
            result = {
                "start_date": f"{last_year}-01-01",
                "end_date": f"{last_year}-12-31",
                "year": str(last_year),
            }
            logger.info("datetime_last_year", year=result["year"])
            return result

        # Pattern: "this year" or "year to date" or "YTD"
        if any(keyword in text for keyword in ["this year", "year to date", "ytd"]):
            result = {
                "start_date": f"{now.year}-01-01",
                "end_date": now.strftime("%Y-%m-%d"),
                "year": str(now.year),
            }
            logger.info("datetime_this_year", year=result["year"])
            return result

        # Pattern: "overdue" - any date before today
        if "overdue" in text:
            yesterday = now - timedelta(days=1)
            result = {
                "cutoff_date": yesterday.strftime("%Y-%m-%d"),
                "description": "Any date before today",
                "comparison": "less_than",
                "reference_date": now.strftime("%Y-%m-%d"),
            }
            logger.info("datetime_overdue", cutoff=result["cutoff_date"])
            return result

        # Default: return current date/time
        result = {
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "timestamp": now.isoformat(),
            "day_of_week": now.strftime("%A"),
            "formatted": now.strftime("%B %d, %Y at %I:%M %p"),
        }
        logger.info("datetime_default", date=result["date"])
        return result
