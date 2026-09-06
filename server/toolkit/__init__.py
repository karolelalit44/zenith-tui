import logging

from .base import BaseTool, ToolContext, ToolMiddleware, ToolResult
from .catalog import ToolInventoryEntry, build_inventory
from .discovery import DiscoverCapabilitiesTool, GetToolDefinitionTool
from .registry import ToolRegistry
from .registry_validation import validate_registry
from .resolver import DISCOVERY_TOOLS, SchemaResolver, build_mode_tool_seed
from .schema_metrics import estimate_tool_schema_tokens, measure_registry_schema_tokens
from .tools.bash import BashTool
from .tools.file_delete import FileDeleteTool
from .tools.file_edit import FileEditTool
from .tools.file_read import FileReadTool
from .tools.file_write import FileWriteTool
from .tools.glob import GlobTool
from .tools.grep import GrepTool
from .tools.job_kill import JobKillTool
from .tools.job_output import JobOutputTool
from .tools.list_dir import ListDirTool
from .tools.todo import TodoTool
from .tools.webfetch import WebfetchTool
from .tools.websearch import WebsearchTool

logger = logging.getLogger(__name__)

__all__ = [
    "DISCOVERY_TOOLS",
    "BaseTool",
    "BashTool",
    "DiscoverCapabilitiesTool",
    "FileDeleteTool",
    "FileEditTool",
    "FileReadTool",
    "FileWriteTool",
    "GetToolDefinitionTool",
    "GlobTool",
    "GrepTool",
    "JobKillTool",
    "JobOutputTool",
    "SchemaResolver",
    "TodoTool",
    "ToolContext",
    "ToolInventoryEntry",
    "ToolMiddleware",
    "ToolRegistry",
    "ToolResult",
    "WebfetchTool",
    "WebsearchTool",
    "build_inventory",
    "build_mode_tool_seed",
    "estimate_tool_schema_tokens",
    "measure_registry_schema_tokens",
    "validate_registry",
]


def create_default_registry(
    timeout: int = 30,
    provider: object | None = None,
    hooks: object | None = None,
    config: object | None = None,
) -> ToolRegistry:
    from .middleware import (
        HookMiddleware,
        LoggingMiddleware,
        SafetyCheckMiddleware,
    )
    from .middleware.plan_write import PlanWriteGuard

    registry = ToolRegistry()
    registry.register_middleware(LoggingMiddleware())
    registry.register_middleware(PlanWriteGuard())
    registry.register(BashTool(timeout=timeout))
    registry.register(FileReadTool())
    registry.register(FileWriteTool())
    registry.register(FileEditTool())
    registry.register(FileDeleteTool())
    registry.register(GlobTool())
    registry.register(GrepTool())
    registry.register(ListDirTool())
    # WP6: structural query family — read-only, evidence-carrying lookups
    # over the tree-sitter symbol graph (callers/outline/blast radius).
    registry.register(WebfetchTool(provider=provider))
    registry.register(WebsearchTool())
    registry.register(JobOutputTool())
    registry.register(JobKillTool())
    registry.register(TodoTool())
    # WP5 (D3/D7, completed): the legacy write-capable "agent" tool has been
    # deleted; explore is the sole delegation surface. See
    # docs/WP5_EXPLORE_DELEGATION_PLAN.md §5.2.5.
    if config is not None and getattr(config, "explore_delegation", "tool") != "off":
        from .tools.explore_tool import ExploreTool

        registry.register(
            ExploreTool(
                config=config,
                provider=provider,
                tool_registry=registry,
                weak_model=getattr(config, "weak_model", None),
            )
        )
    registry.register(DiscoverCapabilitiesTool(registry=registry))
    registry.register(GetToolDefinitionTool(registry=registry))
    if hooks is not None:
        from server.domain.hooks import HookRunner

        registry.register_middleware(HookMiddleware(HookRunner(hooks)))
    registry.register_middleware(SafetyCheckMiddleware())
    validation_errors = validate_registry(registry)
    if validation_errors:
        logger.warning("Tool registry validation failed at startup:")
        for error in validation_errors:
            logger.warning("  %s", error)
    return registry
