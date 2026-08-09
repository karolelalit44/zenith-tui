from __future__ import annotations

from pathlib import Path
from typing import Any

from server.config.constants import (
    CONCURRENCY_GROUP_READONLY,
    PERMISSION_READ,
    TOOL_DOMAIN_WORKSPACE_DISCOVERY,
)

from ..base import BaseTool, ToolResult

# A glob like **/* from the repo root can match tens of thousands of files
# (node_modules, .git, ...) and blow the context by megabytes. Always cap both
# the number of results and the rendered output.
_GLOB_MAX_RESULTS = 500
_GLOB_MAX_OUTPUT_CHARS = 40000


class GlobTool(BaseTool):
    name = "glob"
    description = (
        "Search files by glob pattern. Scope the pattern to a subdirectory "
        "(e.g. 'app/**/*.py') instead of '**/*' from the repo root - an "
        "unscoped recursive glob returns a huge list and wastes context."
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
            # A bare "**" matches only the root directory in pathlib, not files.
            # Normalize it so callers asking for "everything" actually get files.
            pattern = "**/*"
        # Resolve both sides to absolute paths. The `path` param may arrive as an
        # absolute path (e.g. the workspace root itself); joining a relative
        # workspace_root with an absolute path makes relative_to() raise
        # "not in the subpath" on the first file.
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
            truncated_files = total > _GLOB_MAX_RESULTS
            if truncated_files:
                files = files[:_GLOB_MAX_RESULTS]
            output = "\n".join(files) if files else "No files found"
            if truncated_files:
                output += (
                    f"\n[... {total - _GLOB_MAX_RESULTS} more matches omitted; "
                    f"narrow the glob pattern or add a path to search]"
                )
            if len(output) > _GLOB_MAX_OUTPUT_CHARS:
                output = output[:_GLOB_MAX_OUTPUT_CHARS]
                output += "\n[... output truncated; narrow the glob pattern]"
            return ToolResult(
                success=True,
                output=output,
                metadata={"count": total, "files": files},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
