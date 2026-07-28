"""Retry utility with exponential backoff for provider calls.

Provides:
- retry_with_backoff: async function retry with backoff
- retry_stream: async generator retry with backoff
- RetryPolicy: configurable retry strategy

Fixed: no longer crashes at import time when env vars are missing.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, TypeVar

from core.errors import RateLimitError, TimeoutError, ProviderError

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _env_int(key: str, default: int) -> int:
    """Read an int env var, returning default if missing or invalid."""
    val = os.environ.get(key, "").strip()
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    """Read a float env var, returning default if missing or invalid."""
    val = os.environ.get(key, "").strip()
    if not val:
        return default
    try:
        return float(val)
    except ValueError:
        return default


# Defaults (safe — no crash at import time)
_MAX_RETRIES = _env_int("ZENITH_MAX_RETRIES", 3)
_STREAM_MAX_RETRIES = _env_int("ZENITH_STREAM_MAX_RETRIES", 3)
_BASE_DELAY = _env_float("ZENITH_RETRY_BASE_DELAY", 0.5)
_MAX_DELAY = _env_float("ZENITH_RETRY_MAX_DELAY", 10.0)


@dataclass
class RetryPolicy:
    """Configurable retry strategy.

    Attributes:
        max_retries: Maximum number of retry attempts.
        base_delay: Base delay in seconds for exponential backoff.
        max_delay: Maximum delay cap in seconds.
        jitter: Whether to add random jitter to the delay.
        retryable_errors: Tuple of exception types that trigger a retry.
    """
    max_retries: int = 3
    base_delay: float = 0.5
    max_delay: float = 10.0
    jitter: bool = True
    retryable_errors: tuple[type[Exception], ...] = (RateLimitError, TimeoutError)

    @classmethod
    def from_env(cls) -> RetryPolicy:
        """Create a RetryPolicy from environment variables."""
        return cls(
            max_retries=_MAX_RETRIES,
            base_delay=_BASE_DELAY,
            max_delay=_MAX_DELAY,
        )

    @classmethod
    def for_stream(cls) -> RetryPolicy:
        """Create a RetryPolicy optimized for streaming."""
        return cls(
            max_retries=_STREAM_MAX_RETRIES,
            base_delay=_BASE_DELAY,
            max_delay=_MAX_DELAY,
        )

    def calculate_delay(self, error: Exception, attempt: int) -> float:
        """Calculate delay for the next retry attempt."""
        if isinstance(error, RateLimitError) and error.retry_after is not None:
            return min(error.retry_after, self.max_delay)

        delay = self.base_delay * (2 ** attempt)
        if self.jitter:
            delay += random.uniform(0, 0.5)
        return min(delay, self.max_delay)


async def retry_with_backoff(
    func: Callable[..., Any],
    *args: Any,
    max_retries: int = _MAX_RETRIES,
    base_delay: float = _BASE_DELAY,
    max_delay: float = _MAX_DELAY,
    retryable_errors: tuple[type[Exception], ...] = (RateLimitError, TimeoutError),
    policy: RetryPolicy | None = None,
    **kwargs: Any,
) -> Any:
    """Execute an async function with retry and exponential backoff.

    If `policy` is provided, it overrides the individual parameters.
    """
    if policy is not None:
        max_retries = policy.max_retries
        base_delay = policy.base_delay
        max_delay = policy.max_delay
        retryable_errors = policy.retryable_errors

    last_exception: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except retryable_errors as e:
            last_exception = e
            if attempt == max_retries:
                break

            if policy is not None:
                delay = policy.calculate_delay(e, attempt)
            else:
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

            if policy is not None:
                delay = policy.calculate_delay(e, attempt)
            else:
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
    policy: RetryPolicy | None = None,
    **kwargs: Any,
) -> AsyncIterator[T]:
    """Execute an async generator function with retry on failure.

    If `policy` is provided, it overrides the individual parameters.
    """
    if policy is not None:
        max_retries = policy.max_retries
        base_delay = policy.base_delay
        max_delay = policy.max_delay
        retryable_errors = policy.retryable_errors

    last_exception: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            async for item in func(*args, **kwargs):
                yield item
            return
        except retryable_errors as e:
            last_exception = e
            if attempt == max_retries:
                break
            if policy is not None:
                delay = policy.calculate_delay(e, attempt)
            else:
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
            if policy is not None:
                delay = policy.calculate_delay(e, attempt)
            else:
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
