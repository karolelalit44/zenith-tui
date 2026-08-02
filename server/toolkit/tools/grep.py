"""Grep tool — search file contents using regex."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..base import BaseTool, ToolResult


class GrepTool(BaseTool):
    name = "grep"
    description = "Search file contents by regex"
    requires_mode = None  # Available in both plan and build

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern",
                },
                "path": {
                    "type": "string",
                    "description": "Search directory/file",
                },
                "include": {
                    "type": "string",
                    "description": "File pattern filter",
                },
            },
            "required": ["pattern"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        pattern = params.get("pattern", "")
        search_path = Path(workspace_root) / params.get("path", ".")
        include = params.get("include", None)

        if not search_path.exists():
            return ToolResult(
                success=False, error=f"Search path not found: {search_path}"
            )

        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return ToolResult(success=False, error=f"Invalid regex: {e}")

        try:
            matches: list[str] = []

            if search_path.is_file():
                files = [search_path]
            else:
                glob_pattern = include if include else "**/*"
                files = [f for f in search_path.glob(glob_pattern) if f.is_file()]

            for file_path in files:
                try:
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                    for i, line in enumerate(content.split("\n"), 1):
                        if regex.search(line):
                            try:
                                rel = str(file_path.relative_to(workspace_root))
                            except ValueError:
                                rel = str(file_path)
                            matches.append(f"{rel}:{i}: {line.strip()}")
                except Exception:
                    continue

            output = "\n".join(matches) if matches else "No matches found"
            return ToolResult(
                success=True,
                output=output,
                metadata={"count": len(matches)},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
