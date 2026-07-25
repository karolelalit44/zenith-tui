"""Retry utility with exponential backoff for provider calls."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, AsyncIterator, Callable, TypeVar

from zenith.core.errors import RateLimitError, TimeoutError, ProviderError
from zenith.config.env import require_int, require_float

logger = logging.getLogger(__name__)

T = TypeVar("T")

_MAX_RETRIES = require_int("ZENITH_MAX_RETRIES")
_STREAM_MAX_RETRIES = require_int("ZENITH_STREAM_MAX_RETRIES")
_BASE_DELAY = require_float("ZENITH_RETRY_BASE_DELAY")
_MAX_DELAY = require_float("ZENITH_RETRY_MAX_DELAY")


async def retry_with_backoff(
    func: Callable[..., Any],
    *args: Any,
    max_retries: int = _MAX_RETRIES,
    base_delay: float = _BASE_DELAY,
    max_delay: float = _MAX_DELAY,
    retryable_errors: tuple[type[Exception], ...] = (RateLimitError, TimeoutError),
    **kwargs: Any,
) -> Any:
    """Execute an async function with retry and exponential backoff."""
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


async def retry_stream(
    func: Callable[..., AsyncIterator[T]],
    *args: Any,
    max_retries: int = _STREAM_MAX_RETRIES,
    base_delay: float = _BASE_DELAY,
    max_delay: float = _MAX_DELAY,
    retryable_errors: tuple[type[Exception], ...] = (RateLimitError, TimeoutError),
    **kwargs: Any,
) -> AsyncIterator[T]:
    """Execute an async generator function with retry on failure.

    Unlike retry_with_backoff, this is designed for streaming responses.
    On retryable errors, yields nothing from the failed attempt and retries.
    On non-retryable errors, re-raises immediately.
    """
    last_exception: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            async for item in func(*args, **kwargs):
                yield item
            return  # success — stop retrying
        except retryable_errors as e:
            last_exception = e
            if attempt == max_retries:
                break
            delay = _calculate_delay(e, attempt, base_delay, max_delay)
            logger.warning(
                "Stream retry %d/%d after %.1fs: %s",
                attempt + 1, max_retries, delay, str(e),
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
                "Stream retry %d/%d after %.1fs: %s",
                attempt + 1, max_retries, delay, str(e),
            )
            await asyncio.sleep(delay)

    raise last_exception  # type: ignore[misc]


def _calculate_delay(
    error: Exception,
    attempt: int,
    base_delay: float,
    max_delay: float,
) -> float:
    """Calculate delay for the next retry attempt."""
    if isinstance(error, RateLimitError) and error.retry_after is not None:
        return min(error.retry_after, max_delay)

    delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
    return min(delay, max_delay)
