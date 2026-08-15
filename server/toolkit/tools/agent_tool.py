from __future__ import annotations

import logging
from typing import Any

from server.config.constants import (
    BUILD_MODE,
    CONCURRENCY_GROUP_SUBAGENT,
    COST_CLASS_HIGH,
    LATENCY_CLASS_HIGH,
    MAX_TOOL_OUTPUT_BASELINE,
    PERMISSION_SUBAGENT,
    RISK_MEDIUM,
    TOOL_DOMAIN_SUBAGENT,
)

from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class SubAgentTool(BaseTool):
    name = "agent"
    description = "Delegate sub-task to separate agent"
    capability_id = "sub_agent"
    requires_mode = BUILD_MODE
    read_only = False
    concurrency_group = CONCURRENCY_GROUP_SUBAGENT
    permission_scope = PERMISSION_SUBAGENT
    domains = (TOOL_DOMAIN_SUBAGENT,)
    search_terms = (
        "delegate",
        "subagent",
        "sub-agent",
        "separate agent",
        "parallel agent",
    )
    risk_level = RISK_MEDIUM
    cost_class = COST_CLASS_HIGH
    latency_class = LATENCY_CLASS_HIGH

    def __init__(self, provider: Any | None = None) -> None:
        self._provider = provider

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Sub-agent task description"},
                "description": {"type": "string", "description": "Short 3-5 word summary"},
            },
            "required": ["task", "description"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        from server.agents.context import ContextManager
        from server.agents.loop import AgentLoop
        from server.config.settings import AppSettings
        from server.toolkit import create_default_registry

        task = params.get("task", "")
        description = params.get("description", "sub-agent task")
        if not task:
            return ToolResult(success=False, error="No task provided")
        if self._provider is None:
            return ToolResult(
                success=False,
                error="No provider available for sub-agent. Configure a provider first.",
            )
        logger.info("SUB-AGENT starting: %s", description)
        try:
            config = AppSettings(workspace_root=workspace_root)
            tool_registry = create_default_registry()
            context_manager = ContextManager(config)
            loop = AgentLoop(config, self._provider, context_manager, tool_registry)
            collected_output: list[str] = []
            async for event in loop.process_prompt(prompt=task, session_id="sub-agent", history=[]):
                kind = event.kind if hasattr(event, "kind") else ""
                if kind == "message":
                    text = event.data.get("text", "")
                    if text:
                        collected_output.append(text)
            output = (
                "\n".join(collected_output)
                if collected_output
                else "Sub-agent completed with no output."
            )
            logger.info("SUB-AGENT completed: %s", description)
            return ToolResult(
                success=True, output=output[:MAX_TOOL_OUTPUT_BASELINE], metadata={"sub_task": description}
            )
        except Exception as e:
            logger.error("SUB-AGENT failed: %s: %s", description, e)
            return ToolResult(success=False, error=f"Sub-agent failed: {e}")
