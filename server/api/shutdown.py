from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


class GracefulShutdown:
    def __init__(self) -> None:
        self._cleanup_funcs: list[Callable[[], Awaitable[None]]] = []
        self._shutdown_event = asyncio.Event()

    def register_cleanup(self, func: Callable[[], Awaitable[None]]) -> None:
        self._cleanup_funcs.append(func)

    @property
    def is_shutting_down(self) -> bool:
        return self._shutdown_event.is_set()

    async def shutdown(self) -> None:
        if self._shutdown_event.is_set():
            return
        self._shutdown_event.set()
        logger.info("Graceful shutdown initiated...")
        for func in self._cleanup_funcs:
            try:
                await func()
            except Exception as e:
                logger.error("Cleanup error: %s", e)
        logger.info("Graceful shutdown complete")
