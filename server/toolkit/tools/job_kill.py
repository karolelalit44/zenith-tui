from __future__ import annotations

from typing import Any

from server.config.constants import (
    BUILD_MODE,
    CONCURRENCY_GROUP_SHELL,
    PERMISSION_COMMAND,
    RISK_LOW,
    TOOL_DOMAIN_EXECUTION,
)

from ..base import BaseTool, ToolResult
from .background import get_background_manager


class JobKillTool(BaseTool):
    name = "job_kill"
    description = "Terminate background job"
    capability_id = "background_jobs"
    requires_mode = BUILD_MODE
    read_only = False
    concurrency_group = CONCURRENCY_GROUP_SHELL
    permission_scope = PERMISSION_COMMAND
    domains = (TOOL_DOMAIN_EXECUTION,)
    search_terms = (
        "kill",
        "terminate",
        "stop job",
        "background",
    )
    risk_level = RISK_LOW

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {"job_id": {"type": "string", "description": "Background job ID"}},
            "required": ["job_id"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        job_id = params.get("job_id", "")
        if not job_id:
            return ToolResult(success=False, error="No job_id provided")
        manager = get_background_manager()
        message = manager.kill(job_id)
        return ToolResult(success=True, output=message, metadata={"job_id": job_id})
