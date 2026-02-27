"""
FastAPI / Starlette middleware for correlation ID propagation and HTTP request logging.
"""

import time
import uuid
from typing import Callable, Optional

from .logger import VoronodeLogger, VoronodeLoggerInstance, correlation_id_var, log_context_var

CORRELATION_ID_HEADER = "X-Correlation-ID"


def get_correlation_id() -> Optional[str]:
    """Return the correlation ID for the current request context."""
    return correlation_id_var.get()


def set_correlation_id(correlation_id: str) -> None:
    """Manually set the correlation ID for the current async context."""
    correlation_id_var.set(correlation_id)


try:
    from fastapi import Request, Response
    from starlette.middleware.base import BaseHTTPMiddleware

    class CorrelationMiddleware(BaseHTTPMiddleware):
        """
        Middleware that:
        1. Extracts or generates a correlation ID per request
        2. Propagates it via contextvars so every log line includes it
        3. Logs HTTP request start and completion with timing
        4. Echoes the correlation ID back in response headers

        Add to your FastAPI app:
            app.add_middleware(CorrelationMiddleware)
        """

        def __init__(self, app) -> None:
            super().__init__(app)
            self._http_logger: Optional[VoronodeLoggerInstance] = None

        @property
        def _logger(self) -> Optional[VoronodeLoggerInstance]:
            if self._http_logger is None:
                try:
                    self._http_logger = VoronodeLogger.get("HTTP")
                except RuntimeError:
                    return None
            return self._http_logger

        async def dispatch(self, request: Request, call_next: Callable) -> Response:
            # Honour incoming correlation ID or mint a new one
            correlation_id = request.headers.get(
                CORRELATION_ID_HEADER, f"req-{uuid.uuid4()}"
            )
            correlation_id_var.set(correlation_id)
            log_context_var.set({})

            if self._logger:
                self._logger.info(
                    "Request received",
                    method="dispatch",
                    context={
                        "method": request.method,
                        "path": request.url.path,
                        "query": dict(request.query_params) or None,
                    },
                )

            start_time = time.time()
            try:
                response = await call_next(request)
                duration = int((time.time() - start_time) * 1000)

                if self._logger:
                    log_fn = (
                        self._logger.warn
                        if response.status_code >= 400
                        else self._logger.info
                    )
                    log_fn(
                        "Request completed",
                        method="dispatch",
                        context={
                            "method": request.method,
                            "path": request.url.path,
                            "statusCode": response.status_code,
                            "duration": duration,
                        },
                    )

                response.headers[CORRELATION_ID_HEADER] = correlation_id
                return response

            except Exception as e:
                duration = int((time.time() - start_time) * 1000)
                if self._logger:
                    self._logger.error(
                        "Request failed",
                        method="dispatch",
                        error=e,
                        context={
                            "method": request.method,
                            "path": request.url.path,
                            "duration": duration,
                        },
                    )
                raise

            finally:
                correlation_id_var.set(None)
                log_context_var.set({})

except ImportError:

    class CorrelationMiddleware:  # type: ignore
        """Stub — FastAPI/Starlette is not installed."""

        def __init__(self, *args, **kwargs) -> None:
            raise ImportError(
                "fastapi and starlette are required to use CorrelationMiddleware"
            )
