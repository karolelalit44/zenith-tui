"""``file_move`` and ``file_copy`` — first-class path relocation.

A rename reachable only through ``apply_patch`` is a rename nobody uses. It
required a ``*** Update File`` hunk containing a context line that changed
nothing, which is undocumented, and it had no guard against a destination that
already existed — so a "rename" onto an occupied path silently destroyed the
file that was there. Both problems are why a model reaching for ``mv`` was not
being unreasonable, and the shell was the only honest option available.

These tools make the operation explicit, refuse to clobber, carry the same
optimistic-concurrency guard as the other mutators, and report a receipt that
names both paths.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from server.config.constants import (
    CONCURRENCY_GROUP_WORKSPACE_MUTATION,
    EXPECTED_HASH_PARAM,
    RISK_MEDIUM,
    TOOL_DOMAIN_EDIT,
)
from server.toolkit.registry import current_tool_session_id
from server.workspace.ignore import blocked_as_missing, get_matcher, mutation_refusal

from ..base import BaseTool, ToolResult
from ..errors import conflict_error, describe
from ..journal import JOURNAL
from ..path_validator import not_found_error, validate_path
from .file_mutation_queue import FILE_MUTATION_QUEUE
from .file_stat import _content_hash


def _resolve_pair(
    params: dict[str, Any], workspace_root: str
) -> tuple[str, str, Path, Path, str | None]:
    """Validate the source and destination. Returns an error string on refusal."""
    source = params.get("path") or params.get("from") or params.get("source") or ""
    dest = params.get("to") or params.get("dest") or params.get("destination") or ""
    if not source:
        return "", "", Path(), Path(), "Missing source path parameter ('path')"
    if not dest:
        return "", "", Path(), Path(), "Missing destination path parameter ('to')"
    src_resolved = validate_path(source, workspace_root)
    if src_resolved is None:
        return "", "", Path(), Path(), f"Path escapes workspace boundary: {source}"
    dst_resolved = validate_path(dest, workspace_root)
    if dst_resolved is None:
        return "", "", Path(), Path(), f"Destination escapes workspace boundary: {dest}"

    matcher = get_matcher(workspace_root)
    if blocked_as_missing(matcher, source) or blocked_as_missing(matcher, dest):
        offending = source if blocked_as_missing(matcher, source) else dest
        return "", "", Path(), Path(), mutation_refusal(offending)
    return source, dest, src_resolved, dst_resolved, None


class _RelocationTool(BaseTool):
    read_only = False
    concurrency_group = CONCURRENCY_GROUP_WORKSPACE_MUTATION
    risk_level = RISK_MEDIUM
    domains = (TOOL_DOMAIN_EDIT,)
    _verb = "Moved"
    _gerund = "move"

    def _apply(self, source: Path, dest: Path) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        source, dest, src_resolved, dst_resolved, error = _resolve_pair(params, workspace_root)
        if error:
            return ToolResult(success=False, error=error)
        if not src_resolved.exists():
            return ToolResult(
                success=False, error=not_found_error(source, workspace_root)
            )
        if src_resolved.is_dir():
            return ToolResult(
                success=False,
                error=(
                    f"{source}/ is a directory. Use file_delete to remove it, or "
                    f"relocate its contents individually."
                ),
            )
        if src_resolved == dst_resolved:
            return ToolResult(
                success=True,
                output=f"{self._verb} {source} -> {dest} (source and destination are the same path)",
                metadata={"path": str(src_resolved), "to": dest, "noop": True},
            )
        if dst_resolved.exists():
            # Refuse rather than destroy. Codex does the same for a patch move;
            # silently replacing a file the model never looked at is how work
            # disappears without anyone noticing.
            return ToolResult(
                success=False,
                error=(
                    f"Destination already exists: {dest}. The {self._gerund} was not "
                    f"performed and nothing was overwritten. Delete it first, choose a "
                    f"different destination, or use the tool that replaces content "
                    f"deliberately."
                ),
            )

        session_id = current_tool_session_id.get() or ""
        expected = params.get(EXPECTED_HASH_PARAM)
        after_bytes = src_resolved.read_bytes()
        try:
            async with FILE_MUTATION_QUEUE.mutation(workspace_root):
                if expected:
                    actual = _content_hash(src_resolved)
                    if actual != expected:
                        return ToolResult(
                            success=False, error=conflict_error(source)
                        )
                dst_resolved.parent.mkdir(parents=True, exist_ok=True)
                self._apply(src_resolved, dst_resolved)
        except Exception as e:
            return ToolResult(
                success=False,
                error=describe(e, action=f"{self._gerund} '{source}' to '{dest}'"),
            )

        size = dst_resolved.stat().st_size if dst_resolved.exists() else 0
        aftermath = (
            "source no longer exists"
            if self.name == "file_move"
            else "source is unchanged"
        )
        if session_id:
            # A relocation changes two paths, so both are journalled: the
            # destination is written and the source removed. Recording only one
            # would make revert leave a stray file or restore a deleted one.
            if self.name == "file_move":
                JOURNAL.record(
                    session_id,
                    tool="file_move",
                    path=dst_resolved,
                    action="create",
                    before=None,
                    after=after_bytes,
                    extra={"moved_from": source},
                )
                JOURNAL.record(
                    session_id,
                    tool="file_move",
                    path=src_resolved,
                    action="delete",
                    before=after_bytes,
                    after=None,
                    extra={"moved_to": dest},
                )
            else:
                JOURNAL.record(
                    session_id,
                    tool="file_copy",
                    path=dst_resolved,
                    action="create",
                    before=None,
                    after=after_bytes,
                    extra={"copied_from": source},
                )
        return ToolResult(
            success=True,
            output=f"{self._verb} {source} -> {dest}\n  {size} byte(s); {aftermath}",
            metadata={"path": str(dst_resolved), "to": dest, "bytes": size},
        )


class FileMoveTool(_RelocationTool):
    name = "file_move"
    description = (
        "Move or rename a file. Creates any missing parent directories. Refuses "
        "to overwrite an existing destination, so a rename can never silently "
        "destroy a file. Use this instead of a shell mv."
    )
    capability_id = "file_relocate"

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Current file path"},
                "to": {
                    "type": "string",
                    "description": "Destination path, relative to the workspace root",
                },
                EXPECTED_HASH_PARAM: {
                    "type": "string",
                    "description": (
                        "Optional SHA-256 of the source as last seen. The move is "
                        "refused if the file changed since, instead of relocating "
                        "content nobody reviewed."
                    ),
                },
            },
            "required": ["path", "to"],
        }

    def _apply(self, source: Path, dest: Path) -> None:
        shutil.move(str(source), str(dest))


class FileCopyTool(_RelocationTool):
    name = "file_copy"
    description = (
        "Copy a file to a new path, creating any missing parent directories. "
        "Refuses to overwrite an existing destination. Use this instead of a "
        "shell cp."
    )
    capability_id = "file_relocate"
    _verb = "Copied"
    _gerund = "copy"

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File to copy"},
                "to": {
                    "type": "string",
                    "description": "Destination path, relative to the workspace root",
                },
            },
            "required": ["path", "to"],
        }

    def _apply(self, source: Path, dest: Path) -> None:
        shutil.copy2(str(source), str(dest))
