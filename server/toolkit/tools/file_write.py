from __future__ import annotations

import hashlib
from typing import Any

from server.agents.session_workspace import evict_read_cache_path, record_write
from server.config.constants import (
    CONCURRENCY_GROUP_WORKSPACE_MUTATION,
    EXPECTED_HASH_PARAM,
    FILE_ALREADY_EXISTS_ERROR,
    FILE_OVERWRITE_PARAM,
    TOOL_DOMAIN_EDIT,
)
from server.toolkit.registry import current_tool_session_id
from server.workspace.ignore import blocked_as_missing, get_matcher, mutation_refusal

from ..base import BaseTool, ToolResult
from ..errors import conflict_error, describe
from ..journal import JOURNAL
from ..path_validator import path_rejection_error, validate_path
from .file_mutation_queue import FILE_MUTATION_QUEUE


def _line_count(text: str) -> int:
    """Lines a body of text occupies; a trailing newline closes the last line
    rather than opening a new one."""
    if not text:
        return 0
    count = text.count("\n")
    return count if text.endswith("\n") else count + 1


def norm_content_join(existing: str, joiner: str, addition: str) -> str:
    """Existing text, a separator if one is needed, then the addition."""
    return existing + joiner + addition


def _looks_binary(raw: bytes) -> bool:
    """Cheap binary sniff, mirroring the read tool's content rule.

    Overwriting is destructive and irreversible, so a file that is not text must
    be refused rather than silently replaced with UTF-8. Reading it back with
    ``errors="replace"`` would turn every non-UTF-8 byte into U+FFFD and destroy
    the original encoding without saying so.
    """
    if not raw:
        return False
    if b"\x00" in raw[:1024]:
        return True
    chunk = raw[:1024]
    non_printable = sum(1 for b in chunk if b < 9 or (13 < b < 32))
    return non_printable / len(chunk) > 0.3


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
                "mode": {
                    "type": "string",
                    "enum": ["create", "overwrite", "append"],
                    "description": (
                        "create: fail if the file exists (default). overwrite: replace the "
                        "whole content, failing only if the file is absent. append: add to "
                        "the end of an existing file. 'append' is the operation a shell "
                        "'>>' redirect would do; prefer it over reading a file to append."
                    ),
                },
                "line_endings": {
                    "type": "string",
                    "enum": ["preserve", "lf", "crlf"],
                    "description": (
                        "preserve (default): keep the destination file's existing line "
                        "endings and BOM. lf/crlf: force the given ending, converting the "
                        "content accordingly."
                    ),
                },
                EXPECTED_HASH_PARAM: {
                    "type": "string",
                    "description": (
                        "Optional SHA-256 of the file as last read (from file_stat). The "
                        "write is refused if the file changed since, instead of "
                        "overwriting content nobody reviewed."
                    ),
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
                error=path_rejection_error(rel_path, workspace_root) or "Path rejected.",
            )
        if blocked_as_missing(get_matcher(workspace_root), rel_path):
            return ToolResult(success=False, error=mutation_refusal(rel_path))
        content = params.get("content", "")
        overwrite = bool(params.get(FILE_OVERWRITE_PARAM, False))
        mode = params.get("mode", "create")
        if mode not in ("create", "overwrite", "append"):
            return ToolResult(
                success=False,
                error=(
                    f"Invalid mode {mode!r}. Use 'create' (default, fails if the file "
                    f"exists), 'overwrite' (replaces the whole content), or 'append'."
                ),
            )
        if mode in ("overwrite", "append"):
            # Both operate on a file that must already exist, so the
            # "already exists" gate below must not fire for them.
            overwrite = True
        existed = resolved.exists()
        if resolved.is_dir():
            # A directory does "already exist", so without this check the model
            # is told to pass overwrite: true — advice that cannot possibly work
            # and that the model has no way to discover is wrong.
            return ToolResult(
                success=False,
                error=(
                    f"Path is a directory: {rel_path}. Use list_dir to inspect it, "
                    f"or pass a file path inside it. A directory cannot be overwritten "
                    f"by file_write."
                ),
            )
        if mode == "overwrite" and not existed:
            return ToolResult(
                success=False,
                error=(
                    f"Cannot overwrite {rel_path}: it does not exist. "
                    f"Use mode 'create' to create a new file, or file_copy/file_move "
                    f"if you meant to relocate an existing one."
                ),
            )
        if existed and (not overwrite):
            return ToolResult(
                success=False,
                error=FILE_ALREADY_EXISTS_ERROR.format(
                    path=rel_path, overwrite_param=FILE_OVERWRITE_PARAM
                ),
            )
        try:
            # Probe and mutate inside one critical section. Reading the existing
            # encoding outside the lock leaves a window in which a concurrent
            # writer can change the file between the probe and the write, so the
            # bytes written would be encoded for a file that no longer exists.
            async with FILE_MUTATION_QUEUE.mutation(workspace_root):
                has_bom = False
                existing_text = ""
                before_bytes: bytes | None = None
                if existed:
                    before_bytes = resolved.read_bytes()
                    if _looks_binary(before_bytes):
                        return ToolResult(
                            success=False,
                            error=(
                                f"{rel_path} is not text; refusing to overwrite it because "
                                f"the write would destroy {len(before_bytes)} byte(s) of binary "
                                f"content. Use a tool that understands the format, or delete "
                                f"the file deliberately first."
                            ),
                        )
                    has_bom = before_bytes.startswith(b"\xef\xbb\xbf")
                    body = before_bytes[3:] if has_bom else before_bytes
                    try:
                        existing_text = body.decode("utf-8")
                    except UnicodeDecodeError as exc:
                        return ToolResult(
                            success=False,
                            error=(
                                f"{rel_path} is not valid UTF-8 (invalid byte at offset "
                                f"{exc.start}); refusing to overwrite it so existing bytes are "
                                f"never substituted. Re-encode the file as UTF-8 first."
                            ),
                        )

                expected = params.get(EXPECTED_HASH_PARAM)
                if expected:
                    actual = hashlib.sha256(resolved.read_bytes()).hexdigest() if existed else ""
                    if actual != expected:
                        return ToolResult(success=False, error=conflict_error(rel_path))

                # An existing file's dominant line ending is the destination's
                # style, and the whole content is written in that style. Probing
                # for the *presence* of CRLF anywhere in the file would restyle a
                # mixed-ending file wholesale — including a file that merely
                # contains a CRLF inside a string literal.
                norm_content = content
                forced = params.get("line_endings")
                if forced in ("lf", "crlf"):
                    term = "\n" if forced == "lf" else "\r\n"
                    norm_content = content.replace("\r\n", "\n").replace("\r", "\n")
                    if term != "\n":
                        norm_content = norm_content.replace("\n", term)
                elif existing_text and "\r\n" in existing_text:
                    crlf = existing_text.count("\r\n")
                    lf_only = existing_text.count("\n") - crlf
                    if crlf > lf_only:
                        norm_content = content.replace("\r\n", "\n").replace("\n", "\r\n")

                if mode == "append" and existing_text:
                    joiner = ""
                    if existing_text and not existing_text.endswith(("\n", "\r")):
                        joiner = "\r\n" if "\r\n" in existing_text else "\n"
                    out_bytes = (norm_content_join(existing_text, joiner, norm_content)).encode("utf-8")
                    if has_bom:
                        out_bytes = b"\xef\xbb\xbf" + out_bytes
                    action = "Appended to"
                else:
                    out_bytes = norm_content.encode("utf-8")
                    if has_bom:
                        out_bytes = b"\xef\xbb\xbf" + out_bytes
                    action = "Updated" if existed else "Created"

                # Serialize the filesystem mutation per workspace (opencode's
                # file-mutation Semaphore) so parallel tool calls cannot race on
                # the same file.
                resolved.parent.mkdir(parents=True, exist_ok=True)
                resolved.write_bytes(out_bytes)

            # Read slices are cached per absolute path, so invalidation is global
            # and unconditional: a write from a delegated, background or resumed
            # session must still invalidate the primary session's cached slice.
            evict_read_cache_path(str(resolved))
            session_id = current_tool_session_id.get() or ""
            if session_id:
                record_write(session_id, rel_path, content)
                JOURNAL.record(
                    session_id,
                    tool="file_write",
                    path=resolved,
                    action="modify" if existed else "create",
                    before=before_bytes,
                    after=out_bytes,
                    extra={"mode": mode},
                )

            written = out_bytes.decode("utf-8", errors="replace")
            return ToolResult(
                success=True,
                output=(
                    f"{action} {rel_path}\n"
                    f"  wrote {len(out_bytes)} byte(s); file is now "
                    f"{_line_count(written)} line(s)"
                ),
                metadata={
                    "path": str(resolved),
                    "bytes": len(out_bytes),
                    "overwritten": existed,
                    "total_lines": _line_count(written),
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=describe(e, action="write", path=rel_path))

