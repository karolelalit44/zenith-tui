
from __future__ import annotations
import logging
from typing import Any
from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class McpToolWrapper(BaseTool):

    @property
    def risk_level(self) -> str:
        return "low"

    def __init__(self, mcp_tool: dict, mcp_client: Any, server_name: str = "") -> None:
        self._mcp_tool = mcp_tool
        self._mcp_client = mcp_client
        self.server_name = server_name
        raw = mcp_tool.get("name", "unknown")
        self.name = f"mcp_{server_name}_{raw}" if server_name else f"mcp_{raw}"
        self.description = mcp_tool.get("description", "")

    def get_schema(self) -> dict:
        schema = self._mcp_tool.get("inputSchema", {"type": "object", "properties": {}})
        return schema

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        try:
            result = await self._mcp_client.call_tool(self._mcp_tool["name"], params)
        except Exception as e:
            return ToolResult(success=False, error=f"MCP tool call failed: {e}")

        if isinstance(result, dict):
            is_error = result.get("isError", False)
            contents = result.get("content", [])
            text_parts = []
            for c in contents:
                if isinstance(c, dict) and c.get("type") == "text":
                    text_parts.append(c.get("text", ""))
                elif isinstance(c, str):
                    text_parts.append(c)
            output = "\n".join(text_parts) if text_parts else str(result)
            return ToolResult(success=not is_error, output=output, error=output if is_error else "")
        return ToolResult(success=True, output=str(result))
