from __future__ import annotations

from typing import Any

from server.config.constants import (
    CONCURRENCY_GROUP_READONLY,
    PERMISSION_READ,
    TOOL_DOMAIN_EXECUTION,
)

from ..base import BaseTool, ToolResult
from .background import get_background_manager


class JobOutputTool(BaseTool):
    name = "job_output"
    description = "View background job output"
    capability_id = "background_jobs"
    read_only = True
    concurrency_group = CONCURRENCY_GROUP_READONLY
    permission_scope = PERMISSION_READ
    domains = (TOOL_DOMAIN_EXECUTION,)
    search_terms = (
        "background",
        "job",
        "output",
        "log",
        "process",
    )

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
        job = manager.get(job_id)
        if job is None:
            return ToolResult(success=False, error=f"Job {job_id} not found")
        output = manager.get_output(job_id) or ""
        if not job.done:
            return ToolResult(
                success=True, output=output, metadata={"job_id": job_id, "completed": False}
            )
        ok = job.exit_code == 0
        return ToolResult(
            success=ok,
            output=output,
            error="" if ok else output,
            metadata={"job_id": job_id, "completed": True, "exit_code": job.exit_code},
        )
