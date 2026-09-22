from __future__ import annotations

import re
from typing import Any

from server.agents.session_workspace import (
    cache_file_read,
    covering_slice_for,
    get_cached_read,
)
from server.config.constants import (
    CONCURRENCY_GROUP_READONLY,
    DEFAULT_FILE_READ_LINES,
    MAX_FILE_READ_LINES,
    PERMISSION_READ,
    TOOL_DOMAIN_READ,
)
from server.toolkit.registry import current_tool_session_id
from server.workspace.ignore import blocked_as_missing, get_matcher

from ..base import BaseTool, ToolResult
from ..path_validator import validate_path

_OUTLINE_PATTERN = re.compile(
    r"^(?:"
    r"\s*(?:async\s+)?def\s+[A-Za-z_0-9]+"  # Python def / async def
    r"|\s*class\s+[A-Za-z_0-9]+"  # Python/JS/TS class
    r"|\s*(?:export\s+)?(?:async\s+)?function\s+[A-Za-z_0-9]+"  # JS/TS function
    r"|\s*(?:export\s+)?(?:const|let|var)\s+[A-Za-z_0-9]+\s*=\s*(?:async\s*)?\("  # JS/TS arrow func
    r"|\s*(?:export\s+)?(?:interface|type|enum)\s+[A-Za-z_0-9]+"  # TS types/interfaces
    r"|\s*(?:pub\s+)?(?:fn|struct|enum|impl|trait)\s+[A-Za-z_0-9]+"  # Rust
    r"|\s*func\s+(?:\([^)]+\)\s+)?[A-Za-z_0-9]+"  # Go func
    r"|#{1,4}\s+.+"  # Markdown headings
    r")"
)


_LINE_PREFIX_RE = re.compile(r"^(\d+): ")


def _subslice_from_cached(
    cached_output: str, h_offset: int, offset: int, limit: int
) -> str | None:
    """Extract a numbered sub-range from a cached formatted read output.

    ``cached_output`` is the ``"{line}: {text}"`` numbered listing of a
    previously read slice that started at ``h_offset`` (0-indexed). Returns the
    numbered lines for ``[offset, offset+limit)`` if fully present, else None.
    """
    requested = range(offset + 1, offset + limit + 1)
    selected: list[str] = []
    for line in cached_output.splitlines():
        m = _LINE_PREFIX_RE.match(line)
        if not m:
            continue
        line_no = int(m.group(1))
        if line_no in requested:
            selected.append(line)
    if not selected:
        return None
    return "\n".join(selected)


def _first_meaningful_line(lines: list[str], start: int) -> str | None:
    """Return the first non-empty, non-comment line after ``start`` (0-indexed).

    Scans up to 8 lines ahead to find a docstring, return statement, or
    assignment — anything that hints at the symbol's purpose without
    requiring a full file_read.
    """
    for j in range(start, min(start + 8, len(lines))):
        stripped = lines[j].strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Skip lines that are just another symbol definition (nested class/def)
        if _OUTLINE_PATTERN.match(stripped) and not stripped.startswith(('"""', "'''")):
            continue
        # Truncate long preview lines
        if len(stripped) > 100:
            stripped = stripped[:97] + "..."
        return stripped
    return None


def _extract_file_outline(lines: list[str], rel_path: str) -> str:
    outline_entries: list[str] = []
    for i, line in enumerate(lines, 1):
        stripped = line.rstrip()
        if _OUTLINE_PATTERN.match(stripped):
            preview = stripped.strip()
            if len(preview) > 120:
                preview = preview[:117] + "..."
            purpose = _first_meaningful_line(lines, i)  # i is 0-indexed here (next line)
            entry = f"L{i:4d}: {preview}"
            if purpose and purpose != preview:
                entry += f"\n       {purpose}"
            outline_entries.append(entry)

    if not outline_entries:
        sample_count = min(30, len(lines))
        return (
            f"File outline for {rel_path} ({len(lines)} total lines, no explicit class/function symbols detected):\n"
            + "\n".join(f"L{i:4d}: {lines[i - 1].strip()}" for i in range(1, sample_count + 1))
        )

    return (
        f"Symbol outline for {rel_path} ({len(outline_entries)} symbols found across {len(lines)} lines):\n"
        + "\n".join(outline_entries)
    )


_BINARY_EXTENSIONS = {
    ".exe", ".dll", ".so", ".dylib", ".bin", ".iso",
    ".pyc", ".pyo", ".pyd", ".wasm", ".class", ".jar",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".tiff",
    ".pdf", ".sqlite", ".db", ".node",
}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".tiff"}


def _is_binary(path: Path) -> bool:
    if path.suffix.lower() in _BINARY_EXTENSIONS:
        return True
    try:
        with open(path, "rb") as f:
            chunk = f.read(1024)
            if b"\x00" in chunk:
                return True
            non_printable = sum(1 for b in chunk if b < 9 or (13 < b < 32))
            if chunk and (non_printable / len(chunk) > 0.3):
                return True
    except OSError:
        return True
    return False


class FileReadTool(BaseTool):
    name = "file_read"
    description = (
        "Read file contents by line range, inspect directory contents, or inspect symbol outline. "
        "Default limit is 250 lines; pass offset to paginate."
    )
    requires_mode = None
    capability_id = "file_read"
    read_only = True
    concurrency_group = CONCURRENCY_GROUP_READONLY
    permission_scope = PERMISSION_READ
    domains = (TOOL_DOMAIN_READ,)
    search_terms = (
        "read",
        "view",
        "cat",
        "inspect",
        "open file",
        "contents",
        "outline",
    )

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
                "offset": {
                    "type": "integer",
                    "description": "Start line (0-indexed)",
                    "default": 0,
                },
                "limit": {
                    "type": "integer",
                    "description": f"Max lines to read (default {DEFAULT_FILE_READ_LINES}, capped at {MAX_FILE_READ_LINES})",
                    "default": DEFAULT_FILE_READ_LINES,
                },
                "outline": {
                    "type": "boolean",
                    "description": "If true, returns file outline/symbols with line numbers instead of full content",
                    "default": False,
                },
            },
            "required": ["path"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        rel_path = params.get("path") or ""
        resolved = validate_path(rel_path, workspace_root)
        if resolved is None:
            return ToolResult(success=False, error=f"Path escapes workspace boundary: {rel_path}")
        if not resolved.exists():
            return ToolResult(success=False, error=f"File not found: {rel_path}")
        if resolved.is_dir():
            return ToolResult(
                success=False,
                error=f"Path is a directory: {rel_path}. Use list_dir to inspect directory contents.",
            )

        try:
            session_id = current_tool_session_id.get() or ""
            stat = resolved.stat()
            size = stat.st_size
            mtime_ns = stat.st_mtime_ns

            if _is_binary(resolved):
                ext = resolved.suffix.lower()
                if ext in _IMAGE_EXTENSIONS:
                    return ToolResult(
                        success=True,
                        output=f"[Image file: {rel_path} ({size} bytes)]",
                        metadata={"path": str(resolved), "is_image": True, "size": size},
                    )
                return ToolResult(
                    success=False,
                    error=f"Cannot read binary file: {rel_path} ({size} bytes)",
                )

            offset = max(0, int(params.get("offset", 0)))
            raw_limit = params.get("limit")
            limit = (
                min(int(raw_limit), MAX_FILE_READ_LINES)
                if raw_limit is not None
                else DEFAULT_FILE_READ_LINES
            )

            cached = (
                get_cached_read(session_id, str(resolved), offset, limit, mtime_ns, size)
                if session_id
                else None
            )
            if cached is not None:
                return ToolResult(
                    success=True,
                    output=cached,
                    metadata={
                        "path": str(resolved),
                        "from_cache": True,
                    },
                )

            # Sub-slice: the requested range may be fully contained within an
            # already-cached, unchanged slice. Extract the numbered lines directly
            # from the cached formatted output so no disk read is needed.
            if session_id:
                covering = covering_slice_for(
                    session_id, str(resolved), offset, limit, mtime_ns=mtime_ns, size=size
                )
                if covering is not None:
                    h_offset, h_limit = covering
                    covering_out = get_cached_read(
                        session_id, str(resolved), h_offset, h_limit, mtime_ns, size
                    )
                    if covering_out is not None:
                        subslice = _subslice_from_cached(
                            covering_out, h_offset, offset, limit
                        )
                        if subslice is not None:
                            return ToolResult(
                                success=True,
                                output=subslice,
                                metadata={
                                    "path": str(resolved),
                                    "from_cache": True,
                                },
                            )

            content = resolved.read_text(encoding="utf-8", errors="replace")
            lines = content.split("\n")
            total_lines = len(lines)

            if params.get("outline", False):
                outline_text = _extract_file_outline(lines, rel_path)
                return ToolResult(
                    success=True,
                    output=outline_text,
                    metadata={
                        "total_lines": total_lines,
                        "outline": True,
                        "path": str(resolved),
                    },
                )

            raw_selected = lines[offset : offset + limit]
            max_line_len = 2000
            capped_lines = []
            for l in raw_selected:
                if len(l) > max_line_len:
                    l = l[:max_line_len] + " ... (line truncated to 2000 chars)"
                capped_lines.append(l)

            max_read_bytes = 50 * 1024
            selected = []
            cur_bytes = 0
            truncated_by_bytes = False
            for l in capped_lines:
                line_bytes = len(l.encode("utf-8")) + 1
                if selected and (cur_bytes + line_bytes > max_read_bytes):
                    truncated_by_bytes = True
                    break
                selected.append(l)
                cur_bytes += line_bytes

            numbered = "\n".join(f"{i + offset + 1}: {line}" for i, line in enumerate(selected))

            truncated = truncated_by_bytes or ((offset + len(selected)) < total_lines)
            if truncated:
                next_offset = offset + len(selected)
                notice = (
                    f"\n\n... (Showing lines {offset + 1}-{next_offset} of {total_lines} total lines. "
                    f"To read further, pass offset={next_offset}) ..."
                )
                numbered += notice

            if session_id:
                cached_limit = len(selected) if truncated_by_bytes else limit
                cache_file_read(
                    session_id,
                    str(resolved),
                    offset,
                    cached_limit,
                    numbered,
                    mtime_ns,
                    size,
                    total_lines,
                )

            return ToolResult(
                success=True,
                output=numbered,
                metadata={
                    "total_lines": total_lines,
                    "showing": len(selected),
                    "offset": offset,
                    "truncated": truncated,
                    "path": str(resolved),
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
