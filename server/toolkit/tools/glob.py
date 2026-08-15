from __future__ import annotations

from pathlib import Path
from typing import Any

from server.config.constants import (
    CONCURRENCY_GROUP_READONLY,
    GLOB_MAX_OUTPUT_CHARS,
    GLOB_MAX_RESULTS,
    PERMISSION_READ,
    TOOL_DOMAIN_WORKSPACE_DISCOVERY,
)

from ..base import BaseTool, ToolResult


class GlobTool(BaseTool):
    name = "glob"
    description = (
        "Find files by glob pattern. Scope the pattern to a subdirectory "
        "(e.g. 'app/**/*.py'); an unscoped '**/*' from the repo root matches "
        "node_modules/.git and wastes context."
    )
    requires_mode = None
    capability_id = "workspace_discovery"
    read_only = True
    concurrency_group = CONCURRENCY_GROUP_READONLY
    permission_scope = PERMISSION_READ
    domains = (TOOL_DOMAIN_WORKSPACE_DISCOVERY,)
    search_terms = (
        "list files",
        "glob",
        "find",
        "discover",
        "workspace",
        "file search",
    )

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": (
                        "Glob pattern, scoped to a subdirectory (e.g. 'app/**/*.py'). "
                        "Avoid '**/*' from the repo root; it matches node_modules and "
                        ".git and returns thousands of files."
                    ),
                },
                "path": {
                    "type": "string",
                    "description": "Directory to search (defaults to the workspace root)",
                },
            },
            "required": ["pattern"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        pattern = params.get("pattern", "**/*")
        if pattern.strip() == "**":
            pattern = "**/*"
        base = Path(workspace_root).resolve()
        requested = params.get("path") or ""
        search_path = (
            Path(requested) if Path(requested).is_absolute() else base / requested
        ).resolve()
        if search_path != base and base not in search_path.parents:
            return ToolResult(success=False, error=f"Search path outside workspace: {search_path}")
        if not search_path.exists():
            return ToolResult(success=False, error=f"Search path not found: {search_path}")
        try:
            files = sorted(
                str(f.relative_to(base)) for f in search_path.glob(pattern) if f.is_file()
            )
            total = len(files)
            truncated_files = total > GLOB_MAX_RESULTS
            if truncated_files:
                files = files[:GLOB_MAX_RESULTS]
            output = "\n".join(files) if files else "No files found"
            if truncated_files:
                output += (
                    f"\n[... {total - GLOB_MAX_RESULTS} more matches omitted; "
                    f"narrow the glob pattern or add a path to search]"
                )
            if len(output) > GLOB_MAX_OUTPUT_CHARS:
                output = output[:GLOB_MAX_OUTPUT_CHARS]
                output += "\n[... output truncated; narrow the glob pattern]"
            return ToolResult(
                success=True,
                output=output,
                metadata={"count": total, "files": files},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
