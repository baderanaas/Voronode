"""
Structured logger implementation for Voronode.

- Development (ENV=development / dev / local): colorized, human-readable output
- Production (any other ENV value): compact single-line JSON
"""

import json
import logging
import os
import sys
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional, Type, Union


# ── Context variables ─────────────────────────────────────────────────────────

correlation_id_var: ContextVar[Optional[str]] = ContextVar(
    "correlation_id", default=None
)
log_context_var: ContextVar[Dict[str, Any]] = ContextVar("log_context", default={})


# ── ANSI colors ───────────────────────────────────────────────────────────────


class _Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    DEBUG = "\033[36m"  # cyan
    INFO = "\033[32m"  # green
    WARNING = "\033[33m"  # yellow
    ERROR = "\033[31m"  # red
    TIMESTAMP = "\033[90m"  # gray
    SERVICE = "\033[35m"  # magenta
    CORR_ID = "\033[34m"  # blue
    KEY = "\033[90m"  # gray
    VALUE = "\033[97m"  # white

    LEVEL_MAP = {
        "DEBUG": DEBUG,
        "INFO": INFO,
        "WARN": WARNING,
        "WARNING": WARNING,
        "ERROR": ERROR,
    }


# ── Public types ──────────────────────────────────────────────────────────────


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class LogContext:
    """
    Context manager for temporary per-request log fields.

        with LogContext(user_id="abc", workflow_id="xyz"):
            logger.info("processing")   # all logs include those fields
    """

    def __init__(self, **kwargs: Any) -> None:
        self.new_context = kwargs
        self.previous_context: Dict[str, Any] = {}

    def __enter__(self) -> "LogContext":
        self.previous_context = log_context_var.get().copy()
        log_context_var.set({**self.previous_context, **self.new_context})
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Any,
    ) -> bool:
        log_context_var.set(self.previous_context)
        return False


# ── Formatter ─────────────────────────────────────────────────────────────────


class StructuredFormatter(logging.Formatter):
    """
    Log record formatter.

    - Development: colorized, multi-line, human-readable
    - Production: compact single-line JSON (machine-parseable)
    """

    def __init__(self, service_name: str) -> None:
        super().__init__()
        self.service_name = service_name
        self._is_dev = os.getenv("ENV", "development") in (
            "development",
            "dev",
            "local",
        )

    # ── build structured dict ─────────────────────────────────────────────

    def _build_entry(self, record: logging.LogRecord) -> Dict[str, Any]:
        # Normalize Python's "WARNING" → "WARN" for consistency with LogLevel enum
        level_name = record.levelname.upper()
        if level_name == "WARNING":
            level_name = "WARN"

        entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level_name,
            "service": self.service_name,
            "message": record.getMessage(),
        }

        # Class name from logger hierarchy  e.g.  voronode-api.orchestrator → orchestrator
        if record.name and record.name != "root":
            parts = record.name.split(".")
            entry["class"] = parts[-1] if parts else record.name

        # Correlation ID injected by CorrelationMiddleware
        correlation_id = correlation_id_var.get()
        if correlation_id:
            entry["correlationId"] = correlation_id

        # Optional method name passed via _log()
        if hasattr(record, "method_name") and record.method_name:
            entry["method"] = record.method_name

        # Merged context: global (LogContext) + per-call
        context = log_context_var.get().copy()
        if hasattr(record, "log_context") and record.log_context:
            context.update(record.log_context)
        if context:
            entry["context"] = context

        # Duration in ms (for timed operations)
        if hasattr(record, "duration") and record.duration is not None:
            entry["duration"] = record.duration

        # Exception info
        if record.exc_info:
            exc_type, exc_value, exc_tb = record.exc_info
            entry["error"] = {
                "type": exc_type.__name__ if exc_type else "Unknown",
                "message": str(exc_value) if exc_value else "",
            }
            if self._is_dev:
                import traceback

                entry["error"]["stack"] = "".join(
                    traceback.format_exception(exc_type, exc_value, exc_tb)
                )

        return entry

    # ── dev pretty-printer ────────────────────────────────────────────────

    @staticmethod
    def _pretty(entry: Dict[str, Any]) -> str:
        C = _Colors
        level = entry.get("level", "INFO")
        level_color = C.LEVEL_MAP.get(level, C.INFO)

        ts_raw = entry.get("timestamp", "")
        try:
            ts = ts_raw.split("T")[1][:12]  # HH:MM:SS.mmm
        except (IndexError, AttributeError):
            ts = ts_raw

        level_badge = f"{level_color}{C.BOLD}{level:<5}{C.RESET}"
        parts = [f"{C.TIMESTAMP}{ts}{C.RESET}", level_badge]

        service = entry.get("service", "")
        if service:
            parts.append(f"{C.SERVICE}[{service}]{C.RESET}")

        if "class" in entry:
            location = entry["class"]
            if "method" in entry:
                location += f".{entry['method']}"
            parts.append(f"{C.BOLD}{location}{C.RESET}")

        parts.append(f"── {entry.get('message', '')}")
        lines = ["  ".join(parts)]

        corr = entry.get("correlationId")
        if corr:
            lines.append(
                f"    {C.KEY}correlationId:{C.RESET} {C.CORR_ID}{corr}{C.RESET}"
            )

        dur = entry.get("duration")
        if dur is not None:
            lines.append(f"    {C.KEY}duration:{C.RESET} {dur}ms")

        ctx = entry.get("context")
        if ctx:
            lines.append(f"    {C.KEY}context:{C.RESET}")
            for k, v in ctx.items():
                lines.append(f"      {C.KEY}{k}:{C.RESET} {C.VALUE}{v}{C.RESET}")

        err = entry.get("error")
        if err:
            lines.append(
                f"    {C.ERROR}{C.BOLD}error:{C.RESET} "
                f"{C.ERROR}{err.get('type', 'Unknown')}: {err.get('message', '')}{C.RESET}"
            )
            stack = err.get("stack")
            if stack:
                for sline in stack.strip().splitlines():
                    lines.append(f"      {C.DIM}{sline}{C.RESET}")

        return "\n".join(lines)

    # ── entry point ───────────────────────────────────────────────────────

    def format(self, record: logging.LogRecord) -> str:
        entry = self._build_entry(record)
        if self._is_dev:
            return self._pretty(entry)
        return json.dumps(entry, default=str)


# ── VoronodeLogger ────────────────────────────────────────────────────────────


class VoronodeLogger:
    """
    Structured logger for Voronode.

    Initialize once at startup:
        VoronodeLogger.configure("voronode-api", level=settings.log_level)

    Then get per-class/module loggers:
        logger = VoronodeLogger.get(MyClass)
        logger = VoronodeLogger.get("my_module")
    """

    _service_name: Optional[str] = None
    _root_logger: Optional[logging.Logger] = None
    _min_level: LogLevel = LogLevel.INFO

    # Map LogLevel → stdlib logging integer, avoiding the deprecated logging.WARN alias
    _LEVEL_TO_INT: Dict[str, int] = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARN": logging.WARNING,
        "ERROR": logging.ERROR,
    }

    @classmethod
    def configure(
        cls,
        service_name: str,
        level: Union[str, LogLevel] = LogLevel.INFO,
    ) -> logging.Logger:
        """Configure the root logger. Call once at application startup."""
        cls._service_name = service_name

        if isinstance(level, str):
            # Accept both "WARN" and "WARNING" from env vars / config
            normalized = level.upper()
            if normalized == "WARNING":
                normalized = "WARN"
            try:
                level = LogLevel(normalized)
            except ValueError:
                level = LogLevel.INFO
        cls._min_level = level

        logger = logging.getLogger(service_name)
        logger.setLevel(cls._LEVEL_TO_INT.get(level.value, logging.INFO))
        logger.handlers.clear()

        handler = logging.StreamHandler(sys.stdout)
        if hasattr(handler.stream, "reconfigure"):
            try:
                handler.stream.reconfigure(encoding="utf-8")
            except Exception:
                pass
        handler.setFormatter(StructuredFormatter(service_name))
        logger.addHandler(handler)
        logger.propagate = False

        cls._root_logger = logger
        return logger

    @classmethod
    def get(cls, context: Union[Type, str]) -> "VoronodeLoggerInstance":
        """Get a logger instance for a class or named context."""
        if cls._root_logger is None:
            cls.configure("voronode")

        name = context if isinstance(context, str) else context.__name__
        child_logger = cls._root_logger.getChild(name)
        return VoronodeLoggerInstance(child_logger, name)

    @classmethod
    def set_correlation_id(cls, correlation_id: str) -> None:
        """Set correlation ID for the current async context."""
        correlation_id_var.set(correlation_id)

    @classmethod
    def get_correlation_id(cls) -> Optional[str]:
        """Get current correlation ID."""
        return correlation_id_var.get()

    @classmethod
    def set_context(cls, **kwargs: Any) -> None:
        """Add fields included in all subsequent logs in this context."""
        current = log_context_var.get().copy()
        current.update(kwargs)
        log_context_var.set(current)

    @classmethod
    def clear_context(cls) -> None:
        """Clear the current log context."""
        log_context_var.set({})


class VoronodeLoggerInstance:
    """Logger bound to a specific class or module."""

    def __init__(self, logger: logging.Logger, class_name: str) -> None:
        self._logger = logger
        self._class_name = class_name

    def _log(
        self,
        level: int,
        message: str,
        method: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        error: Optional[Exception] = None,
        duration: Optional[int] = None,
    ) -> None:
        extra = {
            "method_name": method,
            "log_context": context if isinstance(context, dict) else {},
            "duration": duration,
        }
        if error:
            self._logger.log(level, message, exc_info=error, extra=extra)
        else:
            self._logger.log(level, message, extra=extra)

    def debug(
        self,
        message: str,
        method: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._log(logging.DEBUG, message, method, context)

    def info(
        self,
        message: str,
        method: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        duration: Optional[int] = None,
    ) -> None:
        self._log(logging.INFO, message, method, context, duration=duration)

    def warn(
        self,
        message: str,
        method: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._log(logging.WARNING, message, method, context)

    def warning(
        self,
        message: str,
        method: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.warn(message, method, context)

    def error(
        self,
        message: str,
        method: Optional[str] = None,
        error: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None,
        exc_info: Optional[bool] = None,
    ) -> None:
        if exc_info is True and error is None:
            exc = sys.exc_info()[1]
            if exc is not None:
                error = exc
        self._log(logging.ERROR, message, method, context, error)

    def timed(
        self, operation: str, context: Optional[Dict[str, Any]] = None
    ) -> "TimedOperation":
        """Context manager that logs start/completion and elapsed time."""
        return TimedOperation(self, operation, context)


class TimedOperation:
    """Context manager for timing and logging an operation."""

    def __init__(
        self,
        logger: VoronodeLoggerInstance,
        operation: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.logger = logger
        self.operation = operation
        self.context = context or {}
        self.start_time: float = 0

    def __enter__(self) -> "TimedOperation":
        self.start_time = time.time()
        self.logger.info(f"{self.operation} started", context=self.context)
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Any,
    ) -> bool:
        duration = int((time.time() - self.start_time) * 1000)
        if exc_type:
            self.logger.error(
                f"{self.operation} failed",
                error=exc_val if isinstance(exc_val, Exception) else None,
                context={**self.context, "duration": duration},
            )
        else:
            self.logger.info(
                f"{self.operation} completed",
                context=self.context,
                duration=duration,
            )
        return False


# ── Structlog-compatible shim ─────────────────────────────────────────────────


class _CompatLogger:
    """
    Drop-in for a structlog bound logger.

    Accepts structlog-style keyword calls:
        logger.info("event_name", key=value, key2=value2)
        logger.error("failed", error=exception_or_string)

    and converts them to VoronodeLoggerInstance with context dict.
    """

    def __init__(self, instance: VoronodeLoggerInstance) -> None:
        self._instance = instance

    def _extract(
        self, kwargs: Dict[str, Any]
    ) -> tuple[Optional[Exception], Optional[str], Optional[Dict[str, Any]]]:
        raw_error = kwargs.pop("error", None)
        error: Optional[Exception] = None
        if isinstance(raw_error, Exception):
            error = raw_error
        elif raw_error is not None:
            kwargs["error"] = str(raw_error)  # surface string errors in context

        method = kwargs.pop("method", None)
        return error, method, (kwargs or None)

    def debug(self, event: str, **kwargs: Any) -> None:
        error, method, ctx = self._extract(kwargs)
        self._instance.debug(event, method=method, context=ctx)

    def info(self, event: str, **kwargs: Any) -> None:
        error, method, ctx = self._extract(kwargs)
        self._instance.info(event, method=method, context=ctx)

    def warn(self, event: str, **kwargs: Any) -> None:
        error, method, ctx = self._extract(kwargs)
        self._instance.warn(event, method=method, context=ctx)

    def warning(self, event: str, **kwargs: Any) -> None:
        self.warn(event, **kwargs)

    def error(self, event: str, **kwargs: Any) -> None:
        error, method, ctx = self._extract(kwargs)
        self._instance.error(event, method=method, error=error, context=ctx)

    def exception(self, event: str, **kwargs: Any) -> None:
        exc = sys.exc_info()[1]
        if exc is not None:
            kwargs.setdefault("error", exc)
        self.error(event, **kwargs)


def get_logger(name: Optional[str] = None) -> _CompatLogger:
    """
    Drop-in replacement for structlog.get_logger().

        logger = get_logger(__name__)
        logger.info("event_name", key=value)
        logger.error("failed", error=exc)
    """
    class_name = name.split(".")[-1] if name and "." in name else (name or "app")
    return _CompatLogger(VoronodeLogger.get(class_name))
