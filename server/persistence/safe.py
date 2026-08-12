from __future__ import annotations

import functools
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from server.domain.errors import (
    PersistenceError,
    PersistenceIntegrityError,
    PersistenceOperationError,
)

from .logging import db_log

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def classify(exc: Exception) -> PersistenceError:
    if isinstance(exc, PersistenceError):
        return exc
    if isinstance(exc, IntegrityError):
        return PersistenceIntegrityError(cause=exc)
    if isinstance(exc, (OperationalError, SQLAlchemyError)):
        return PersistenceOperationError(cause=exc)
    return PersistenceOperationError(cause=exc)


def safe_db(operation: str, *, table: str = "") -> Callable[[F], F]:
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            import time

            start = time.perf_counter()
            try:
                result = await func(self, *args, **kwargs)
                duration_ms = (time.perf_counter() - start) * 1000.0
                db_log(
                    operation,
                    table=table,
                    status="ok",
                    duration_ms=duration_ms,
                    level=logging.DEBUG,
                )
                return result
            except Exception as e:
                duration_ms = (time.perf_counter() - start) * 1000.0
                db_log(
                    operation, table=table, status="error", duration_ms=duration_ms, error=str(e)
                )
                raise classify(e) from e

        return wrapper

    return decorator
