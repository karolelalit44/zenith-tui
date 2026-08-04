"""Permission middleware — checks tool-level permissions before execution.

Two modes:
1. Callback mode (default): delegates to a callable `check(tool, params, ctx)`.
2. Service mode (HP-8): delegates to a `PermissionService`. Persisted deny
   rules are enforced directly from storage, without a UI round-trip.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from server.domain.domain import PermissionDecision
from server.permissions.service import PermissionService

from ..base import ToolContext, ToolMiddleware, ToolResult

# Callback signature: (tool_name, params, ctx) -> bool | ToolResult
PermissionCallback = Callable[[str, dict[str, Any], ToolContext], Awaitable[bool | ToolResult]]


class PermissionMiddleware(ToolMiddleware):
    """Delegates permission checks to a service or configurable callback.

    Service mode (HP-8): the middleware consults stored permission decisions
    only. A persisted deny rule blocks the tool without a UI round-trip; when
    no rule exists the call passes through (interactive confirmation is
    handled by the agent loop's own confirm callback).
    """

    def __init__(
        self,
        check: PermissionCallback | None = None,
        service: PermissionService | None = None,
    ) -> None:
        self._check = check
        self._service = service

    async def before_execute(
        self, name: str, params: dict[str, Any], ctx: ToolContext
    ) -> bool | ToolResult:
        if self._service is not None:
            try:
                decision = await self._service.get_decision(name, ctx.session_id or "")
            except Exception:
                return True  # Fail-open: service errors do not block execution
            if decision is None:
                return True  # no stored rule → interactive flow handles it
            if decision in (
                PermissionDecision.ALLOW,
                PermissionDecision.PERSISTENT_ALLOW,
            ):
                return True
            return ToolResult(
                success=False,
                error=f"Tool '{name}' denied by persisted permission policy",
            )
        if self._check is None:
            return True
        try:
            return await self._check(name, params, ctx)
        except Exception:
            # Fail-open: if the permission check itself errors, allow execution
            return True
