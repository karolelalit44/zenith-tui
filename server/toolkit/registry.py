"""Tool registry — dispatches tool execution, enforces mode, runs middleware."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from .base import BaseTool, ToolContext, ToolMiddleware, ToolResult

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry of available tools with dispatch, mode enforcement, and middleware."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._middleware: list[ToolMiddleware] = []

    # ── registration ──────────────────────────────────────────────────────

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def register_middleware(self, middleware: ToolMiddleware) -> None:
        """Append middleware (executed in registration order)."""
        self._middleware.append(middleware)

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def list_tools_for_mode(
        self,
        mode: str,
        allowed_mcp: dict[str, list[str]] | None = None,
    ) -> list[str]:
        """Return tool names available in the given mode.

        allowed_mcp controls MCP tool visibility per mode (Crush-style):
          None = all MCPs allowed
          {}   = no MCPs allowed
          {"server": ["tool"]} = specific MCP tools
        """
        tools = []
        for name in self._tools:
            if not self._is_available_in_mode(name, mode):
                continue
            if name.startswith("mcp_") and not self._is_mcp_allowed(name, allowed_mcp):
                continue
            tools.append(name)
        return tools

    @staticmethod
    def _is_mcp_allowed(
        tool_name: str,
        allowed_mcp: dict[str, list[str]] | None,
    ) -> bool:
        """Check if an MCP tool is allowed by the allowed_mcp filter."""
        if allowed_mcp is None:
            return True  # None = all MCPs allowed
        # allowed_mcp is a dict: {"server": ["tool1", "tool2"]}
        # tool_name format: "mcp_<server_tool_name>"
        # We need to check if any server in allowed_mcp allows this tool
        for server, tools in allowed_mcp.items():
            # Could match by server prefix or exact tool name
            # The tool name is "mcp_<tool_name>" — we check if the suffix
            # matches any tool in the server's list, or if the server
            # allows all tools (wildcard)
            for t in tools:
                if t == "*":
                    return True  # Server allows all tools
                if tool_name == f"mcp_{t}":
                    return True
                # Also check for server-prefixed names like "mcp_server_tool"
                if tool_name == f"mcp_{server}_{t}":
                    return True
        return False

    # ── schema queries ────────────────────────────────────────────────────

    def get_schemas(self) -> list[dict]:
        """Return schema info for all registered tools."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "schema": t.get_schema(),
            }
            for t in self._tools.values()
        ]

    def get_schemas_for_mode(
        self,
        mode: str,
        allowed_mcp: dict[str, list[str]] | None = None,
        allowed_tools: list[str] | None = None,
    ) -> list[dict]:
        """Return schemas for tools available in the given mode and allowed_tools list."""
        schemas = []
        for s in self.get_schemas():
            name = s["name"]
            if not self._is_available_in_mode(name, mode):
                continue
            if allowed_tools is not None and name not in allowed_tools:
                continue
            if name.startswith("mcp_") and not self._is_mcp_allowed(name, allowed_mcp):
                continue
            schemas.append(s)
        return schemas

    def _is_available_in_mode(self, tool_name: str, mode: str) -> bool:
        tool = self.get(tool_name)
        if tool is None:
            return False
        modes = tool.modes
        return not (modes is not None and mode not in modes)

    # ── execution with middleware chain ────────────────────────────────────

    async def execute(
        self,
        tool_name: str,
        params: dict[str, Any],
        workspace_root: str,
        mode: str = "build",
        request_id: str | None = None,
        session_id: str | None = None,
        allowed_mcp: dict[str, list[str]] | None = None,
    ) -> ToolResult:
        """Execute a tool by name with mode enforcement and middleware chain."""
        tool = self.get(tool_name)
        if not tool:
            return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

        # Mode check
        if not self._is_available_in_mode(tool_name, mode):
            return ToolResult(
                success=False,
                error=f"Tool '{tool_name}' not available in '{mode}' mode",
            )

        # MCP filter check
        if tool_name.startswith("mcp_") and not self._is_mcp_allowed(tool_name, allowed_mcp):
            return ToolResult(
                success=False,
                error=f"MCP tool '{tool_name}' not allowed in this mode",
            )

        # Param validation
        if not tool.validate_params(params):
            return ToolResult(
                success=False,
                error=f"Invalid parameters for tool '{tool_name}'",
            )

        # Build context
        ctx = ToolContext(
            request_id=request_id or str(uuid.uuid4()),
            session_id=session_id,
            workspace_root=workspace_root,
            mode=mode,
            tool_name=tool_name,
        )

        # Middleware: before_execute
        for mw in self._middleware:
            try:
                outcome = await mw.before_execute(tool_name, params, ctx)
                if outcome is not True and isinstance(outcome, ToolResult):
                    # middleware returned a ToolResult — short-circuit
                    return outcome
                    # unexpected return — skip this middleware
            except Exception:
                logger.exception("Middleware before_execute failed: %s", type(mw).__name__)

        # Execute
        try:
            result = await tool.execute(params, workspace_root)
        except Exception as e:
            logger.exception("Tool execution failed: %s", tool_name)
            # Let middleware try to recover
            for mw in self._middleware:
                try:
                    recovered = await mw.on_error(tool_name, params, e, ctx)
                    if recovered is not None:
                        result = recovered
                        break
                except Exception:
                    logger.exception("Middleware on_error failed: %s", type(mw).__name__)
            else:
                # No middleware recovered — return error
                return ToolResult(success=False, error=str(e))

        # Middleware: after_execute
        for mw in self._middleware:
            try:
                result = await mw.after_execute(tool_name, params, result, ctx)
            except Exception:
                logger.exception("Middleware after_execute failed: %s", type(mw).__name__)

        return result
