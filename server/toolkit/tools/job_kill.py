"""Job kill tool — terminate a background job."""

from __future__ import annotations

from typing import Any

from ..base import BaseTool, ToolResult
from .background import get_background_manager


class JobKillTool(BaseTool):
    name = "job_kill"
    description = "Terminate background job"

    @property
    def risk_level(self) -> str:
        return "low"

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "Background job ID",
                },
            },
            "required": ["job_id"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        job_id = params.get("job_id", "")
        if not job_id:
            return ToolResult(success=False, error="No job_id provided")

        manager = get_background_manager()
        message = manager.kill(job_id)

        return ToolResult(success=True, output=message, metadata={"job_id": job_id})
