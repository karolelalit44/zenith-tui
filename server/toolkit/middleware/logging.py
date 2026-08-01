"""Logging middleware — logs tool execution timing and results."""

from __future__ import annotations

import logging
import time
from typing import Any

from ..base import ToolContext, ToolMiddleware, ToolResult

logger = logging.getLogger(__name__)


class LoggingMiddleware(ToolMiddleware):
    """Logs tool execution start, duration, and outcome."""

    async def before_execute(
        self, name: str, params: dict[str, Any], ctx: ToolContext
    ) -> bool | ToolResult:
        ctx.metadata["_start_time"] = time.monotonic()
        logger.info(
            "tool.execute.start name=%s request_id=%s mode=%s",
            name,
            ctx.request_id,
            ctx.mode,
        )
        return True

    async def after_execute(
        self,
        name: str,
        params: dict[str, Any],
        result: ToolResult,
        ctx: ToolContext,
    ) -> ToolResult:
        elapsed = time.monotonic() - ctx.metadata.get("_start_time", time.monotonic())
        logger.info(
            "tool.execute.done name=%s success=%s elapsed=%.3fs request_id=%s",
            name,
            result.success,
            elapsed,
            ctx.request_id,
        )
        return result

    async def on_error(
        self,
        name: str,
        params: dict[str, Any],
        error: Exception,
        ctx: ToolContext,
    ) -> ToolResult | None:
        elapsed = time.monotonic() - ctx.metadata.get("_start_time", time.monotonic())
        logger.error(
            "tool.execute.error name=%s error=%s elapsed=%.3fs request_id=%s",
            name,
            error,
            elapsed,
            ctx.request_id,
        )
        return None  # don't suppress — let registry handle it
