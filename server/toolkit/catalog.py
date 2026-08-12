from __future__ import annotations

from pydantic import BaseModel, Field

from server.config.constants import (
    CAPABILITY_TOOL_DISCOVERY,
    COST_CLASS_HIGH,
    COST_CLASS_LOW,
    COST_CLASS_MEDIUM,
    DEFAULT_TOKENIZER_MODEL,
    LATENCY_CLASS_HIGH,
    LATENCY_CLASS_LOW,
    LATENCY_CLASS_MEDIUM,
    RISK_HIGH,
    RISK_LOW,
    RISK_MEDIUM,
    RISK_SAFE,
    TOOL_DOMAIN_DISCOVERY,
    TOOL_DOMAIN_EDIT,
    TOOL_DOMAIN_EXECUTION,
    TOOL_DOMAIN_READ,
    TOOL_DOMAIN_SUBAGENT,
    TOOL_DOMAIN_TASK,
    TOOL_DOMAIN_WEB_MCP,
    TOOL_DOMAIN_WORKSPACE_DISCOVERY,
)
from server.toolkit.registry import ToolRegistry
from server.toolkit.schema_metrics import estimate_tool_schema_tokens


class CapabilityDescriptor(BaseModel):
    id: str
    name: str
    short_description: str
    domains: list[str] = Field(default_factory=list)
    search_terms: list[str] = Field(default_factory=list)
    risk_level: str = RISK_SAFE
    read_only: bool = False
    cost_class: str = COST_CLASS_LOW
    latency_class: str = LATENCY_CLASS_LOW


CAPABILITIES: list[CapabilityDescriptor] = [
    CapabilityDescriptor(
        id="workspace_discovery",
        name="Workspace discovery",
        short_description="List and find files in the workspace",
        domains=[TOOL_DOMAIN_WORKSPACE_DISCOVERY],
        search_terms=["list files", "glob", "find", "discover", "workspace", "file search"],
        risk_level=RISK_SAFE,
        read_only=True,
        cost_class=COST_CLASS_LOW,
        latency_class=LATENCY_CLASS_MEDIUM,
    ),
    CapabilityDescriptor(
        id="file_read",
        name="Read files",
        short_description="Read file contents from the workspace",
        domains=[TOOL_DOMAIN_READ],
        search_terms=["read", "view", "cat", "inspect", "open file", "contents"],
        risk_level=RISK_SAFE,
        read_only=True,
        cost_class=COST_CLASS_LOW,
        latency_class=LATENCY_CLASS_LOW,
    ),
    CapabilityDescriptor(
        id="content_search",
        name="Search file contents",
        short_description="Search file contents by regex pattern",
        domains=[TOOL_DOMAIN_READ],
        search_terms=["grep", "search", "regex", "pattern", "find in files", "occurrences"],
        risk_level=RISK_SAFE,
        read_only=True,
        cost_class=COST_CLASS_LOW,
        latency_class=LATENCY_CLASS_MEDIUM,
    ),
    CapabilityDescriptor(
        id="file_write",
        name="Write files",
        short_description="Create new files in the workspace",
        domains=[TOOL_DOMAIN_EDIT],
        search_terms=["create", "write", "new file", "generate file"],
        risk_level=RISK_MEDIUM,
        read_only=False,
        cost_class=COST_CLASS_MEDIUM,
        latency_class=LATENCY_CLASS_LOW,
    ),
    CapabilityDescriptor(
        id="file_edit",
        name="Edit files",
        short_description="Apply targeted edits to existing files",
        domains=[TOOL_DOMAIN_EDIT],
        search_terms=["edit", "modify", "update", "replace", "patch", "change"],
        risk_level=RISK_MEDIUM,
        read_only=False,
        cost_class=COST_CLASS_MEDIUM,
        latency_class=LATENCY_CLASS_LOW,
    ),
    CapabilityDescriptor(
        id="file_delete",
        name="Delete files",
        short_description="Delete files from the workspace",
        domains=[TOOL_DOMAIN_EDIT],
        search_terms=["delete", "remove", "unlink", "clean up"],
        risk_level=RISK_HIGH,
        read_only=False,
        cost_class=COST_CLASS_MEDIUM,
        latency_class=LATENCY_CLASS_LOW,
    ),
    CapabilityDescriptor(
        id="command_execution",
        name="Command execution",
        short_description="Run shell commands in the workspace",
        domains=[TOOL_DOMAIN_EXECUTION],
        search_terms=["shell", "bash", "command", "run", "execute", "terminal", "npm"],
        risk_level=RISK_MEDIUM,
        read_only=False,
        cost_class=COST_CLASS_HIGH,
        latency_class=LATENCY_CLASS_HIGH,
    ),
    CapabilityDescriptor(
        id="background_jobs",
        name="Background jobs",
        short_description="Start, inspect, and terminate background jobs",
        domains=[TOOL_DOMAIN_EXECUTION],
        search_terms=["background", "job", "process", "output", "kill", "long running"],
        risk_level=RISK_LOW,
        read_only=False,
        cost_class=COST_CLASS_MEDIUM,
        latency_class=LATENCY_CLASS_MEDIUM,
    ),
    CapabilityDescriptor(
        id="web_fetch",
        name="Web fetch",
        short_description="Fetch content from external URLs",
        domains=[TOOL_DOMAIN_WEB_MCP],
        search_terms=["web", "fetch", "url", "http", "download", "page", "link"],
        risk_level=RISK_LOW,
        read_only=True,
        cost_class=COST_CLASS_MEDIUM,
        latency_class=LATENCY_CLASS_HIGH,
    ),
    CapabilityDescriptor(
        id="web_search",
        name="Web search",
        short_description="Search the web and return ranked sources",
        domains=[TOOL_DOMAIN_WEB_MCP],
        search_terms=["web", "search", "query", "research", "sources", "find", "google", "bing"],
        risk_level=RISK_LOW,
        read_only=True,
        cost_class=COST_CLASS_MEDIUM,
        latency_class=LATENCY_CLASS_HIGH,
    ),
    CapabilityDescriptor(
        id="lsp_analysis",
        name="Code analysis",
        short_description="Language-server analysis of symbols and diagnostics",
        domains=[TOOL_DOMAIN_READ],
        search_terms=["diagnostics", "lsp", "definition", "symbol", "errors", "go to"],
        risk_level=RISK_SAFE,
        read_only=True,
        cost_class=COST_CLASS_LOW,
        latency_class=LATENCY_CLASS_MEDIUM,
    ),
    CapabilityDescriptor(
        id="lsp_refactoring",
        name="Semantic refactoring",
        short_description="Language-server powered rename and refactoring",
        domains=[TOOL_DOMAIN_EDIT],
        search_terms=["rename", "refactor", "symbol", "lsp"],
        risk_level=RISK_MEDIUM,
        read_only=False,
        cost_class=COST_CLASS_LOW,
        latency_class=LATENCY_CLASS_MEDIUM,
    ),
    CapabilityDescriptor(
        id="task_tracking",
        name="Task tracking",
        short_description="Track an in-memory task/todo list",
        domains=[TOOL_DOMAIN_TASK],
        search_terms=["todo", "task", "track", "plan list", "progress"],
        risk_level=RISK_SAFE,
        read_only=False,
        cost_class=COST_CLASS_LOW,
        latency_class=LATENCY_CLASS_LOW,
    ),
    CapabilityDescriptor(
        id="sub_agent",
        name="Sub-agent delegation",
        short_description="Delegate a scoped task to a sub-agent",
        domains=[TOOL_DOMAIN_SUBAGENT],
        search_terms=["delegate", "subagent", "sub-agent", "separate agent", "parallel agent"],
        risk_level=RISK_MEDIUM,
        read_only=False,
        cost_class=COST_CLASS_HIGH,
        latency_class=LATENCY_CLASS_HIGH,
    ),
    CapabilityDescriptor(
        id="mcp_tool",
        name="MCP server tools",
        short_description="Tools exposed by external MCP servers",
        domains=[TOOL_DOMAIN_WEB_MCP],
        search_terms=["mcp", "external", "integration", "server tool"],
        risk_level=RISK_LOW,
        read_only=False,
        cost_class=COST_CLASS_MEDIUM,
        latency_class=LATENCY_CLASS_MEDIUM,
    ),
    CapabilityDescriptor(
        id=CAPABILITY_TOOL_DISCOVERY,
        name="Tool discovery",
        short_description="List capabilities and load full tool definitions on demand",
        domains=[TOOL_DOMAIN_DISCOVERY],
        search_terms=[
            "discover",
            "list tools",
            "tool definition",
            "available capabilities",
            "what tools",
        ],
        risk_level=RISK_SAFE,
        read_only=True,
        cost_class=COST_CLASS_LOW,
        latency_class=LATENCY_CLASS_LOW,
    ),
]

_CAPABILITY_IDS = frozenset(c.id for c in CAPABILITIES)


class CapabilityCatalog:
    def __init__(self, descriptors: list[CapabilityDescriptor] | None = None) -> None:
        self._descriptors: dict[str, CapabilityDescriptor] = {
            d.id: d for d in (descriptors or CAPABILITIES)
        }

    @property
    def ids(self) -> frozenset[str]:
        return frozenset(self._descriptors)

    def descriptors(self) -> list[CapabilityDescriptor]:
        return list(self._descriptors.values())

    def get(self, capability_id: str) -> CapabilityDescriptor | None:
        return self._descriptors.get(capability_id)

    def for_tool(self, tool) -> CapabilityDescriptor | None:
        return self.get(getattr(tool, "capability_id", "core"))


def build_catalog() -> CapabilityCatalog:
    return CapabilityCatalog()


class ToolInventoryEntry(BaseModel):
    name: str
    capability_id: str
    description: str
    modes: list[str]
    read_only: bool
    risk_level: str
    permission_scope: str
    concurrency_group: str
    timeout_ms: int | None
    domains: list[str]
    search_terms: list[str]
    cost_class: str
    latency_class: str
    schema_tokens: int


def build_inventory(
    registry: ToolRegistry, model: str = DEFAULT_TOKENIZER_MODEL
) -> list[ToolInventoryEntry]:
    entries: list[ToolInventoryEntry] = []
    for name in registry.list_tools():
        tool = registry.get(name)
        if tool is None:
            continue
        schema_tokens = estimate_tool_schema_tokens(tool.get_schema(), tool.description, model)
        entries.append(
            ToolInventoryEntry(
                name=name,
                capability_id=tool.capability_id,
                description=tool.description,
                modes=list(tool.modes or []),
                read_only=tool.read_only,
                risk_level=tool.risk_level,
                permission_scope=tool.permission_scope,
                concurrency_group=tool.concurrency_group,
                timeout_ms=tool.timeout_ms,
                domains=list(tool.domains),
                search_terms=list(tool.search_terms),
                cost_class=tool.cost_class,
                latency_class=tool.latency_class,
                schema_tokens=schema_tokens,
            )
        )
    return entries


def is_known_capability(capability_id: str) -> bool:
    return capability_id in _CAPABILITY_IDS
