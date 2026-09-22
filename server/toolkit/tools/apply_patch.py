from __future__ import annotations

from dataclasses import dataclass, field
from difflib import unified_diff
import re
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
        if (
            s.startswith("*** Add File:")
            or s.startswith("*** Update File:")
            or s.startswith("*** Delete File:")
        ):
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
                    if cur_s.startswith("***") or cur_s.startswith("@@"):
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
    lines: list[str],
    pattern: list[str],
    offset: int,
    comparator: Any,
) -> bool:
    for idx, pat_line in enumerate(pattern):
        if not comparator(lines[offset + idx], pat_line):
            return False
    return True


def _seek(
    lines: list[str],
    pattern: list[str],
    start: int,
    eof: bool = False,
) -> int:
    if not pattern:
        return -1
    comparators = [
        lambda l, r: l == r,
        lambda l, r: l.rstrip() == r.rstrip(),
        lambda l, r: l.strip() == r.strip(),
        lambda l, r: _normalize_unicode(l.strip()) == _normalize_unicode(r.strip()),
    ]
    p_len = len(pattern)
    for comp in comparators:
        if eof:
            offset = len(lines) - p_len
            if offset >= start and offset >= 0:
                if _matches_slice(lines, pattern, offset, comp):
                    return offset
        for offset in range(start, len(lines) - p_len + 1):
            if _matches_slice(lines, pattern, offset, comp):
                return offset
    return -1


def derive_updated_content(
    path: str, chunks: list[UpdateChunk], original: str
) -> str:
    lines = original.split("\n")
    had_trailing_newline = len(lines) > 1 and lines[-1] == ""
    if had_trailing_newline:
        lines.pop()

    replacements: list[tuple[int, int, list[str]]] = []
    line_idx = 0

    for chunk in chunks:
        search_start = line_idx
        if chunk.change_context:
            ctx_found = _seek(lines, [chunk.change_context], line_idx)
            if ctx_found == -1:
                raise ValueError(
                    f"Failed to find context '{chunk.change_context}' in {path}"
                )
            search_start = ctx_found

        if not chunk.old_lines:
            replacements.append((len(lines), 0, chunk.new_lines))
            continue

        old_lines = list(chunk.old_lines)
        new_lines = list(chunk.new_lines)
        found = _seek(lines, old_lines, search_start, chunk.end_of_file)
        if found == -1 and old_lines and old_lines[-1] == "":
            old_lines.pop()
            if new_lines and new_lines[-1] == "":
                new_lines.pop()
            found = _seek(lines, old_lines, line_idx, chunk.end_of_file)

        if found == -1:
            expected = "\n".join(chunk.old_lines)
            raise ValueError(f"Failed to find expected lines in {path}:\n{expected}")

        replacements.append((found, len(old_lines), new_lines))
        line_idx = found + len(old_lines)

    updated = list(lines)
    for start, remove_count, insert_lines in sorted(
        replacements, key=lambda r: r[0], reverse=True
    ):
        updated[start : start + remove_count] = insert_lines

    if had_trailing_newline:
        updated.append("")

    return "\n".join(updated)


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
    permission_scope = PERMISSION_WRITE
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

        for hunk in hunks:
            resolved = validate_path(hunk.path, workspace_root)
            if resolved is None:
                return ToolResult(
                    success=False,
                    error=f"Path escapes workspace boundary: {hunk.path}",
                )

            if hunk.action == "add":
                content = hunk.content or ""
                diff = "".join(
                    unified_diff(
                        [],
                        content.splitlines(keepends=True),
                        fromfile="/dev/null",
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
                old_content = ""
                try:
                    old_content = resolved.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass
                diff = "".join(
                    unified_diff(
                        old_content.splitlines(keepends=True),
                        [],
                        fromfile=f"a/{hunk.path}",
                        tofile="/dev/null",
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
                has_bom = raw_bytes.startswith(b"\xef\xbb\xbf")
                if has_bom:
                    raw_bytes = raw_bytes[3:]
                has_crlf = b"\r\n" in raw_bytes
                original_text = raw_bytes.decode("utf-8", errors="replace").replace(
                    "\r\n", "\n"
                )

                try:
                    updated_text = derive_updated_content(
                        hunk.path, hunk.chunks, original_text
                    )
                except Exception as e:
                    return ToolResult(
                        success=False,
                        error=f"Patch hunk failed for {hunk.path}: {e}",
                    )

                final_text = (
                    updated_text.replace("\n", "\r\n") if has_crlf else updated_text
                )
                out_bytes = (
                    b"\xef\xbb\xbf" + final_text.encode("utf-8")
                    if has_bom
                    else final_text.encode("utf-8")
                )

                diff = "".join(
                    unified_diff(
                        original_text.splitlines(keepends=True),
                        updated_text.splitlines(keepends=True),
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
                        if session_id:
                            evict_file_cache(session_id, str(res_path))
                            record_write(session_id, rel_path, op["content"])

                    elif action == "delete":
                        res_path.unlink(missing_ok=True)
                        affected_files.append(rel_path)
                        if session_id:
                            evict_file_cache(session_id, str(res_path))

                    elif action == "update":
                        target_res = op["move_resolved"] or res_path
                        target_path = op["move_to"] or rel_path

                        target_res.parent.mkdir(parents=True, exist_ok=True)
                        target_res.write_bytes(op["bytes"])

                        if op["move_resolved"] and op["move_resolved"] != res_path:
                            res_path.unlink(missing_ok=True)
                            if session_id:
                                evict_file_cache(session_id, str(res_path))

                        affected_files.append(target_path)
                        if session_id:
                            evict_file_cache(session_id, str(target_res))
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
            return ToolResult(
                success=False,
                error=f"Filesystem mutation failed during patch application: {e}",
            )
