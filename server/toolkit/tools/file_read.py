from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from server.agents.session_workspace import (
    cache_file_read,
    covering_slice_for,
    get_cached_read_entry,
)
from server.config.constants import (
    CONCURRENCY_GROUP_READONLY,
    DEFAULT_FILE_READ_LINES,
    MAX_FILE_READ_LINES,
    TOOL_DOMAIN_READ,
)
from server.toolkit.registry import current_tool_session_id

from ..base import BaseTool, ToolResult
from ..errors import describe
from ..path_validator import not_found_error, path_rejection_error, validate_path

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


def _render_window(body: str, offset: int, shown: int, total_lines: int) -> tuple[str, bool]:
    """Append the continuation notice when the window does not reach EOF."""
    truncated = shown > 0 and (offset + shown) < total_lines
    return (body + _page_notice(offset, shown, total_lines) if truncated else body, truncated)


def _resolve_window(params: dict[str, Any]) -> tuple[int, int, str | None]:
    """Validate and normalise the read window. Returns ``(offset, limit, error)``.

    ``limit`` is bounded to ``[1, MAX_FILE_READ_LINES]``. The lower bound is the
    part that matters: an unclamped negative limit reaches ``lines[offset:offset+limit]``
    and Python reads that as a negative slice, silently returning the file minus
    its last ``|limit|`` lines and reporting success. A bad window is a caller
    error, so it is rejected with the corrected call rather than executed.
    """
    raw_offset = params.get("offset")
    if raw_offset is None:
        raw_offset = 0
    try:
        offset = int(raw_offset)
    except (TypeError, ValueError):
        return (
            0,
            0,
            f"Invalid offset {raw_offset!r}: offset must be an integer line index where 0 is the first line.",
        )
    if offset < 0:
        return (
            0,
            0,
            f"Invalid offset {offset}: offset must be >= 0 (0 is the first line).",
        )

    raw_limit = params.get("limit")
    if raw_limit is None:
        return offset, DEFAULT_FILE_READ_LINES, None
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        return (
            offset,
            0,
            f"Invalid limit {raw_limit!r}: limit must be an integer line count.",
        )
    if limit < 1:
        return (
            offset,
            0,
            f"Invalid limit {limit}: limit must be >= 1 line. "
            f"Omit 'limit' to read the default {DEFAULT_FILE_READ_LINES} lines, "
            f"or pass offset to continue past this window.",
        )
    return offset, min(limit, MAX_FILE_READ_LINES), None


def _read_window(
    path: Path, offset: int, limit: int
) -> tuple[list[str] | None, int, bool]:
    """``(selected_lines, total_lines, total_is_exact)`` for a window, read in bounded memory.

    Only the requested window is retained. The line count is streamed alongside
    it, so a 1GB log costs a fixed amount of memory rather than 1GB of resident
    heap to return 250 lines.

    Counting every line still means reading every byte, so past
    ``_TOTAL_COUNT_BYTE_CAP`` the count stops and is reported as a lower bound
    rather than as a precise figure. A model told "of 40000 total lines" will
    page against that number; a model told an approximation will not, which is
    the whole point of labelling it.

    A trailing carriage return is stripped from each returned line so a CRLF
    file reads as clean text, matching what the model was shown before the read
    was made streaming. Leaving it in place would invite the model to copy a
    literal ``\\r`` into ``old_content``, which is exactly the kind of invisible
    character that makes a content-addressed edit fail on the second attempt.
    """
    collected: list[str] = []
    seen = 0
    total = 0
    pending = ""
    want_end = offset + limit
    exact = True
    scanned = 0
    tail_is_line = False

    with path.open("rb") as handle:
        while True:
            if scanned >= _TOTAL_COUNT_BYTE_CAP:
                exact = False
                break
            chunk = handle.read(min(_READ_CHUNK_BYTES, _TOTAL_COUNT_BYTE_CAP - scanned))
            if not chunk:
                tail_is_line = bool(pending)
                break
            scanned += len(chunk)
            pending += chunk.decode("utf-8", errors="replace")
            parts = pending.split("\n")
            # The final element is either an incomplete line or the empty string
            # when the chunk ended exactly on a newline. Either way it is not yet
            # a countable line.
            pending = parts.pop()
            for line in parts:
                total += 1
                if offset <= seen < want_end:
                    collected.append(line[:-1] if line.endswith("\r") else line)
                seen += 1

    if tail_is_line:
        total += 1
        if offset <= seen < want_end:
            tail = pending[:-1] if pending.endswith("\r") else pending
            collected.append(tail)

    past_end = offset >= total and total > 0
    return (None if past_end else collected), total, exact


_LINE_PREFIX_RE = re.compile(r"^(\d+): ")


def _split_lines(content: str) -> list[str]:
    """Split file content into the lines a reader actually sees.

    ``str.split("\\n")`` is the obvious implementation and it is wrong: a file
    that ends with a newline yields a trailing empty element, so ``"a\\nb\\n"``
    counts as three lines instead of two. Every newline-terminated file — which
    is nearly all of them — would then over-report its length by one, and the
    pagination hint computed from that count points one line past the end, where
    the read returns nothing. The trailing element is an artefact of the
    separator, not a line, so it is dropped.

    An empty file has zero lines, not one.
    """
    if not content:
        return []
    lines = content.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


_READ_CHUNK_BYTES = 64 * 1024
# Past this size the line count stops being exact. The window itself is still
# complete; only the denominator of the pagination hint becomes a lower bound.
_TOTAL_COUNT_BYTE_CAP = 4 * 1024 * 1024


def _page_notice(offset: int, shown: int, total_lines: int, exact: bool = True) -> str:
    """The continuation hint appended to a partial read.

    Every truncated read must end with the exact next call, otherwise the model
    has no way to resume and will either re-read the same window or give up on
    the file. Regenerated verbatim on the cached path so a cache hit is
    indistinguishable from a cold read of the same range.
    """
    next_offset = offset + shown
    return (
        f"\n\n... (Showing lines {offset + 1}-{next_offset} of {total_lines} total lines. "
        f"To read further, pass offset={next_offset}) ..."
    )


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
            return ToolResult(success=False, error=path_rejection_error(rel_path, workspace_root) or "Path rejected.")
        if not resolved.exists():
            return ToolResult(success=False, error=not_found_error(rel_path, workspace_root))
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

            offset, limit, err = _resolve_window(params)
            if err is not None:
                return ToolResult(success=False, error=err)

            cached_entry = (
                get_cached_read_entry(session_id, str(resolved), offset, limit, mtime_ns, size)
                if session_id
                else None
            )
            if cached_entry is not None:
                return ToolResult(
                    success=True,
                    output=str(cached_entry.get("output", "")),
                    metadata={**dict(cached_entry.get("metadata") or {}), "from_cache": True},
                )

            # Sub-slice: the requested range may be fully contained within an
            # already-cached, unchanged slice. Extract the numbered lines directly
            # from the cached formatted output so no disk read is needed. The
            # pagination state is rebuilt for the requested range rather than
            # inherited from the covering one, because the two describe different
            # windows of the file.
            if session_id:
                covering = covering_slice_for(
                    session_id, str(resolved), offset, limit, mtime_ns=mtime_ns, size=size
                )
                if covering is not None:
                    h_offset, h_limit = covering
                    covering_entry = get_cached_read_entry(
                        session_id, str(resolved), h_offset, h_limit, mtime_ns, size
                    )
                    if covering_entry is not None:
                        subslice = _subslice_from_cached(
                            str(covering_entry.get("output", "")), h_offset, offset, limit
                        )
                        if subslice is not None:
                            total = int(
                                (covering_entry.get("metadata") or {}).get("total_lines") or 0
                            )
                            shown = len(subslice.splitlines())
                            body, truncated = _render_window(subslice, offset, shown, total)
                            return ToolResult(
                                success=True,
                                output=body,
                                metadata={
                                    "total_lines": total,
                                    "showing": shown,
                                    "offset": offset,
                                    "truncated": truncated,
                                    "path": str(resolved),
                                    "from_cache": True,
                                },
                            )

            # Read a bounded window straight off the disk instead of loading the
            # file. A 1GB log must not become 1GB of resident memory to return
            # 250 lines, and the previous whole-file read also meant the cost of
            # a read scaled with the size of the file rather than the size of
            # the answer.
            window, total_lines, total_exact = _read_window(resolved, offset, limit)
            if window is None:
                return ToolResult(
                    success=False,
                    error=(
                        f"offset {offset} is past the end of {rel_path} "
                        f"({total_lines} lines). Highest valid offset is "
                        f"{max(0, total_lines - 1)}. Pass offset=0 to read from the start."
                    ),
                    metadata={"total_lines": total_lines, "offset": offset, "path": str(resolved)},
                )

            if params.get("outline", False):
                # An outline is a whole-file view, so it cannot come from a
                # bounded window; fall back to a full read for this one case.
                outline_text = _extract_file_outline(
                    _split_lines(resolved.read_text(encoding="utf-8", errors="replace")),
                    rel_path,
                )
                return ToolResult(
                    success=True,
                    output=outline_text,
                    metadata={
                        "total_lines": total_lines,
                        "outline": True,
                        "path": str(resolved),
                    },
                )

            if total_lines == 0:
                return ToolResult(
                    success=True,
                    output="",
                    metadata={
                        "total_lines": 0,
                        "showing": 0,
                        "offset": 0,
                        "truncated": False,
                        "empty": True,
                        "path": str(resolved),
                    },
                )

            raw_selected = window
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
                numbered += _page_notice(offset, len(selected), total_lines, total_exact)
            elif not total_exact:
                numbered += (
                    f"\n\n... (File is larger than "
                    f"{_TOTAL_COUNT_BYTE_CAP // (1024 * 1024)}MB, so the line count is a "
                    f"lower bound of {total_lines}. Keep paging with offset= to reach "
                    f"further.) ..."
                )
                truncated = True

            metadata = {
                "total_lines": total_lines,
                "showing": len(selected),
                "offset": offset,
                "truncated": truncated,
                "path": str(resolved),
            }

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
                    metadata=metadata,
                )

            return ToolResult(success=True, output=numbered, metadata=metadata)
        except Exception as e:
            return ToolResult(success=False, error=describe(e, action="read", path=rel_path))
