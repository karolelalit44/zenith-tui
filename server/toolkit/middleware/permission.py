
from __future__ import annotations
from collections.abc import Awaitable, Callable
from typing import Any
from server.domain.domain import PermissionDecision
from server.permissions.service import PermissionService
from ..base import ToolContext, ToolMiddleware, ToolResult

PermissionCallback = Callable[[str, dict[str, Any], ToolContext], Awaitable[bool | ToolResult]]


class PermissionMiddleware(ToolMiddleware):

    def __init__(self, check: PermissionCallback | None = None, service: PermissionService | None = None) -> None:
        self._check = check
        self._service = service

    async def before_execute(self, name: str, params: dict[str, Any], ctx: ToolContext) -> bool | ToolResult:
        if self._service is not None:
            try:
                decision = await self._service.get_decision(name, ctx.session_id or "")
            except Exception:
                return True
            if decision is None:
                return True
            if decision in (PermissionDecision.ALLOW, PermissionDecision.PERSISTENT_ALLOW):
                return True
            return ToolResult(success=False, error=f"Tool '{name}' denied by persisted permission policy")
        if self._check is None:
            return True
        try:
            return await self._check(name, params, ctx)
        except Exception:
            return True
