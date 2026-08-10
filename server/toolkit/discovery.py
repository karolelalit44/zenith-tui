from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from server.config.constants import (
    CAPABILITY_TOOL_DISCOVERY,
    CONCURRENCY_GROUP_READONLY,
    DISCOVER_CAPABILITIES_TOOL,
    GET_TOOL_DEFINITION_TOOL,
    PERMISSION_READ,
    RISK_SAFE,
    TOOL_DOMAIN_DISCOVERY,
)

from .base import BaseTool, ToolResult
from .catalog import build_catalog

if TYPE_CHECKING:
    from .registry import ToolRegistry


def serialize_tool_definition(tool: BaseTool) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.get_schema(),
        },
    }


class DiscoverCapabilitiesTool(BaseTool):
    name = DISCOVER_CAPABILITIES_TOOL
    description = (
        "List every capability and the tools that provide each, with risk and "
        "read-only status. Use it to discover what you can do, then "
        "get_tool_definition for any tool you want to use."
    )
    capability_id = CAPABILITY_TOOL_DISCOVERY
    read_only = True
    concurrency_group = CONCURRENCY_GROUP_READONLY
    permission_scope = PERMISSION_READ
    domains = (TOOL_DOMAIN_DISCOVERY,)
    search_terms = ("discover", "list tools", "capabilities", "available", "what can you do")
    risk_level = RISK_SAFE

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        super().__init__()
        self._registry = registry

    def get_schema(self) -> dict:
        return {"type": "object", "properties": {}}

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        if self._registry is None:
            return ToolResult(success=False, error="Tool discovery unavailable: no registry")
        catalog = build_catalog()
        lines = []
        capability_ids = []
        for capability in catalog.descriptors():
            tool_names = sorted(
                name
                for name in self._registry.list_tools()
                if (tool := self._registry.get(name)) and tool.capability_id == capability.id
            )
            if not tool_names:
                continue
            capability_ids.append(capability.id)
            flags = "read-only" if capability.read_only else "mutating"
            lines.append(
                f"- {capability.id} [{flags}]: {capability.short_description} — "
                f"tools: {', '.join(tool_names)}"
            )
        lines.append(
            "Call get_tool_definition('<tool_name>') to load the full schema for any tool "
            "you need before using it."
        )
        return ToolResult(
            success=True, output="\n".join(lines), metadata={"capabilities": capability_ids}
        )


class GetToolDefinitionTool(BaseTool):
    name = GET_TOOL_DEFINITION_TOOL
    description = (
        "Load the full schema and metadata for a tool so it can be called. Returns "
        "its JSON parameters, description, risk, read-only status, and mode availability."
    )
    capability_id = CAPABILITY_TOOL_DISCOVERY
    read_only = True
    concurrency_group = CONCURRENCY_GROUP_READONLY
    permission_scope = PERMISSION_READ
    domains = (TOOL_DOMAIN_DISCOVERY,)
    search_terms = ("get tool", "tool schema", "tool definition", "how to use tool", "load tool")
    risk_level = RISK_SAFE

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        super().__init__()
        self._registry = registry

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string",
                    "description": "Name of the tool whose definition to load",
                },
            },
            "required": ["tool_name"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        tool_name = params.get("tool_name", "")
        if not tool_name:
            return ToolResult(success=False, error="No tool_name provided")
        if self._registry is None:
            return ToolResult(success=False, error="Tool discovery unavailable: no registry")
        tool = self._registry.get(tool_name)
        if tool is None:
            return ToolResult(
                success=False,
                error=f"Unknown tool: '{tool_name}'",
                metadata={"tool_name": tool_name},
            )
        payload = {
            "tool": serialize_tool_definition(tool),
            "metadata": {
                "capability_id": tool.capability_id,
                "risk_level": tool.risk_level,
                "read_only": tool.read_only,
                "permission_scope": tool.permission_scope,
                "concurrency_group": tool.concurrency_group,
                "requires_mode": tool.requires_mode,
            },
        }
        return ToolResult(
            success=True,
            output=json.dumps(payload, indent=2),
            metadata={"tool_name": tool_name},
        )
