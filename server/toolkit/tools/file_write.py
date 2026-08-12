from __future__ import annotations

import re
from typing import Any

from server.config.constants import (
    BUILD_MODE,
    CONCURRENCY_GROUP_WORKSPACE_MUTATION,
    FILE_ALREADY_EXISTS_ERROR,
    FILE_OVERWRITE_PARAM,
    PERMISSION_WRITE,
    TOOL_DOMAIN_EDIT,
)

from ..base import BaseTool, ToolResult
from ..path_validator import validate_path

_PLACEHOLDER_RE = re.compile(
    "\\[[\\w\\s]*(?:CONTENT|FILE|CODE|PASTE|INSERT|TODO|DESIRED|UPDATED|REPLACE|YOUR)[\\w\\s]*\\]|\\bYOUR_[\\w_]+_HERE\\b|\\b(?:PLACEHOLDER|TODO|FIXME|XXX|TBD)\\b|\\[HTML\\]|\\[ACTUAL_|\\[Current |\\[UPDATED_",
    re.IGNORECASE,
)


class FileWriteTool(BaseTool):
    name = "file_write"
    description = (
        "Create or overwrite a file; missing parent directories are created automatically."
    )
    requires_mode = BUILD_MODE
    capability_id = "file_write"
    read_only = False
    concurrency_group = CONCURRENCY_GROUP_WORKSPACE_MUTATION
    permission_scope = PERMISSION_WRITE
    domains = (TOOL_DOMAIN_EDIT,)
    search_terms = (
        "create",
        "write",
        "new file",
        "generate file",
    )

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "File path; any missing parent directories are created automatically"
                    ),
                },
                "content": {"type": "string", "description": "File content"},
                FILE_OVERWRITE_PARAM: {
                    "type": "boolean",
                    "description": "Overwrite existing",
                    "default": False,
                },
            },
            "required": ["path", "content"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        rel_path = params.get("path") or ""
        if not rel_path:
            return ToolResult(success=False, error="Missing file path parameter")
        resolved = validate_path(rel_path, workspace_root)
        if resolved is None:
            return ToolResult(
                success=False,
                error=f"Path escapes workspace boundary: {rel_path}. Use relative paths within the project.",
            )
        content = params.get("content", "")
        overwrite = params.get(FILE_OVERWRITE_PARAM, False)
        if content and _PLACEHOLDER_RE.search(content):
            m = _PLACEHOLDER_RE.search(content)
            return ToolResult(
                success=False,
                error=f"Content contains placeholder ({m.group(0)}). Write the actual content, not a placeholder.",
            )
        if resolved.exists() and (not overwrite):
            return ToolResult(
                success=False,
                error=FILE_ALREADY_EXISTS_ERROR.format(
                    path=rel_path, overwrite_param=FILE_OVERWRITE_PARAM
                ),
            )
        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
            return ToolResult(
                success=True,
                output=f"Created {rel_path} ({len(content)} bytes)",
                metadata={"path": str(resolved), "bytes": len(content)},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
