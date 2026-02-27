"""
voronode_logging — Structured logging for the Voronode platform.

Provides:
- VoronodeLogger: configure once, get per-module loggers anywhere
- get_logger(): drop-in for structlog.get_logger() (accepts key=value kwargs)
- CorrelationMiddleware: FastAPI middleware for request correlation IDs
- LogContext: context manager for temporary per-block log fields
- LogLevel, TimedOperation: supporting types

Usage — backend (main.py):
    from voronode_logging import VoronodeLogger, CorrelationMiddleware
    VoronodeLogger.configure("voronode-api", level=settings.log_level)
    app.add_middleware(CorrelationMiddleware)

Usage — any module:
    from voronode_logging import get_logger
    logger = get_logger(__name__)
    logger.info("event_name", key=value)
    logger.error("something_failed", error=exc)

Usage — rich API:
    logger = VoronodeLogger.get(MyClass)
    logger.info("msg", method="my_method", context={"jobId": 123})
    with logger.timed("operation"):
        ...
    with LogContext(user_id="abc"):
        logger.info("scoped")
"""

from .logger import (
    VoronodeLogger,
    VoronodeLoggerInstance,
    LogLevel,
    LogContext,
    TimedOperation,
    get_logger,
    correlation_id_var,
    log_context_var,
)
from .middleware import (
    CorrelationMiddleware,
    get_correlation_id,
    set_correlation_id,
    CORRELATION_ID_HEADER,
)

__all__ = [
    # Core logger
    "VoronodeLogger",
    "VoronodeLoggerInstance",
    "LogLevel",
    "LogContext",
    "TimedOperation",
    "get_logger",
    "correlation_id_var",
    "log_context_var",
    # FastAPI middleware
    "CorrelationMiddleware",
    "get_correlation_id",
    "set_correlation_id",
    "CORRELATION_ID_HEADER",
]
