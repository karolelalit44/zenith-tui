"""Glob tool — search for files by pattern."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import BaseTool, ToolResult


class GlobTool(BaseTool):
    name = "glob"
    description = "Search files by glob pattern"
    requires_mode = None  # Available in both plan and build

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (e.g. **/*.py)",
                },
                "path": {
                    "type": "string",
                    "description": "Directory to search",
                },
            },
            "required": ["pattern"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        pattern = params.get("pattern", "**/*")
        search_path = Path(workspace_root) / params.get("path", "")

        if not search_path.exists():
            return ToolResult(success=False, error=f"Search path not found: {search_path}")

        try:
            files = sorted(
                str(f.relative_to(workspace_root)) for f in search_path.glob(pattern) if f.is_file()
            )
            output = "\n".join(files) if files else "No files found"
            return ToolResult(
                success=True,
                output=output,
                metadata={"count": len(files), "files": files},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
