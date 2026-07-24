"""Retry utility with exponential backoff for provider calls."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Callable, TypeVar

from zenith.core.errors import RateLimitError, TimeoutError, ProviderError

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def retry_with_backoff(
    func: Callable[..., Any],
    *args: Any,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    retryable_errors: tuple[type[Exception], ...] = (RateLimitError, TimeoutError),
    **kwargs: Any,
) -> Any:
    """Execute an async function with retry and exponential backoff.

    Args:
        func: Async function to call.
        *args: Positional arguments for func.
        max_retries: Maximum number of retry attempts (0 = no retries).
        base_delay: Base delay in seconds for the first retry.
        max_delay: Maximum delay between retries in seconds.
        retryable_errors: Tuple of exception types that trigger retries.
        **kwargs: Keyword arguments for func.

    Returns:
        The return value of func.

    Raises:
        The last exception if all retries are exhausted.
    """
    last_exception: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except retryable_errors as e:
            last_exception = e
            if attempt == max_retries:
                break

            delay = _calculate_delay(e, attempt, base_delay, max_delay)
            logger.warning(
                "Retry %d/%d after %.1fs: %s",
                attempt + 1,
                max_retries,
                delay,
                str(e),
            )
            await asyncio.sleep(delay)
        except ProviderError:
            raise
        except Exception as e:
            last_exception = e
            if attempt == max_retries:
                break

            delay = _calculate_delay(e, attempt, base_delay, max_delay)
            logger.warning(
                "Retry %d/%d after %.1fs: %s",
                attempt + 1,
                max_retries,
                delay,
                str(e),
            )
            await asyncio.sleep(delay)

    raise last_exception  # type: ignore[misc]


def _calculate_delay(
    error: Exception,
    attempt: int,
    base_delay: float,
    max_delay: float,
) -> float:
    """Calculate delay for the next retry attempt.

    Uses server-provided retry_after for rate limits, otherwise exponential backoff
    with jitter.
    """
    if isinstance(error, RateLimitError) and error.retry_after is not None:
        return min(error.retry_after, max_delay)

    delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
    return min(delay, max_delay)
