"""Failure-isolation helpers for the persistence layer.

The rule (HP-1, "database failure isolation"): a database failure must never
crash the application or leak raw driver exceptions to handlers. Every
repository public method is wrapped so failures surface as a typed
``PersistenceError`` (see ``server/domain/errors.py``) and are logged with
full context via ``db_log``.
"""

from __future__ import annotations

import functools
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
    """Map a driver-level exception to a typed PersistenceError."""
    if isinstance(exc, PersistenceError):
        return exc
    if isinstance(exc, IntegrityError):
        return PersistenceIntegrityError(cause=exc)
    if isinstance(exc, (OperationalError, SQLAlchemyError)):
        return PersistenceOperationError(cause=exc)
    return PersistenceOperationError(cause=exc)


def safe_db(
    operation: str,
    *,
    table: str = "",
) -> Callable[[F], F]:
    """Decorate an async repository method with failure isolation + logging.

    The decorated method catches every exception, logs a structured
    ``db.<operation>`` line with `status=error`, and re-raises a typed
    :class:`PersistenceError`. Success is logged too.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            import time

            start = time.perf_counter()
            try:
                result = await func(self, *args, **kwargs)
                duration_ms = (time.perf_counter() - start) * 1000.0
                db_log(operation, table=table, status="ok", duration_ms=duration_ms)
                return result
            except Exception as e:
                duration_ms = (time.perf_counter() - start) * 1000.0
                db_log(
                    operation, table=table, status="error", duration_ms=duration_ms, error=str(e)
                )
                raise classify(e) from e

        return wrapper  # type: ignore[return-value]

    return decorator
