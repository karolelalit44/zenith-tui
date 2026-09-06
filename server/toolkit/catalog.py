from __future__ import annotations

from pydantic import BaseModel

from server.config.constants import DEFAULT_TOKENIZER_MODEL

from .registry import ToolRegistry
from .schema_metrics import estimate_tool_schema_tokens


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
