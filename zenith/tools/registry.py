"""Tool registry — dispatches tool execution, enforces mode permissions."""

from __future__ import annotations

import logging
from typing import Any

from .base import BaseTool, ToolResult
from .permission import PermissionGate
from zenith.core.errors import ToolError, PermissionDenied

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry of available tools with dispatch, mode enforcement, and permission gating."""

    def __init__(self, permission_gate: PermissionGate | None = None) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._gate = permission_gate or PermissionGate()

    @property
    def gate(self) -> PermissionGate:
        return self._gate

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def get_schemas(self) -> list[dict]:
        """Return schema info for all registered tools."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "permission_level": t.permission_level,
                "schema": t.get_schema(),
            }
            for t in self._tools.values()
        ]

    def get_schemas_for_mode(self, mode: str) -> list[dict]:
        """Return schemas for tools available in the given mode."""
        return [
            s for s in self.get_schemas()
            if self._is_available_in_mode(s["name"], mode)
        ]

    def _is_available_in_mode(self, tool_name: str, mode: str) -> bool:
        tool = self.get(tool_name)
        if tool is None:
            return False
        if tool.requires_mode and tool.requires_mode != mode:
            return False
        return True

    async def execute(
        self,
        tool_name: str,
        params: dict[str, Any],
        workspace_root: str,
        mode: str = "build",
    ) -> ToolResult:
        """Execute a tool by name with mode enforcement and permission gating."""
        tool = self.get(tool_name)
        if not tool:
            return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

        if tool.requires_mode and tool.requires_mode != mode:
            return ToolResult(
                success=False,
                error=f"Tool '{tool_name}' not available in '{mode}' mode",
            )

        if not await self._gate.check(tool):
            raise PermissionDenied(tool_name)

        if not tool.validate_params(params):
            return ToolResult(
                success=False,
                error=f"Invalid parameters for tool '{tool_name}'",
            )

        try:
            return await tool.execute(params, workspace_root)
        except PermissionDenied:
            raise
        except Exception as e:
            logger.exception("Tool execution failed: %s", tool_name)
            return ToolResult(success=False, error=str(e))
