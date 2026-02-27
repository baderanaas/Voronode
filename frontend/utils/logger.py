"""
Frontend logging — imports from the shared voronode_logging package.

Usage (app.py entry point):
    from utils.logger import setup_frontend_logging
    setup_frontend_logging()

Usage (any page / component):
    from utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("page_loaded")
    logger.error("api_call_failed", error=exc)
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path so voronode_logging is importable
_project_root = Path(__file__).parent.parent.parent  # .../Voronode/
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from voronode_logging import (
    VoronodeLogger,
    get_logger,
    LogContext,
    LogLevel,
    correlation_id_var,
    log_context_var,
)

__all__ = [
    "VoronodeLogger",
    "get_logger",
    "LogContext",
    "LogLevel",
    "setup_frontend_logging",
    "correlation_id_var",
    "log_context_var",
]


def setup_frontend_logging(level: str = "INFO") -> None:
    """Configure structured logging for the Streamlit frontend.

    Safe to call multiple times — VoronodeLogger.configure() resets the
    handler each call, so repeated Streamlit reruns are fine.
    """
    VoronodeLogger.configure("voronode-frontend", level=level)
