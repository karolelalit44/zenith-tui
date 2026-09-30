from __future__ import annotations

import hashlib
import logging
from difflib import unified_diff
from typing import Any

from server.agents.session_workspace import evict_read_cache_path, record_write
from server.config.constants import (
    CONCURRENCY_GROUP_WORKSPACE_MUTATION,
    EXPECTED_HASH_PARAM,
    TOOL_DOMAIN_EDIT,
)
from server.toolkit.registry import current_tool_session_id
from server.workspace.ignore import blocked_as_missing, get_matcher, mutation_refusal

from ..base import BaseTool, ToolResult
from ..errors import conflict_error, describe
from ..journal import JOURNAL
from ..path_validator import not_found_error, path_rejection_error, validate_path
from ._line_endings import (
    crlf_normalized_with_offsets,
    line_terminator,
    local_terminator,
    map_offset,
    split_physical_lines,
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


def _line_count(text: str) -> int:
    """How many lines a body of text occupies.

    A trailing newline terminates the last line; it does not begin a new one.
    Counting it as a line would report a 5-line file as 7 lines, which is the
    same off-by-one the read tool was corrected for — and a receipt that
    overstates the file size is worse than no receipt, because the model
    trusts it over its own re-read.
    """
    if not text:
        return 0
    count = text.count("\n")
    return count if text.endswith("\n") else count + 1


def _line_range_spans(
    original: str, start_line: Any, end_line: Any
) -> tuple[list[tuple[int, int]], str]:
    """Char spans for a 1-based inclusive line range, plus an error string.

    Positional addressing exists because content-addressed editing has a real
    failure mode: to change line 147 the model must first read it and then
    reproduce its bytes exactly, including indentation, trailing whitespace and
    any invisible characters. Get one of those wrong and the edit is rejected,
    which sends the model to ``sed`` or a Python one-liner instead — a shell
    escape that a dedicated file tool was supposed to make unnecessary.

    The span deliberately excludes the terminator that follows the last
    replaced line, so the rest of the file keeps its own line endings and
    blank-line runs byte for byte, exactly as a content-matched edit does.
    """
    if start_line is None:
        return [], (
            "start_line is required when addressing by position. "
            "Pass start_line (1-based) and optionally end_line."
        )
    try:
        first = int(start_line)
    except (TypeError, ValueError):
        return [], f"Invalid start_line {start_line!r}: must be an integer line number (1-based)."
    if first < 1:
        return [], f"Invalid start_line {first}: line numbers are 1-based, so the first line is 1."

    lines = split_physical_lines(original)
    total = len(lines)
    if not lines:
        return [], f"{'The file'} is empty (0 lines); there is nothing to replace."
    if first > total:
        return [], (
            f"start_line {first} is past the end of the file ({total} lines). "
            f"Highest valid line is {total}."
        )

    if end_line is None:
        last = first
    else:
        try:
            last = int(end_line)
        except (TypeError, ValueError):
            return [], f"Invalid end_line {end_line!r}: must be an integer line number."
        if last < first:
            return [], (
                f"end_line {last} is before start_line {first}. "
                f"end_line is inclusive and must be >= start_line."
            )
        if last > total:
            return [], (
                f"end_line {last} is past the end of the file ({total} lines). "
                f"Highest valid line is {total}."
            )

    start = sum(len(line) for line in lines[: first - 1])
    end = sum(len(line) for line in lines[:last])
    # Back off the terminator that closes the last replaced line. _splice_text
    # only re-terminates the replacement when the span reaches EOF, so leaving
    # the terminator inside the span would drop it and glue the replacement onto
    # whatever follows. Excluding it keeps the untouched text at `end` supplying
    # the line break, which is what preserves the surrounding file byte for byte.
    if end > start:
        end -= len(line_terminator(lines[last - 1]))
    return [(start, end)], ""


def _edit_receipt(
    rel_path: str,
    original: str,
    spans: list[tuple[int, int]],
    replacement: str,
    new_text: str,
    match_kind: str,
) -> str:
    """The model-visible confirmation for a completed edit.

    An edit used to report only ``Edited <path>``. That is not a receipt: it
    cannot be distinguished from a no-op, it says nothing about *where* the
    change landed, and it hides the fact that a loosened rung of the match
    ladder was used. The model therefore had no way to confirm its intent
    without re-reading the file — which defeats the point of a self-verifying
    tool call and is exactly what pushes an agent toward a redundant re-read.

    The receipt states where the change landed, how many lines were added and
    removed, which match rung fired, and the resulting file size. It is
    deliberately a receipt and not a diff: any non-trivial diff would be
    truncated here, and the full unified diff already reaches the user through
    the event metadata at no token cost.
    """
    first_start = min(s for s, _ in spans)
    last_end = max(e for _, e in spans)
    start_line = original.count("\n", 0, first_start) + 1
    end_line = start_line + original[first_start:last_end].count("\n")

    removed = sum(original[s:e].count("\n") + 1 for s, e in spans if original[s:e])
    added = _line_count(replacement) * len(spans)

    # A line-range edit is a different addressing mode, not a loosened match.
    # Labelling it "loosened" would tell the model its positional request was
    # fuzzy-matched, which is a different and misleading claim.
    if match_kind == "line_range":
        rung = "addressed by line range"
    elif match_kind == "exact":
        rung = "exact"
    else:
        rung = f"{match_kind} (loosened match)"
    result_lines = _line_count(new_text)

    if len(spans) == 1:
        where = f"line {start_line}" if end_line <= start_line else f"lines {start_line}-{end_line}"
    else:
        where = (
            f"{len(spans)} separate regions, first at line {start_line}, "
            f"last ending at line {end_line}"
        )

    return (
        f"Edited {rel_path}\n"
        f"  {where} replaced (+{added} -{removed} lines), match={rung}\n"
        f"  file is now {result_lines} line(s), {len(new_text.encode('utf-8'))} byte(s)"
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
                "old_content": {
                    "type": "string",
                    "description": (
                        "Text to replace, copied exactly from the file. Omit when "
                        "using start_line/end_line."
                    ),
                },
                "new_content": {"type": "string", "description": "Replacement text"},
                "start_line": {
                    "type": "integer",
                    "description": (
                        "1-based first line to replace. Use with end_line to address a "
                        "region by position instead of by content — preferred when the "
                        "replacement is known but the exact existing text is not."
                    ),
                },
                "end_line": {
                    "type": "integer",
                    "description": (
                        "1-based last line to replace, inclusive. Omit to replace only "
                        "start_line."
                    ),
                },
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
                EXPECTED_HASH_PARAM: {
                    "type": "string",
                    "description": (
                        "Optional SHA-256 of the file as last read (from file_stat). The "
                        "edit is refused if the file changed since, instead of applying "
                        "to content nobody reviewed."
                    ),
                },
            },
            "required": ["path", "new_content"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        rel_path = params.get("path") or ""
        resolved = validate_path(rel_path, workspace_root)
        if resolved is None:
            return ToolResult(success=False, error=path_rejection_error(rel_path, workspace_root) or "Path rejected.")
        if blocked_as_missing(get_matcher(workspace_root), rel_path):
            return ToolResult(success=False, error=mutation_refusal(rel_path))
        if not resolved.exists():
            return ToolResult(
                success=False, error=not_found_error(rel_path, workspace_root)
            )
        new = params.get("new_content", "")
        replace_all = bool(params.get("replaceAll") or params.get("replace_all") or False)
        fuzzy = bool(
            params.get("fuzzyMatch") or params.get("fuzzy_match") or params.get("fuzzy") or False
        )
        ladder = _MATCH_LADDER if fuzzy else _MATCH_LADDER[:2]
        start_line = params.get("start_line", params.get("startLine"))
        end_line = params.get("end_line", params.get("endLine"))
        by_position = start_line is not None or end_line is not None

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
                expected = params.get(EXPECTED_HASH_PARAM)
                if expected:
                    actual = hashlib.sha256(raw).hexdigest()
                    if actual != expected:
                        return ToolResult(
                            success=False, error=conflict_error(rel_path)
                        )

                spans: list[tuple[int, int]] = []
                match_kind = "line_range"
                old = ""
                if by_position:
                    resolved_spans, range_error = _line_range_spans(
                        original, start_line, end_line
                    )
                    if range_error:
                        return ToolResult(success=False, error=range_error)
                    spans = resolved_spans
                else:
                    old = params.get("old_content", "")
                    if not old:
                        return ToolResult(success=False, error="old_content cannot be empty")
                    haystack, offsets = crlf_normalized_with_offsets(original)
                    norm_old, _ = crlf_normalized_with_offsets(old)
                    for label, mode in ladder:
                        found = (
                            _exact_spans(haystack, norm_old)
                            if mode == ""
                            else _line_spans(haystack, norm_old, mode)
                        )
                        if found:
                            spans = [
                                (
                                    map_offset(original, offsets, s),
                                    map_offset(original, offsets, e),
                                )
                                for s, e in found
                            ]
                            match_kind = label
                            break

                    if not spans:
                        preview = old[:80] + ("..." if len(old) > 80 else "")
                        hint = (
                            "Read the file first and copy old_content exactly, add more surrounding "
                            "context, or set fuzzyMatch: true to allow whitespace-normalized matching. "
                            "Alternatively address the region by position with start_line/end_line."
                            if fuzzy
                            else "Read the file first and copy old_content exactly, or add more surrounding "
                            "context. Alternatively address the region by position with start_line/end_line."
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
                    JOURNAL.record(
                        session_id,
                        tool="file_edit",
                        path=resolved,
                        action="modify",
                        before=raw,
                        after=out_bytes,
                        extra={"match": match_kind, "spans": len(spans)},
                    )

                logger.info(
                    "Edited %s (%d %s match%s)", rel_path, len(spans), match_kind,
                    "" if len(spans) == 1 else "es",
                )
                receipt = _edit_receipt(rel_path, original, spans, new, new_text, match_kind)
                return ToolResult(
                    success=True,
                    output=receipt,
                    metadata={
                        "path": str(resolved),
                        "changes": len(spans),
                        "match": match_kind,
                        "diff": _unified_patch(rel_path, original, new_text),
                    },
                )
        except Exception as e:
            return ToolResult(success=False, error=describe(e, action="edit", path=rel_path))
