from __future__ import annotations

from difflib import unified_diff
from typing import Any

from server.agents.session_workspace import evict_file_cache, record_write
from server.config.constants import (
    CONCURRENCY_GROUP_WORKSPACE_MUTATION,
    PERMISSION_WRITE,
    TOOL_DOMAIN_EDIT,
)
from server.toolkit.registry import current_tool_session_id

from ..base import BaseTool, ToolResult
from ..path_validator import validate_path
from .file_mutation_queue import FILE_MUTATION_QUEUE


def _unified_patch(rel_path: str, before: str, after: str) -> str:
    return "".join(
        unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{rel_path}",
            tofile=f"b/{rel_path}",
        )
    )


class FileEditTool(BaseTool):
    name = "file_edit"
    description = "Edit file via search-replace"
    requires_mode = None
    capability_id = "file_edit"
    read_only = False
    concurrency_group = CONCURRENCY_GROUP_WORKSPACE_MUTATION
    permission_scope = PERMISSION_WRITE
    domains = (TOOL_DOMAIN_EDIT,)
    search_terms = (
        "edit",
        "modify",
        "update",
        "replace",
        "patch",
        "change",
    )

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
                "old_content": {"type": "string", "description": "Text to replace"},
                "new_content": {"type": "string", "description": "Replacement text"},
                "replaceAll": {
                    "type": "boolean",
                    "description": "If true, replaces all occurrences of old_content instead of requiring a unique match",
                    "default": False,
                },
            },
            "required": ["path", "old_content", "new_content"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        rel_path = params.get("path") or ""
        resolved = validate_path(rel_path, workspace_root)
        if resolved is None:
            return ToolResult(success=False, error=f"Path escapes workspace boundary: {rel_path}")
        if not resolved.exists():
            return ToolResult(success=False, error=f"File not found: {rel_path}")
        old = params.get("old_content", "")
        new = params.get("new_content", "")
        if not old:
            return ToolResult(success=False, error="old_content cannot be empty")
        replace_all = bool(params.get("replaceAll") or params.get("replace_all") or False)

        try:
            async with FILE_MUTATION_QUEUE.mutation(workspace_root):
                raw = resolved.read_bytes()
                has_bom = raw.startswith(b"\xef\xbb\xbf")
                if has_bom:
                    raw = raw[3:]
                has_crlf = b"\r\n" in raw
                content = raw.decode("utf-8", errors="replace")

                norm_content = content.replace("\r\n", "\n")
                norm_old = old.replace("\r\n", "\n")
                norm_new = new.replace("\r\n", "\n")

                count = norm_content.count(norm_old)
                if count == 1:
                    new_norm_content = norm_content.replace(norm_old, norm_new, 1)
                    changes = 1
                    match_kind = "exact"
                elif count > 1:
                    if replace_all:
                        new_norm_content = norm_content.replace(norm_old, norm_new)
                        changes = count
                        match_kind = "exact"
                    else:
                        return ToolResult(
                            success=False,
                            error=f"Ambiguous: found {count} matches. Provide more surrounding context or set replaceAll: true.",
                        )
                else:
                    # Exact match failed: try line-trimmed matching (ignoring trailing whitespace)
                    lines = norm_content.split("\n")
                    old_lines = norm_old.split("\n")
                    new_lines = norm_new.split("\n")
                    old_len = len(old_lines)
                    trimmed_old = [l.rstrip() for l in old_lines]

                    matches: list[int] = []
                    if old_len <= len(lines):
                        for i in range(len(lines) - old_len + 1):
                            window = [l.rstrip() for l in lines[i : i + old_len]]
                            if window == trimmed_old:
                                matches.append(i)

                    if len(matches) == 1:
                        idx = matches[0]
                        updated_lines = lines[:idx] + new_lines + lines[idx + old_len :]
                        new_norm_content = "\n".join(updated_lines)
                        changes = 1
                        match_kind = "trimmed"
                    elif len(matches) > 1 and replace_all:
                        updated_lines = list(lines)
                        for idx in reversed(matches):
                            updated_lines = updated_lines[:idx] + new_lines + updated_lines[idx + old_len :]
                        new_norm_content = "\n".join(updated_lines)
                        changes = len(matches)
                        match_kind = "trimmed"
                    elif len(matches) > 1:
                        return ToolResult(
                            success=False,
                            error=f"Ambiguous: found {len(matches)} line-trimmed matches. Provide more surrounding context or set replaceAll: true.",
                        )
                    else:
                        preview = old[:80] + ("..." if len(old) > 80 else "")
                        return ToolResult(
                            success=False,
                            error=f"Content not found in file (exact match only): {preview}",
                        )

                final_text = (
                    new_norm_content.replace("\n", "\r\n")
                    if has_crlf
                    else new_norm_content
                )
                out_bytes = (
                    b"\xef\xbb\xbf" + final_text.encode("utf-8")
                    if has_bom
                    else final_text.encode("utf-8")
                )
                resolved.write_bytes(out_bytes)

                session_id = current_tool_session_id.get() or ""
                if session_id:
                    evict_file_cache(session_id, str(resolved))
                    record_write(session_id, rel_path, final_text)

                return ToolResult(
                    success=True,
                    output=f"Edited {rel_path}",
                    metadata={
                        "path": str(resolved),
                        "changes": changes,
                        "match": match_kind,
                        "diff": _unified_patch(rel_path, content, final_text),
                    },
                )
        except Exception as e:
            return ToolResult(success=False, error=str(e))

