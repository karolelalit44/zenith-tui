"""Graceful shutdown — signal handling for clean server teardown."""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Callable, Awaitable, Any

logger = logging.getLogger(__name__)


class GracefulShutdown:
    """Manages graceful shutdown of async resources on SIGINT/SIGTERM."""

    def __init__(self) -> None:
        self._cleanup_funcs: list[Callable[[], Awaitable[None]]] = []
        self._shutdown_event = asyncio.Event()

    def register_cleanup(self, func: Callable[[], Awaitable[None]]) -> None:
        """Register an async cleanup function to call on shutdown."""
        self._cleanup_funcs.append(func)

    @property
    def is_shutting_down(self) -> bool:
        return self._shutdown_event.is_set()

    async def shutdown(self) -> None:
        """Execute all registered cleanup functions."""
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

    def install_signal_handlers(self, loop: asyncio.AbstractEventLoop) -> None:
        """Install SIGINT/SIGTERM handlers on the event loop."""
        if hasattr(loop, "add_signal_handler"):
            # Unix: add_signal_handler works
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(
                    sig,
                    lambda s=sig: asyncio.ensure_future(self._handle_signal(s)),
                )
            logger.info("Signal handlers installed (Unix)")
        else:
            # Windows: signal.signal works but not in async loops
            # Fall back to atexit or manual handling
            logger.info("Signal handlers deferred (Windows — use uvicorn shutdown)")

    async def _handle_signal(self, sig: signal.Signals) -> None:
        logger.info("Received signal %s", sig.name)
        await self.shutdown()
