"""Job output tool — view output from a background job."""

from __future__ import annotations

from typing import Any

from .background import get_background_manager
from .base import BaseTool, ToolResult


class JobOutputTool(BaseTool):
    name = "job_output"
    description = "View output from a running or completed background job"

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "The background job ID to get output from",
                },
            },
            "required": ["job_id"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        job_id = params.get("job_id", "")
        if not job_id:
            return ToolResult(success=False, error="No job_id provided")

        manager = get_background_manager()
        output = manager.get_output(job_id)

        if output is None:
            return ToolResult(success=False, error=f"Job {job_id} not found")

        return ToolResult(success=True, output=output, metadata={"job_id": job_id})
