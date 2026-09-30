from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from server.agents.session_workspace import evict_read_cache_path
from server.config.constants import (
    BUILD_MODE,
    CONCURRENCY_GROUP_WORKSPACE_MUTATION,
    RISK_MEDIUM,
    TOOL_DOMAIN_EDIT,
)
from server.toolkit.registry import current_tool_session_id
from server.workspace.ignore import blocked_as_missing, get_matcher, mutation_refusal

from ..base import BaseTool, ToolResult
from ..errors import describe
from ..journal import JOURNAL
from ..path_validator import not_found_error, path_rejection_error, validate_path
from .file_mutation_queue import FILE_MUTATION_QUEUE


MAX_DELETE_TREE_ENTRIES = 50_000


def _count_entries(root: Path, cap: int = MAX_DELETE_TREE_ENTRIES) -> tuple[int, bool]:
    """``(entries, hit_cap)`` for a tree.

    The count is bounded and the bound is reported. Walking an unbounded tree
    to produce a summary number means a ``node_modules``-sized delete holds the
    workspace mutation lock for the entire traversal, blocking every other
    writer for as long as the summary takes. The cap keeps the lock hold time
    proportional to the delete itself rather than to a cosmetic number.
    """
    count = 0
    for _ in root.rglob("*"):
        count += 1
        if count >= cap:
            return count, True
    return count, False


def _journal_delete(resolved: Path, rel_path: str, before: bytes | None) -> None:
    session_id = current_tool_session_id.get() or ""
    if not session_id:
        return
    JOURNAL.record(
        session_id,
        tool="file_delete",
        path=resolved,
        action="delete",
        before=before,
        after=None,
    )


def _journal_dir_delete(resolved: Path, rel_path: str) -> None:
    """Record a recursive delete so the journal can report it.

    The tree's contents are not retained: a deleted ``node_modules`` would put
    hundreds of megabytes in memory to make an undo possible, and a directory
    tree is not something this agent recreated. Reverting removes the entry and
    reports that the tree's contents were not retained, which is honest.
    """
    session_id = current_tool_session_id.get() or ""
    if not session_id:
        return
    JOURNAL.record(
        session_id,
        tool="file_delete",
        path=resolved,
        action="delete",
        before=None,
        after=None,
        extra={"directory": True},
    )


class FileDeleteTool(BaseTool):
    name = "file_delete"
    description = "Delete a file or a directory tree (recursively)."
    requires_mode = BUILD_MODE
    capability_id = "file_delete"
    read_only = False
    concurrency_group = CONCURRENCY_GROUP_WORKSPACE_MUTATION
    domains = (TOOL_DOMAIN_EDIT,)
    search_terms = (
        "delete",
        "remove",
        "unlink",
        "clean up",
    )
    risk_level = RISK_MEDIUM

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File or directory path to delete"}
            },
            "required": ["path"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        rel_path = params.get("path", "")
        resolved = validate_path(rel_path, workspace_root)
        if resolved is None:
            return ToolResult(success=False, error=path_rejection_error(rel_path, workspace_root) or "Path rejected.")
        if blocked_as_missing(get_matcher(workspace_root), rel_path):
            return ToolResult(success=False, error=mutation_refusal(rel_path))
        if not resolved.exists():
            return ToolResult(
                success=False, error=not_found_error(rel_path, workspace_root)
            )

        root = Path(workspace_root).resolve()
        if resolved == root:
            return ToolResult(
                success=False,
                error=(
                    "Refusing to delete the workspace root. That would remove every file "
                    "in the project. Delete specific paths instead, or ask the user to "
                    "remove the directory themselves if that is genuinely intended."
                ),
            )
        if resolved.is_symlink() or (
            resolved.is_dir() and root not in resolved.parents
        ):
            return ToolResult(
                success=False,
                error=(
                    f"Refusing to delete '{rel_path}' recursively. It is a symlink or "
                    f"resolves outside the workspace, so a recursive delete would "
                    f"destroy a tree this session does not own. Delete the link itself, "
                    f"or target the contents explicitly."
                ),
            )

        try:
            # Serialize the destructive mutation so a concurrent tool cannot
            # recreate a path mid-delete (opencode's file-mutation Semaphore).
            async with FILE_MUTATION_QUEUE.mutation(workspace_root):
                if resolved.is_dir():
                    removed, hit_cap = _count_entries(resolved)
                    shutil.rmtree(resolved)
                    evict_read_cache_path(str(resolved))
                    _journal_dir_delete(resolved, rel_path)
                    note = "+" if hit_cap else ""
                    return ToolResult(
                        success=True,
                        output=(
                            f"Deleted directory '{rel_path}' ({removed}{note} entries); "
                            f"the directory no longer exists"
                        ),
                        metadata={"path": str(resolved), "directory": True, "entries": removed},
                    )
                content = ""
                before_bytes: bytes | None = None
                try:
                    before_bytes = resolved.read_bytes()
                    content = before_bytes.decode("utf-8", errors="replace")
                except Exception:
                    pass
                resolved.unlink()
                evict_read_cache_path(str(resolved))
                _journal_delete(resolved, rel_path, before_bytes)
                return ToolResult(
                    success=True,
                    output=(
                        f"Deleted {rel_path}\n"
                        f"  {len(content.encode('utf-8', errors='replace'))} byte(s) removed; "
                        f"the path no longer exists"
                    ),
                    metadata={"path": str(resolved), "content": content},
                )
        except Exception as e:
            return ToolResult(success=False, error=describe(e, action="delete", path=rel_path))

