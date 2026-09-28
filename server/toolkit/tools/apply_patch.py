from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from difflib import unified_diff
from pathlib import Path
from typing import Any

from server.agents.session_workspace import evict_read_cache_path, record_write
from server.config.constants import (
    CONCURRENCY_GROUP_WORKSPACE_MUTATION,
    TOOL_DOMAIN_EDIT,
)
from server.toolkit.registry import current_tool_session_id
from server.workspace.ignore import (
    blocked_as_missing,
    get_matcher,
    mutation_refusal,
)

from ..base import BaseTool, ToolResult
from ..path_validator import validate_path
from ._line_endings import (
    dominant_terminator,
    line_body,
    line_terminator,
    split_physical_lines,
    terminated,
)
from .file_mutation_queue import FILE_MUTATION_QUEUE

logger = logging.getLogger(__name__)

_BOM = b"\xef\xbb\xbf"


@dataclass
class UpdateChunk:
    old_lines: list[str]
    new_lines: list[str]
    change_context: str | None = None
    end_of_file: bool = False


@dataclass
class PatchHunk:
    action: str  # "add", "delete", "update"
    path: str
    move_to: str | None = None
    content: str | None = None
    chunks: list[UpdateChunk] = field(default_factory=list)


def _strip_envelope(patch_text: str) -> list[str]:
    text = patch_text.strip()
    # Strip markdown code fences if wrapped
    m_fence = re.match(r"^```(?:diff|patch)?\s*\n([\s\S]*?)\n```$", text, re.IGNORECASE)
    if m_fence:
        text = m_fence.group(1).strip()
    # Strip heredoc if wrapped
    m_heredoc = re.match(
        r"^(?:cat\s+)?<<['\"]?(\w+)['\"]?\s*\n([\s\S]*?)\n\1\s*$", text
    )
    if m_heredoc:
        text = m_heredoc.group(2).strip()

    lines = text.split("\n")
    begin_idx = -1
    end_idx = -1
    for i, line in enumerate(lines):
        s = line.strip()
        if s == "*** Begin Patch":
            begin_idx = i
        elif s == "*** End Patch":
            end_idx = i

    if begin_idx != -1 and end_idx != -1 and begin_idx < end_idx:
        return lines[begin_idx + 1 : end_idx]
    if begin_idx != -1:
        return lines[begin_idx + 1 :]

    # If markers not present, look for the first file directive
    first_directive = -1
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith(("*** Add File:", "*** Update File:", "*** Delete File:")):
            first_directive = i
            break
    if first_directive != -1:
        return lines[first_directive:]

    raise ValueError("Invalid patch format: missing Begin/End markers or file directives")


def parse_patch(patch_text: str) -> list[PatchHunk]:
    lines = _strip_envelope(patch_text)
    hunks: list[PatchHunk] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith("*** Add File:"):
            path = line[len("*** Add File:") :].strip()
            if not path:
                raise ValueError(f"Missing file path in '{line}'")
            i += 1
            content_lines: list[str] = []
            while i < n:
                raw_l = lines[i]
                if raw_l.strip().startswith("***"):
                    break
                if raw_l.startswith("+"):
                    content_lines.append(raw_l[1:])
                elif not raw_l.strip():
                    content_lines.append("")
                else:
                    raise ValueError(
                        f"Invalid add file line in '{path}' (expected leading '+'): {raw_l}"
                    )
                i += 1
            hunks.append(
                PatchHunk(action="add", path=path, content="\n".join(content_lines))
            )
            continue

        if line.startswith("*** Delete File:"):
            path = line[len("*** Delete File:") :].strip()
            if not path:
                raise ValueError(f"Missing file path in '{line}'")
            hunks.append(PatchHunk(action="delete", path=path))
            i += 1
            continue

        if line.startswith("*** Update File:"):
            path = line[len("*** Update File:") :].strip()
            if not path:
                raise ValueError(f"Missing file path in '{line}'")
            i += 1
            move_to = None
            if i < n and lines[i].strip().startswith("*** Move to:"):
                move_to = lines[i].strip()[len("*** Move to:") :].strip()
                if not move_to:
                    raise ValueError(f"Missing move-to path in '{lines[i]}'")
                i += 1
            chunks: list[UpdateChunk] = []
            while i < n and not lines[i].strip().startswith("***"):
                chunk_line = lines[i].strip()
                if not chunk_line.startswith("@@"):
                    raise ValueError(
                        f"Invalid update chunk header in '{path}' (expected '@@'): {lines[i]}"
                    )
                change_context = chunk_line[2:].strip() or None
                old_lines: list[str] = []
                new_lines: list[str] = []
                end_of_file = False
                i += 1
                while i < n:
                    cur = lines[i]
                    cur_s = cur.strip()
                    if cur_s == "*** End of File":
                        end_of_file = True
                        i += 1
                        break
                    if cur_s.startswith(("***", "@@")):
                        break
                    if cur.startswith(" "):
                        old_lines.append(cur[1:])
                        new_lines.append(cur[1:])
                    elif cur.startswith("-"):
                        old_lines.append(cur[1:])
                    elif cur.startswith("+"):
                        new_lines.append(cur[1:])
                    elif not cur:
                        old_lines.append("")
                        new_lines.append("")
                    else:
                        raise ValueError(
                            f"Invalid update line in '{path}' (expected ' ', '-', or '+'): {cur}"
                        )
                    i += 1
                chunks.append(
                    UpdateChunk(
                        old_lines=old_lines,
                        new_lines=new_lines,
                        change_context=change_context,
                        end_of_file=end_of_file,
                    )
                )
            if not chunks:
                raise ValueError(
                    f"Invalid update hunk for '{path}': expected at least one '@@' chunk"
                )
            hunks.append(
                PatchHunk(action="update", path=path, move_to=move_to, chunks=chunks)
            )
            continue

        raise ValueError(f"Unexpected patch line: {line}")

    return hunks


def _normalize_unicode(text: str) -> str:
    return (
        text.replace("‘", "'")
        .replace("’", "'")
        .replace("‚", "'")
        .replace("‛", "'")
        .replace("“", '"')
        .replace("”", '"')
        .replace("„", '"')
        .replace("‟", '"')
        .replace("‐", "-")
        .replace("‑", "-")
        .replace("‒", "-")
        .replace("–", "-")
        .replace("—", "-")
        .replace("―", "-")
        .replace("…", "...")
        .replace("\u00a0", " ")
    )


def _matches_slice(
    bodies: list[str],
    order: list[int],
    pattern: list[str],
    offset: int,
    comparator: Any,
) -> bool:
    for idx, pat_line in enumerate(pattern):
        if not comparator(bodies[order[offset + idx]], pat_line):
            return False
    return True


def _seek(
    bodies: list[str],
    order: list[int],
    pattern: list[str],
    start: int,
    eof: bool = False,
) -> int:
    """First position in *order* whose line window matches *pattern*.

    Comparators are tried in order of decreasing strictness, so an exact
    whitespace match always wins over a normalized one.
    """
    if not pattern:
        return -1
    comparators = [
        lambda l, r: l == r,
        lambda l, r: l.rstrip() == r.rstrip(),
        lambda l, r: l.strip() == r.strip(),
        lambda l, r: _normalize_unicode(l.strip()) == _normalize_unicode(r.strip()),
    ]
    p_len = len(pattern)
    n = len(order)
    for comp in comparators:
        if eof and n - p_len >= start >= 0 and _matches_slice(
            bodies, order, pattern, n - p_len, comp
        ):
            return n - p_len
        for offset in range(start, n - p_len + 1):
            if _matches_slice(bodies, order, pattern, offset, comp):
                return offset
    return -1


def _narrow_unchanged_context(
    old_lines: list[str], new_lines: list[str]
) -> int:
    """Strip context lines a chunk quotes but does not change.

    Exact equality only, so a line the model deliberately re-indented is still
    rewritten. Leaving the matches in place means their original terminators
    survive verbatim, which is what stops a one-hunk patch from restyling a file
    that mixes LF and CRLF. Never empties both sides, so a chunk that really
    does delete every line still deletes them. Returns the number of leading
    lines dropped, which shifts the replaced range's start.
    """
    lead = 0
    while len(old_lines) > 1 and len(new_lines) > 1 and old_lines[0] == new_lines[0]:
        old_lines.pop(0)
        new_lines.pop(0)
        lead += 1
    while len(old_lines) > 1 and len(new_lines) > 1 and old_lines[-1] == new_lines[-1]:
        old_lines.pop()
        new_lines.pop()
    return lead


def derive_updated_lines(
    path: str, chunks: list[UpdateChunk], physical: list[str]
) -> list[str]:
    """Apply *chunks* to *physical* and return the new physical lines.

    Lines are tracked by their index into *physical* rather than by value, so
    every line the patch does not touch is re-emitted byte-for-byte. That keeps
    per-line endings (including files that mix LF and CRLF) intact instead of
    normalizing the whole file to one style.
    """
    bodies = [line_body(line) for line in physical]
    order: list[int] = list(range(len(physical)))

    replacements: list[tuple[int, int, list[str], str]] = []
    line_idx = 0

    for chunk in chunks:
        search_start = line_idx
        if chunk.change_context:
            ctx_found = _seek(bodies, order, [chunk.change_context], line_idx)
            if ctx_found == -1:
                raise ValueError(
                    f"Failed to find context '{chunk.change_context}' in {path}"
                )
            search_start = ctx_found

        if not chunk.old_lines:
            # Append-only hunk: no line is replaced, so the inserted group sits
            # after the last line and inherits that line's ending.
            replacements.append(
                (
                    len(order),
                    0,
                    chunk.new_lines,
                    line_terminator(physical[-1]) if physical else "",
                )
            )
            continue

        old_lines = list(chunk.old_lines)
        new_lines = list(chunk.new_lines)
        found = _seek(bodies, order, old_lines, search_start, chunk.end_of_file)
        if found == -1 and old_lines and old_lines[-1] == "":
            old_lines.pop()
            if new_lines and new_lines[-1] == "":
                new_lines.pop()
            found = _seek(bodies, order, old_lines, line_idx, chunk.end_of_file)

        if found == -1:
            expected = "\n".join(chunk.old_lines)
            raise ValueError(
                f"Failed to find expected lines in {path}:\n{expected}"
            )

        consumed = len(old_lines)
        lead = _narrow_unchanged_context(old_lines, new_lines)
        start = found + lead
        # Inherit the ending of the line being replaced so a patched line keeps
        # the style of the line it took the place of.
        term_hint = (
            line_terminator(physical[order[start]])
            if start < len(order) and isinstance(order[start], int)
            else ""
        )
        replacements.append((start, len(old_lines), new_lines, term_hint))
        line_idx = found + consumed

    slots: list[int | tuple[list[str], str]] = list(order)
    for start, remove_count, insert_lines, term_hint in sorted(
        replacements, key=lambda r: r[0], reverse=True
    ):
        slots[start : start + remove_count] = [(insert_lines, term_hint)]

    # An inserted group takes the ending already in force around it, and the
    # file's trailing-newline state is carried by the surviving last line.
    eof_newline = bool(physical) and line_terminator(physical[-1]) != ""
    out: list[str] = []
    for i, slot in enumerate(slots):
        if isinstance(slot, int):
            out.append(physical[slot])
            continue
        insert_lines, term_hint = slot
        next_term = ""
        for later in slots[i + 1 :]:
            if isinstance(later, int):
                next_term = line_terminator(physical[later])
                break
        prev_term = line_terminator(out[-1]) if out else ""
        term = term_hint or prev_term or next_term or dominant_terminator(physical)
        tail_newline = bool(next_term) or i < len(slots) - 1 or eof_newline
        if insert_lines and out and not prev_term:
            # The last surviving line ended at EOF with no terminator, so the
            # first inserted line would be glued onto it. Close it first.
            out[-1] += term
        out.extend(
            terminated("\n".join(insert_lines), term, tail_newline=tail_newline)
        )
    return out


class ApplyPatchTool(BaseTool):
    name = "apply_patch"
    description = (
        "Apply a unified multi-file patch containing Add File, Delete File, or Update File actions. "
        "Matches and validates context lines before updating files."
    )
    requires_mode = None
    capability_id = "apply_patch"
    read_only = False
    concurrency_group = CONCURRENCY_GROUP_WORKSPACE_MUTATION
    domains = (TOOL_DOMAIN_EDIT,)
    search_terms = (
        "patch",
        "apply patch",
        "diff",
        "multi file edit",
        "batch edit",
    )

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "patch": {
                    "type": "string",
                    "description": (
                        "Patch text adhering to the unified patch format "
                        "(*** Begin Patch ... *** Add File / *** Update File / *** Delete File ... *** End Patch)"
                    ),
                }
            },
            "required": ["patch"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        patch_text = params.get("patch") or ""
        if not patch_text.strip():
            return ToolResult(success=False, error="Missing or empty patch parameter")

        try:
            hunks = parse_patch(patch_text)
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to parse patch: {e}")

        if not hunks:
            return ToolResult(success=False, error="Patch contains no file operations")

        # Phase 1: Dry run validation and derivation
        prepared_operations: list[dict[str, Any]] = []
        combined_diffs: list[str] = []
        matcher = get_matcher(workspace_root)

        for hunk in hunks:
            resolved = validate_path(hunk.path, workspace_root)
            if resolved is None:
                return ToolResult(
                    success=False,
                    error=f"Path escapes workspace boundary: {hunk.path}",
                )
            # Ignored paths are invisible to every other tool, so a patch must
            # not be able to create, rewrite or delete them.
            if blocked_as_missing(matcher, hunk.path):
                return ToolResult(success=False, error=mutation_refusal(hunk.path))
            if hunk.move_to and blocked_as_missing(matcher, hunk.move_to):
                return ToolResult(success=False, error=mutation_refusal(hunk.move_to))

            if hunk.action == "add":
                content = hunk.content or ""
                diff = "".join(
                    unified_diff(
                        [],
                        content.splitlines(keepends=True),
                        fromfile=os.devnull,
                        tofile=f"b/{hunk.path}",
                    )
                )
                combined_diffs.append(diff)
                prepared_operations.append(
                    {
                        "action": "add",
                        "path": hunk.path,
                        "resolved": resolved,
                        "content": content,
                        "bytes": content.encode("utf-8"),
                    }
                )

            elif hunk.action == "delete":
                if not resolved.exists():
                    return ToolResult(
                        success=False,
                        error=f"Cannot delete nonexistent file: {hunk.path}",
                    )
                try:
                    old_content = resolved.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    old_content = ""
                diff = "".join(
                    unified_diff(
                        old_content.splitlines(keepends=True),
                        [],
                        fromfile=f"a/{hunk.path}",
                        tofile=os.devnull,
                    )
                )
                combined_diffs.append(diff)
                prepared_operations.append(
                    {
                        "action": "delete",
                        "path": hunk.path,
                        "resolved": resolved,
                    }
                )

            elif hunk.action == "update":
                if not resolved.exists():
                    return ToolResult(
                        success=False,
                        error=f"Cannot update nonexistent file: {hunk.path}",
                    )
                move_resolved = None
                if hunk.move_to:
                    move_resolved = validate_path(hunk.move_to, workspace_root)
                    if move_resolved is None:
                        return ToolResult(
                            success=False,
                            error=f"Move destination escapes workspace boundary: {hunk.move_to}",
                        )

                raw_bytes = resolved.read_bytes()
                has_bom = raw_bytes.startswith(_BOM)
                body = raw_bytes[3:] if has_bom else raw_bytes
                try:
                    original_text = body.decode("utf-8")
                except UnicodeDecodeError as exc:
                    return ToolResult(
                        success=False,
                        error=(
                            f"{hunk.path} is not valid UTF-8 (invalid byte at offset "
                            f"{exc.start}); refusing to patch so existing bytes are never "
                            "substituted. Re-encode the file as UTF-8 first."
                        ),
                    )

                # Match on logical lines but keep every untouched physical line
                # verbatim, so a file mixing LF and CRLF is not restyled wholesale.
                physical = split_physical_lines(original_text)
                try:
                    updated_physical = derive_updated_lines(
                        hunk.path, hunk.chunks, physical
                    )
                except Exception as e:
                    return ToolResult(
                        success=False,
                        error=f"Patch hunk failed for {hunk.path}: {e}",
                    )

                final_text = "".join(updated_physical)
                out_bytes = (
                    (_BOM if has_bom else b"") + final_text.encode("utf-8")
                )

                diff = "".join(
                    unified_diff(
                        original_text.splitlines(keepends=True),
                        final_text.splitlines(keepends=True),
                        fromfile=f"a/{hunk.path}",
                        tofile=f"b/{hunk.move_to or hunk.path}",
                    )
                )
                combined_diffs.append(diff)
                prepared_operations.append(
                    {
                        "action": "update",
                        "path": hunk.path,
                        "move_to": hunk.move_to,
                        "resolved": resolved,
                        "move_resolved": move_resolved,
                        "content": final_text,
                        "bytes": out_bytes,
                    }
                )

        # Phase 2: Execute atomic mutations on disk
        session_id = current_tool_session_id.get() or ""
        affected_files: list[str] = []

        # Rollback ledger. Every path this patch will touch is snapshotted during
        # the dry run, so a failure part-way through can put the workspace back
        # exactly as it was. Reporting failure while leaving hunks 1..n applied
        # is worse than failing: the model retries a patch whose hunks are already
        # on disk and then fails on context mismatch.
        snapshots: list[tuple[Path, bytes | None]] = []
        for op in prepared_operations:
            for path in (op["resolved"], op.get("move_resolved")):
                if path is None:
                    continue
                if any(path is seen for seen, _ in snapshots):
                    continue
                snapshots.append((path, path.read_bytes() if path.exists() else None))

        def _rollback() -> tuple[list[str], list[str]]:
            restored: list[str] = []
            failed: list[str] = []
            for path, original_bytes in reversed(snapshots):
                try:
                    if original_bytes is None:
                        path.unlink(missing_ok=True)
                    else:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(original_bytes)
                    restored.append(str(path))
                except OSError as rollback_err:
                    failed.append(str(path))
                    logger.error("Rollback failed for %s: %s", path, rollback_err)
            return restored, failed

        try:
            async with FILE_MUTATION_QUEUE.mutation(workspace_root):
                for op in prepared_operations:
                    action = op["action"]
                    res_path = op["resolved"]
                    rel_path = op["path"]

                    if action == "add":
                        res_path.parent.mkdir(parents=True, exist_ok=True)
                        res_path.write_bytes(op["bytes"])
                        affected_files.append(rel_path)
                        evict_read_cache_path(str(res_path))
                        if session_id:
                            record_write(session_id, rel_path, op["content"])

                    elif action == "delete":
                        res_path.unlink(missing_ok=True)
                        affected_files.append(rel_path)
                        evict_read_cache_path(str(res_path))

                    elif action == "update":
                        target_res = op["move_resolved"] or res_path
                        target_path = op["move_to"] or rel_path

                        target_res.parent.mkdir(parents=True, exist_ok=True)
                        target_res.write_bytes(op["bytes"])

                        if op["move_resolved"] and op["move_resolved"] != res_path:
                            res_path.unlink(missing_ok=True)
                            evict_read_cache_path(str(res_path))

                        affected_files.append(target_path)
                        evict_read_cache_path(str(target_res))
                        if session_id:
                            record_write(session_id, target_path, op["content"])

            summary_msg = f"Applied patch to {len(affected_files)} file(s):\n" + "\n".join(
                f"- {f}" for f in affected_files
            )
            return ToolResult(
                success=True,
                output=summary_msg,
                metadata={
                    "files": affected_files,
                    "count": len(affected_files),
                    "diff": "\n".join(combined_diffs),
                },
            )
        except Exception as e:
            restored, unrestored = _rollback()
            for path, _ in snapshots:
                evict_read_cache_path(str(path))
            if unrestored:
                # Never let a partial restore read as a clean failure: the model
                # would retry a patch whose hunks may already be on disk.
                detail = (
                    f"Filesystem mutation failed during patch application: {e}. "
                    f"ROLLBACK INCOMPLETE — {len(restored)} file(s) were restored, but these "
                    f"could not be: {', '.join(unrestored)}. Inspect them before retrying."
                )
            else:
                detail = (
                    f"Filesystem mutation failed during patch application: {e}. "
                    f"The workspace was restored to its pre-patch state "
                    f"({len(restored)} file(s) rolled back) — re-read the files before retrying."
                )
            logger.error(
                "apply_patch failed on %s: %s (rolled back %d, unrestored %d)",
                ", ".join(affected_files) or "<none>",
                e,
                len(restored),
                len(unrestored),
            )
            return ToolResult(success=False, error=detail)
