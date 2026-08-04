
from __future__ import annotations
import asyncio
import logging
import os
import random
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any, TypeVar
from server.domain.errors import ProviderError, RateLimitError, TimeoutError

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _env_int(key: str, default: int) -> int:
    val = os.environ.get(key, "").strip()
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    val = os.environ.get(key, "").strip()
    if not val:
        return default
    try:
        return float(val)
    except ValueError:
        return default


_MAX_RETRIES = _env_int("ZENITH_MAX_RETRIES", 3)
_STREAM_MAX_RETRIES = _env_int("ZENITH_STREAM_MAX_RETRIES", 3)
_BASE_DELAY = _env_float("ZENITH_RETRY_BASE_DELAY", 0.125)
_MAX_DELAY = _env_float("ZENITH_RETRY_MAX_DELAY", 60.0)


@dataclass
class RetryPolicy:

    max_retries: int = 3
    base_delay: float = 0.125
    max_delay: float = 60.0
    jitter: bool = True
    retryable_errors: tuple[type[Exception], ...] = (RateLimitError, TimeoutError)

    @classmethod
    def from_env(cls) -> RetryPolicy:
        return cls(max_retries=_MAX_RETRIES, base_delay=_BASE_DELAY, max_delay=_MAX_DELAY)

    @classmethod
    def for_stream(cls) -> RetryPolicy:
        return cls(max_retries=_STREAM_MAX_RETRIES, base_delay=_BASE_DELAY, max_delay=_MAX_DELAY)

    def calculate_delay(self, error: Exception, attempt: int) -> float:
        if isinstance(error, RateLimitError) and error.retry_after is not None:
            return min(error.retry_after, self.max_delay)

        delay = self.base_delay * (2**attempt)
        if self.jitter:
            delay += random.uniform(0, 0.5)
        return min(delay, self.max_delay)


async def retry_with_backoff(func: Callable[..., Any], *args: Any, max_retries: int = _MAX_RETRIES, base_delay: float = _BASE_DELAY, max_delay: float = _MAX_DELAY, retryable_errors: tuple[type[Exception], ...] = (RateLimitError, TimeoutError), policy: RetryPolicy | None = None, **kwargs: Any) -> Any:
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

            logger.warning("Retry %d/%d after %.1fs: %s", attempt + 1, max_retries, delay, str(e))
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

            logger.warning("Retry %d/%d after %.1fs: %s", attempt + 1, max_retries, delay, str(e))
            await asyncio.sleep(delay)

    raise last_exception


async def retry_stream(func: Callable[..., AsyncIterator[T]], *args: Any, max_retries: int = _STREAM_MAX_RETRIES, base_delay: float = _BASE_DELAY, max_delay: float = _MAX_DELAY, retryable_errors: tuple[type[Exception], ...] = (RateLimitError, TimeoutError), policy: RetryPolicy | None = None, **kwargs: Any) -> AsyncIterator[T]:
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
            logger.warning("Stream retry %d/%d after %.1fs: %s", attempt + 1, max_retries, delay, str(e))
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
            logger.warning("Stream retry %d/%d after %.1fs: %s", attempt + 1, max_retries, delay, str(e))
            await asyncio.sleep(delay)

    raise last_exception


def _calculate_delay(error: Exception, attempt: int, base_delay: float, max_delay: float) -> float:
    if isinstance(error, RateLimitError) and error.retry_after is not None:
        return min(error.retry_after, max_delay)

    delay = base_delay * (2**attempt) + random.uniform(0, 0.5)
    return min(delay, max_delay)
