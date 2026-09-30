"""``file_stat`` — address and fingerprint a path without reading it.

Every other way to learn a file's size, line count, or identity requires either
reading it (wasting context on content the model does not need) or running a
shell command (``stat``, ``wc -l``, ``md5sum``, ``git diff``) which is slower and
less precise than a direct filesystem call.

The important output is the fingerprint. A model that read a file, then edited
it, cannot tell whether the file it read is still the file on disk — a build
step, a formatter, or the user may have changed it in between. A content hash
makes that decidable: the mutating tools accept the hash as an expectation, and
a mismatch is reported as a conflict rather than silently overwriting whatever
is there now.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from server.config.constants import (
    CONCURRENCY_GROUP_READONLY,
    TOOL_DOMAIN_READ,
)
from server.workspace.ignore import blocked_as_missing, get_matcher

from ..base import BaseTool, ToolResult
from ..errors import describe
from ..path_validator import not_found_error, path_rejection_error, validate_path
from .file_read import _BINARY_EXTENSIONS, _IMAGE_EXTENSIONS, _is_binary

# Bytes sampled for line counting. Counting the lines of a multi-gigabyte log by
# reading all of it would defeat the point of a metadata tool, so the count is
# explicitly an estimate once the sample is exhausted rather than a silent lie.
_LINE_SAMPLE_BYTES = 256 * 1024
_HASH_CHUNK_BYTES = 1024 * 1024


def _count_lines_sampled(path: Path) -> tuple[int, bool]:
    """``(line_count, exact)`` for the whole file, or for a bounded prefix.

    The full file is walked when it is small enough that doing so costs less
    than the alternative. Past the sample budget the result is reported as
    inexact, because a model that trusts a precise-looking number it did not
    actually compute will page against a line that does not exist.
    """
    size = path.stat().st_size
    if size <= _LINE_SAMPLE_BYTES:
        with path.open("rb") as handle:
            data = handle.read()
        return _count_newlines(data.decode("utf-8", errors="replace")), True
    with path.open("rb") as handle:
        data = handle.read(_LINE_SAMPLE_BYTES)
    return _count_newlines(data.decode("utf-8", errors="replace")), False


def _count_newlines(text: str) -> int:
    if not text:
        return 0
    count = text.count("\n")
    return count if text.endswith("\n") else count + 1


def _content_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


class FileStatTool(BaseTool):
    name = "file_stat"
    description = (
        "Get file metadata without reading its content: size, line count, "
        "modification time, content hash, and whether it is text, binary, or a "
        "directory. Use this to check a file exists and is current before "
        "editing it, or to pass the 'expected_sha256' guard to file_write, "
        "file_edit, file_move, file_copy, or apply_patch so a change made since "
        "the file was read is detected instead of silently overwritten."
    )
    capability_id = "file_metadata"
    read_only = True
    concurrency_group = CONCURRENCY_GROUP_READONLY
    domains = (TOOL_DOMAIN_READ,)

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "File or directory path, relative to the workspace root. "
                        "Omit or use '.' to describe the workspace root itself."
                    ),
                },
                "hash": {
                    "type": "boolean",
                    "description": (
                        "Compute the SHA-256 of the content (default true). Pass "
                        "false for a cheap existence and size check on a very large file."
                    ),
                },
            },
            "required": [],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        rel_path = params.get("path") or "."
        resolved = validate_path(rel_path, workspace_root)
        if resolved is None:
            return ToolResult(success=False, error=path_rejection_error(rel_path, workspace_root) or "Path rejected.")
        if blocked_as_missing(get_matcher(workspace_root), rel_path):
            # Reads of ignored paths are opaque by policy: the same not-found
            # answer a genuinely absent file gets, so the ignore rules are not
            # leaked through the error message.
            return ToolResult(success=False, error=not_found_error(rel_path, workspace_root))
        if not resolved.exists():
            return ToolResult(success=False, error=not_found_error(rel_path, workspace_root))

        try:
            return self._describe(rel_path, resolved, want_hash=params.get("hash", True))
        except Exception as e:
            return ToolResult(
                success=False, error=describe(e, action="stat", path=rel_path)
            )

    def _describe(self, rel_path: str, resolved: Path, *, want_hash: bool) -> ToolResult:
        stat = resolved.stat()
        if resolved.is_dir():
            try:
                entries = len(list(resolved.iterdir()))
            except OSError:
                entries = 0
            return ToolResult(
                success=True,
                output=(
                    f"{rel_path}/ is a directory with {entries} immediate "
                    f"entr{'y' if entries == 1 else 'ies'}"
                ),
                metadata={
                    "path": str(resolved),
                    "is_dir": True,
                    "entries": entries,
                    "modified_at": int(stat.st_mtime),
                },
            )

        is_binary = _is_binary(resolved)
        ext = resolved.suffix.lower()
        lines, exact = (0, True) if is_binary else _count_lines_sampled(resolved)
        sha = _content_hash(resolved) if want_hash else ""

        line_note = "" if exact else "+"
        kind = "image" if is_binary and ext in _IMAGE_EXTENSIONS else (
            "binary" if is_binary else "text"
        )
        lines_out = [
            f"{rel_path} ({kind})",
            f"  size: {stat.st_size} byte(s)",
            f"  lines: {lines}{line_note}",
            f"  modified: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_mtime))}",
        ]
        if sha:
            lines_out.append(f"  sha256: {sha}")
        if not exact:
            lines_out.append(
                "  (line count sampled from the first "
                f"{_LINE_SAMPLE_BYTES // 1024}KB; treat as a lower bound)"
            )
        if is_binary and ext in _BINARY_EXTENSIONS:
            lines_out.append(f"  note: {ext} is a binary format; file_read will refuse it")

        metadata: dict[str, Any] = {
            "path": str(resolved),
            "is_dir": False,
            "is_binary": is_binary,
            "size": stat.st_size,
            "lines": lines,
            "lines_exact": exact,
            "modified_at": int(stat.st_mtime),
        }
        if sha:
            metadata["sha256"] = sha
        return ToolResult(success=True, output="\n".join(lines_out), metadata=metadata)
