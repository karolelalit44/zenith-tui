from __future__ import annotations

from typing import Any

from server.agents.session_workspace import evict_file_cache, record_write
from server.config.constants import (
    CONCURRENCY_GROUP_WORKSPACE_MUTATION,
    FILE_ALREADY_EXISTS_ERROR,
    FILE_OVERWRITE_PARAM,
    TOOL_DOMAIN_EDIT,
)
from server.toolkit.registry import current_tool_session_id

from ..base import BaseTool, ToolResult
from ..path_validator import validate_path
from .file_mutation_queue import FILE_MUTATION_QUEUE


class FileWriteTool(BaseTool):
    name = "file_write"
    description = (
        "Create or overwrite a file; missing parent directories are created automatically. "
        "In plan mode, only plan.md/todo.md are writable."
    )
    requires_mode = None
    capability_id = "file_write"
    read_only = False
    concurrency_group = CONCURRENCY_GROUP_WORKSPACE_MUTATION
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
        existed = resolved.exists()
        if existed and (not overwrite):
            return ToolResult(
                success=False,
                error=FILE_ALREADY_EXISTS_ERROR.format(
                    path=rel_path, overwrite_param=FILE_OVERWRITE_PARAM
                ),
            )
        try:
            # Detect existing line endings and BOM before mutating
            has_bom = False
            has_crlf = False
            if existed:
                try:
                    raw_bytes = resolved.read_bytes()
                    has_bom = raw_bytes.startswith(b"\xef\xbb\xbf")
                    has_crlf = b"\r\n" in raw_bytes
                except OSError:
                    pass

            norm_content = (
                content.replace("\r\n", "\n").replace("\n", "\r\n")
                if has_crlf
                else content
            )
            out_bytes = (
                b"\xef\xbb\xbf" + norm_content.encode("utf-8")
                if has_bom
                else norm_content.encode("utf-8")
            )

            # Serialize the filesystem mutation per workspace (opencode's
            # file-mutation Semaphore) so parallel tool calls cannot race on
            # the same file.
            async with FILE_MUTATION_QUEUE.mutation(workspace_root):
                resolved.parent.mkdir(parents=True, exist_ok=True)
                resolved.write_bytes(out_bytes)

            session_id = current_tool_session_id.get() or ""
            if session_id:
                # _STORE (write records) is keyed by the raw relative path.
                # _READ_CACHE (read slices) is absolute-keyed; evict both so
                # subsequent reads (inside or outside simple_loop) get fresh data.
                evict_file_cache(session_id, rel_path)
                evict_file_cache(session_id, str(resolved))
                record_write(session_id, rel_path, content)

            action = "Updated" if existed else "Created"
            return ToolResult(
                success=True,
                output=f"{action} {rel_path} ({len(content)} bytes)",
                metadata={"path": str(resolved), "bytes": len(content), "overwritten": existed},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))

