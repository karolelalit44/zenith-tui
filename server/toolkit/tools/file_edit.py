from __future__ import annotations

import logging
from difflib import unified_diff
from typing import Any

from server.agents.session_workspace import evict_read_cache_path, record_write
from server.config.constants import (
    CONCURRENCY_GROUP_WORKSPACE_MUTATION,
    TOOL_DOMAIN_EDIT,
)
from server.toolkit.registry import current_tool_session_id
from server.workspace.ignore import blocked_as_missing, get_matcher, mutation_refusal

from ..base import BaseTool, ToolResult
from ..path_validator import validate_path
from ._line_endings import (
    crlf_normalized_with_offsets,
    local_terminator,
    map_offset,
    terminated,
)
from .file_mutation_queue import FILE_MUTATION_QUEUE

logger = logging.getLogger(__name__)

_BOM = b"\xef\xbb\xbf"

# Match ladders, tried in order. Each entry is (label, key) where ``key``
# normalizes one line for comparison. "exact" keeps the historical behaviour of
# comparing the whole normalized blob; the rest progressively relax whitespace.
_MATCH_LADDER: tuple[tuple[str, str], ...] = (
    ("exact", ""),
    ("trimmed", "rstrip"),
    ("whitespace_normalized", "strip"),
)


def _unified_patch(rel_path: str, before: str, after: str) -> str:
    return "".join(
        unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{rel_path}",
            tofile=f"b/{rel_path}",
        )
    )


def _norm_line(line: str, mode: str) -> str:
    if mode == "rstrip":
        return line.rstrip()
    if mode == "strip":
        return line.strip()
    return line


def _exact_spans(haystack: str, needle: str) -> list[tuple[int, int]]:
    """Every substring occurrence of *needle*, as char spans.

    Substring (not whole-line) matching is deliberate: it is what lets the model
    replace a fragment in the middle of a line.
    """
    spans: list[tuple[int, int]] = []
    start = 0
    while True:
        idx = haystack.find(needle, start)
        if idx == -1:
            return spans
        spans.append((idx, idx + len(needle)))
        start = idx + max(1, len(needle))


def _line_spans(haystack: str, needle: str, mode: str) -> list[tuple[int, int]]:
    """Every whole-line window equal to *needle* under *mode*, as char spans.

    The span covers the matched lines and the newlines between them but not the
    newline that follows the last one, so a line replacement leaves the file's
    line structure intact.
    """
    hay_lines = haystack.split("\n")
    old_lines = needle.split("\n")
    width = len(old_lines)
    if width == 0 or width > len(hay_lines):
        return []
    target = [_norm_line(line, mode) for line in old_lines]
    spans: list[tuple[int, int]] = []
    for i in range(len(hay_lines) - width + 1):
        if [_norm_line(line, mode) for line in hay_lines[i : i + width]] == target:
            start = sum(len(line) + 1 for line in hay_lines[:i])
            end = start + sum(len(line) + 1 for line in hay_lines[i : i + width]) - 1
            spans.append((start, end))
    return spans


def _splice_text(original: str, start: int, end: int, replacement: str) -> str:
    """Replace ``original[start:end]``, re-terminating *replacement* locally.

    Everything outside the replaced range is copied verbatim, so per-line
    endings, blank-line runs and the trailing-newline state of the rest of the
    file are preserved exactly. Only a replacement that lands at EOF needs to
    close its own last line; otherwise the untouched text starting at *end*
    already supplies the line break, and adding another would double it.
    """
    term = local_terminator(original, start)
    tail_newline = end >= len(original) and original.endswith(("\n", "\r"))
    inserted = terminated(replacement, term, tail_newline=tail_newline)
    return original[:start] + "".join(inserted) + original[end:]


class FileEditTool(BaseTool):
    name = "file_edit"
    description = "Edit file via search-replace"
    requires_mode = None
    capability_id = "file_edit"
    read_only = False
    concurrency_group = CONCURRENCY_GROUP_WORKSPACE_MUTATION
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
                "fuzzyMatch": {
                    "type": "boolean",
                    "description": "Opt-in to whitespace-normalized matching (ignores leading indentation) when exact and trailing-whitespace matches fail. Default false — fail closed.",
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
        if blocked_as_missing(get_matcher(workspace_root), rel_path):
            return ToolResult(success=False, error=mutation_refusal(rel_path))
        if not resolved.exists():
            return ToolResult(success=False, error=f"File not found: {rel_path}")
        old = params.get("old_content", "")
        new = params.get("new_content", "")
        if not old:
            return ToolResult(success=False, error="old_content cannot be empty")
        replace_all = bool(params.get("replaceAll") or params.get("replace_all") or False)
        fuzzy = bool(
            params.get("fuzzyMatch") or params.get("fuzzy_match") or params.get("fuzzy") or False
        )
        ladder = _MATCH_LADDER if fuzzy else _MATCH_LADDER[:2]

        try:
            async with FILE_MUTATION_QUEUE.mutation(workspace_root):
                raw = resolved.read_bytes()
                has_bom = raw.startswith(_BOM)
                body = raw[3:] if has_bom else raw
                try:
                    original = body.decode("utf-8")
                except UnicodeDecodeError as exc:
                    return ToolResult(
                        success=False,
                        error=(
                            f"{rel_path} is not valid UTF-8 (invalid byte at offset {exc.start}); "
                            "refusing to edit so existing bytes are never substituted. Re-encode "
                            "the file as UTF-8 first."
                        ),
                    )

                # Match on CRLF-normalized text so LF `old_content` still matches a
                # CRLF file, then map every span back onto the original bytes.
                haystack, offsets = crlf_normalized_with_offsets(original)
                norm_old, _ = crlf_normalized_with_offsets(old)
                spans: list[tuple[int, int]] = []
                match_kind = ""
                for label, mode in ladder:
                    found = (
                        _exact_spans(haystack, norm_old)
                        if mode == ""
                        else _line_spans(haystack, norm_old, mode)
                    )
                    if found:
                        spans = [
                            (map_offset(original, offsets, s), map_offset(original, offsets, e))
                            for s, e in found
                        ]
                        match_kind = label
                        break

                if not spans:
                    preview = old[:80] + ("..." if len(old) > 80 else "")
                    hint = (
                        "Read the file first and copy old_content exactly, add more surrounding "
                        "context, or set fuzzyMatch: true to allow whitespace-normalized matching."
                        if fuzzy
                        else "Read the file first and copy old_content exactly, or add more surrounding context."
                    )
                    return ToolResult(
                        success=False,
                        error=f"Content not found in file (exact match only): {preview}. {hint}",
                    )

                if len(spans) > 1 and not replace_all:
                    kind = "exact" if match_kind == "exact" else f"{match_kind} "
                    return ToolResult(
                        success=False,
                        error=(
                            f"Ambiguous: found {len(spans)} {kind}matches. Provide more "
                            "surrounding context or set replaceAll: true."
                        ),
                    )

                # Apply back-to-front so earlier spans keep their offsets valid.
                new_text = original
                for start, end in reversed(spans):
                    new_text = _splice_text(new_text, start, end, new)

                out_bytes = (_BOM if has_bom else b"") + new_text.encode("utf-8")
                resolved.write_bytes(out_bytes)

                # Read slices are cached per absolute path, so invalidation is
                # global and unconditional: a write from a delegated, background
                # or resumed session must still invalidate the primary session.
                evict_read_cache_path(str(resolved))
                session_id = current_tool_session_id.get() or ""
                if session_id:
                    record_write(session_id, rel_path, new_text)

                logger.info(
                    "Edited %s (%d %s match%s)", rel_path, len(spans), match_kind,
                    "" if len(spans) == 1 else "es",
                )
                return ToolResult(
                    success=True,
                    output=f"Edited {rel_path}",
                    metadata={
                        "path": str(resolved),
                        "changes": len(spans),
                        "match": match_kind,
                        "diff": _unified_patch(rel_path, original, new_text),
                    },
                )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
