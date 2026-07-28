"""Permission middleware — checks tool-level permissions before execution.

In the default implementation this middleware is a pass-through.
A production deployment can supply a PermissionService via the constructor.
"""

from __future__ import annotations

from typing import Any, Callable, Awaitable

from ..base import ToolContext, ToolMiddleware, ToolResult


# Callback signature: (tool_name, params, ctx) -> bool | ToolResult
PermissionCallback = Callable[[str, dict[str, Any], ToolContext], Awaitable[bool | ToolResult]]


class PermissionMiddleware(ToolMiddleware):
    """Delegates permission checks to a configurable callback."""

    def __init__(self, check: PermissionCallback | None = None) -> None:
        self._check = check

    async def before_execute(
        self, name: str, params: dict[str, Any], ctx: ToolContext
    ) -> bool | ToolResult:
        if self._check is None:
            return True
        try:
            return await self._check(name, params, ctx)
        except Exception:
            # Fail-open: if the permission check itself errors, allow execution
            return True
