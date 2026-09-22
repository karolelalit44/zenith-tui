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
    description = (
        "View background job output. Poll periodically until completed is true. "
        "Pass the job_id from bash run_in_background, then re-poll for completion."
    )
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
            "properties": {
                "job_id": {"type": "string", "description": "Background job ID"},
                "offset": {
                    "type": "integer",
                    "description": "Char offset to page from (default 0 = latest tail when truncated)",
                    "default": 0,
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Max chars to return per poll (default 15000, max 50000)",
                    "default": 15000,
                },
            },
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
        full = manager.get_output(job_id) or ""
        raw_offset = params.get("offset", 0)
        try:
            offset = max(0, int(raw_offset or 0))
        except (TypeError, ValueError):
            return ToolResult(success=False, error=f"Invalid offset: {raw_offset!r}")
        raw_max = params.get("max_chars", 15000)
        try:
            _max = int(raw_max or 15000)
        except (TypeError, ValueError):
            return ToolResult(success=False, error=f"Invalid max_chars: {raw_max!r}")
        _max = max(1000, min(_max, 50000))
        total = len(full)
        offset = min(offset, total)
        truncated = (total - offset) > _max
        if not truncated:
            output = full[offset:] if offset else full
            next_offset = total
        elif offset > 0:
            output = full[offset : offset + _max]
            next_offset = min(total, offset + len(output))
            output += (
                f"\n\n... [showing chars {offset}-{next_offset} of {total}. "
                f"Poll again with offset={next_offset} job_id='{job_id}'.]"
            )
        else:
            output = full[-_max:]
            next_offset = total
            output += (
                f"\n\n... [output truncated: showing latest {_max} chars of {total} total. "
                f"Poll with offset=0 for tail, or offset<N max_chars<M to page.]"
            )
        base_meta = {
            "job_id": job_id,
            "completed": bool(job.done),
            "total_chars": total,
            "truncated": truncated,
            "offset": offset,
            "next_offset": next_offset,
        }
        if not job.done:
            return ToolResult(success=True, output=output, metadata=base_meta)
        ok = job.exit_code == 0
        return ToolResult(
            success=ok,
            output=output,
            error="" if ok else output,
            metadata={**base_meta, "exit_code": job.exit_code},
        )
