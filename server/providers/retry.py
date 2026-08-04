from __future__ import annotations

import asyncio
import logging
import os
import random
from collections.abc import Callable
from typing import Any

from server.domain.errors import ProviderError, RateLimitError, TimeoutError

logger = logging.getLogger(__name__)


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
_BASE_DELAY = _env_float("ZENITH_RETRY_BASE_DELAY", 0.125)
_MAX_DELAY = _env_float("ZENITH_RETRY_MAX_DELAY", 60.0)


async def retry_with_backoff(
    func: Callable[..., Any],
    *args: Any,
    max_retries: int = _MAX_RETRIES,
    base_delay: float = _BASE_DELAY,
    max_delay: float = _MAX_DELAY,
    retryable_errors: tuple[type[Exception], ...] = (RateLimitError, TimeoutError),
    **kwargs: Any,
) -> Any:
    last_exception: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except retryable_errors as e:
            last_exception = e
            if attempt == max_retries:
                break
            delay = _calculate_delay(e, attempt, base_delay, max_delay)
            logger.warning("Retry %d/%d after %.1fs: %s", attempt + 1, max_retries, delay, str(e))
            await asyncio.sleep(delay)
        except ProviderError:
            raise
        except Exception as e:
            last_exception = e
            if attempt == max_retries:
                break
            delay = _calculate_delay(e, attempt, base_delay, max_delay)
            logger.warning("Retry %d/%d after %.1fs: %s", attempt + 1, max_retries, delay, str(e))
            await asyncio.sleep(delay)
    raise last_exception


def _calculate_delay(error: Exception, attempt: int, base_delay: float, max_delay: float) -> float:
    if isinstance(error, RateLimitError) and error.retry_after is not None:
        return min(error.retry_after, max_delay)
    delay = base_delay * 2**attempt + random.uniform(0, 0.5)
    return min(delay, max_delay)
