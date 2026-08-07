from __future__ import annotations

from collections import OrderedDict

from server.config.constants import (
    DISCOVER_CAPABILITIES_TOOL,
    GET_TOOL_DEFINITION_TOOL,
    MAX_ACTIVE_TOOLS_PER_TURN,
)
from server.toolkit.registry import ToolRegistry
from server.toolkit.schema_metrics import estimate_tool_schema_tokens

DISCOVERY_TOOLS: tuple[str, ...] = (DISCOVER_CAPABILITIES_TOOL, GET_TOOL_DEFINITION_TOOL)


def build_mode_tool_seed(allowed_tools: list[str] | None) -> list[str]:
    """Combine the mode's core tool set with the always-on discovery meta-tools."""
    seed = list(allowed_tools or [])
    for name in DISCOVERY_TOOLS:
        if name not in seed:
            seed.append(name)
    return seed


class SchemaResolver:
    """Tracks the bounded set of tool schemas offered to the model on each turn.

    The active set is seeded with the mode's core tools plus the discovery
    meta-tools, and grows on demand when the model requests a tool definition or
    the loop escalates a registered-but-unoffered tool. It never offers more than
    ``max_tools`` schemas per turn; the discovery meta-tools are always retained.
    """

    def __init__(
        self,
        registry: ToolRegistry | None,
        seed: list[str] | None = None,
        max_tools: int = MAX_ACTIVE_TOOLS_PER_TURN,
    ) -> None:
        self.registry = registry
        self._always_on: tuple[str, ...] = DISCOVERY_TOOLS
        self._max_tools = max_tools
        self._active: OrderedDict[str, None] = OrderedDict()
        for name in seed or []:
            self.request_tool(name)

    def is_active(self, name: str) -> bool:
        return name in self._active

    def active_names(self) -> list[str]:
        return list(self._active)

    def request_tool(self, name: str) -> bool:
        if self.registry is None or self.registry.get(name) is None:
            return False
        if name in self._active:
            self._active.move_to_end(name)
            return True
        self._active[name] = None
        self._evict()
        return True

    def _evict(self) -> None:
        while len(self._active) > self._max_tools:
            for name in self._active:
                if name not in self._always_on:
                    del self._active[name]
                    break
            else:
                break

    def schemas(self, mode: str, allowed_mcp: dict[str, list[str]] | None = None) -> list[dict]:
        if self.registry is None:
            return []
        return self.registry.get_schemas_for_mode(
            mode, allowed_mcp=allowed_mcp, allowed_tools=list(self._active)
        )

    def openai_tools(
        self, mode: str, allowed_mcp: dict[str, list[str]] | None = None
    ) -> list[dict]:
        from server.agents.validation import schemas_to_openai_tools

        return schemas_to_openai_tools(self.schemas(mode, allowed_mcp=allowed_mcp))

    def schema_tokens(self, model: str) -> int:
        if self.registry is None:
            return 0
        total = 0
        for name in self._active:
            tool = self.registry.get(name)
            if tool is None:
                continue
            total += estimate_tool_schema_tokens(tool.get_schema(), tool.description, model)
        return total
