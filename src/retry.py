"""Retry decorator with exponential backoff and jitter."""

import functools
import logging
import random
import time
from collections.abc import Callable
from typing import Any, TypeVar

from src.exceptions import RetryExhaustedError

logger = logging.getLogger("invoice_automation.retry")

F = TypeVar("F", bound=Callable[..., Any])


def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    on_retry: Callable[[int, Exception], None] | None = None,
) -> Callable[[F], F]:
    """Decorator that retries a function with exponential backoff and jitter.

    Args:
        max_attempts: Maximum number of attempts (including the first).
        base_delay: Initial delay in seconds before the first retry.
        max_delay: Maximum delay cap in seconds.
        exponential_base: Base for exponential backoff calculation.
        retryable_exceptions: Tuple of exception types that trigger a retry.
        on_retry: Optional callback invoked before each retry with
            (attempt_number, exception).

    Returns:
        Decorated function with retry behavior.

    Raises:
        RetryExhaustedError: When all attempts have been exhausted.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as exc:
                    last_exception = exc

                    if attempt == max_attempts:
                        break

                    delay = min(
                        base_delay * (exponential_base ** (attempt - 1)),
                        max_delay,
                    )
                    # Add jitter: random value between 0 and delay
                    jittered_delay = delay * random.uniform(0.5, 1.0)

                    logger.warning(
                        "Attempt %d/%d for %s failed: %s. "
                        "Retrying in %.2fs.",
                        attempt,
                        max_attempts,
                        func.__name__,
                        str(exc),
                        jittered_delay,
                    )

                    if on_retry is not None:
                        on_retry(attempt, exc)

                    time.sleep(jittered_delay)

            assert last_exception is not None
            raise RetryExhaustedError(
                message=(
                    f"All {max_attempts} attempts exhausted for {func.__name__}"
                ),
                attempts=max_attempts,
                last_exception=last_exception,
            )

        return wrapper  # type: ignore[return-value]

    return decorator
