"""
Circuit Breaker Pattern for Tool Execution.

Prevents repeated execution of failing tools and provides graceful degradation.
After N consecutive failures, the circuit "opens" and prevents further attempts
for a cooldown period.
"""

import time
from typing import Dict, Callable, Any
from enum import Enum
import structlog

logger = structlog.get_logger()


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"      # Blocking calls due to failures
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """
    Circuit breaker for tool execution.

    States:
    - CLOSED: Normal operation, calls go through
    - OPEN: Too many failures, calls blocked
    - HALF_OPEN: Testing recovery, limited calls allowed

    Example:
        breaker = CircuitBreaker(failure_threshold=3, timeout=60)
        result = breaker.call(lambda: risky_operation())
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: int = 60,
        expected_exception: type = Exception,
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            timeout: Seconds to wait before attempting recovery (half-open)
            expected_exception: Exception type to catch (default: Exception)
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.expected_exception = expected_exception

        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.

        Args:
            func: Function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Function result if successful

        Raises:
            CircuitOpenError: If circuit is open (too many failures)
            Exception: Original exception from func if circuit is closed
        """
        if self.state == CircuitState.OPEN:
            # Check if timeout has passed
            if self._should_attempt_reset():
                logger.info("circuit_breaker_half_open", timeout_passed=True)
                self.state = CircuitState.HALF_OPEN
            else:
                logger.warning("circuit_breaker_open", failures=self.failure_count)
                raise CircuitOpenError(
                    f"Circuit breaker is OPEN after {self.failure_count} failures. "
                    f"Try again in {self._remaining_timeout():.0f} seconds."
                )

        try:
            # Execute function
            result = func(*args, **kwargs)

            # Success! Reset failure count
            if self.state == CircuitState.HALF_OPEN:
                logger.info("circuit_breaker_recovered")
                self.state = CircuitState.CLOSED
                self.failure_count = 0

            return result

        except self.expected_exception as e:
            # Failure! Increment counter
            self.failure_count += 1
            self.last_failure_time = time.time()

            logger.warning(
                "circuit_breaker_failure",
                failure_count=self.failure_count,
                threshold=self.failure_threshold,
            )

            # Open circuit if threshold reached
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                logger.error(
                    "circuit_breaker_opened",
                    failures=self.failure_count,
                    timeout=self.timeout,
                )

            # Re-raise original exception
            raise

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        if self.last_failure_time is None:
            return True
        return time.time() - self.last_failure_time >= self.timeout

    def _remaining_timeout(self) -> float:
        """Calculate remaining timeout in seconds."""
        if self.last_failure_time is None:
            return 0
        elapsed = time.time() - self.last_failure_time
        return max(0, self.timeout - elapsed)

    def reset(self):
        """Manually reset circuit breaker to CLOSED state."""
        logger.info("circuit_breaker_manual_reset")
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open and blocking calls."""
    pass


class ToolCircuitBreakerManager:
    """
    Manages circuit breakers for multiple tools.

    Each tool gets its own circuit breaker to prevent one failing tool
    from affecting others.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        timeout: int = 30,
    ):
        """
        Initialize manager.

        Args:
            failure_threshold: Failures before opening circuit
            timeout: Cooldown period in seconds
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.breakers: Dict[str, CircuitBreaker] = {}

    def get_breaker(self, tool_name: str) -> CircuitBreaker:
        """
        Get or create circuit breaker for a tool.

        Args:
            tool_name: Name of the tool

        Returns:
            CircuitBreaker instance for this tool
        """
        if tool_name not in self.breakers:
            self.breakers[tool_name] = CircuitBreaker(
                failure_threshold=self.failure_threshold,
                timeout=self.timeout,
            )
        return self.breakers[tool_name]

    def reset_all(self):
        """Reset all circuit breakers."""
        for breaker in self.breakers.values():
            breaker.reset()

    def get_status(self) -> Dict[str, Dict[str, Any]]:
        """
        Get status of all circuit breakers.

        Returns:
            Dict mapping tool names to their breaker status
        """
        return {
            tool_name: {
                "state": breaker.state.value,
                "failure_count": breaker.failure_count,
                "last_failure": breaker.last_failure_time,
            }
            for tool_name, breaker in self.breakers.items()
        }
