from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from server.config.constants import (
    BROAD_PATTERN_THRESHOLD,
    CONCURRENCY_GROUP_READONLY,
    GLOB_MAX_OUTPUT_CHARS,
    GLOB_MAX_RESULTS,
    PERMISSION_READ,
    TOOL_DOMAIN_WORKSPACE_DISCOVERY,
)
from server.workspace.ignore import get_matcher
from server.workspace.search import RipgrepBackend, _find_rg

from ..base import BaseTool, ToolResult
from .grep import _iter_source_files, _matches_glob, _safe_rel


def _pattern_is_unscoped(pattern: str) -> bool:
    """True when the pattern is not pinned to a named top-level directory.

    ``**/*.py``, ``*`` and ``**/*`` sweep the whole workspace; ``tui/**/*`` is
    scoped. Unscoped patterns that over-match get a directory summary so the
    structure is visible even when the file list truncates (P4.2).
    """
    first = pattern.split("/", 1)[0]
    return first in ("*", "**")


def _build_directory_summary(file_rel_paths: list[Path]) -> str:
    dir_counts: Counter[str] = Counter()
    root_files: list[str] = []
    for p in file_rel_paths:
        if len(p.parts) > 1:
            top_dir = p.parts[0] + "/"
            dir_counts[top_dir] += 1
        else:
            root_files.append(p.name)
    lines: list[str] = [
        f"Directory structure overview ({len(file_rel_paths)} files across {len(dir_counts)} directories):"
    ]
    for d, count in sorted(dir_counts.items()):
        lines.append(f"  📁 {d} ({count} files)")
    if root_files:
        lines.append(
            f"  📄 Root files ({len(root_files)} files): {', '.join(sorted(root_files)[:8])}"
        )
        if len(root_files) > 8:
            lines[-1] += f", ... (+{len(root_files) - 8} more)"
    lines.append("")
    return "\n".join(lines)


class GlobTool(BaseTool):
    name = "glob"
    description = (
        "Find files by glob pattern. Paths matched by .zenithignore are skipped entirely. "
        "Scope pattern to a subfolder (e.g. 'server/**/*.py') for faster and focused results."
    )
    requires_mode = None
    capability_id = "workspace_discovery"
    read_only = True
    concurrency_group = CONCURRENCY_GROUP_READONLY
    permission_scope = PERMISSION_READ
    domains = (TOOL_DOMAIN_WORKSPACE_DISCOVERY,)
    search_terms = (
        "list files",
        "glob",
        "find",
        "discover",
        "workspace",
        "file search",
    )

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": (
                        "Glob pattern, preferably scoped to a subdirectory (e.g. 'server/**/*.py'). "
                        "Brace expansion is supported (e.g. 'src/**/*.{ts,tsx}'). "
                        "Paths matched by .zenithignore are applied automatically."
                    ),
                },
                "path": {
                    "type": "string",
                    "description": "Directory to search (defaults to the workspace root)",
                },
            },
            "required": ["pattern"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        pattern = params.get("pattern", "**/*")
        if pattern.strip() == "**":
            pattern = "**/*"
        base = Path(workspace_root).resolve()
        requested = params.get("path") or ""

        search_path = (
            Path(requested) if Path(requested).is_absolute() else base / requested
        ).resolve()
        if search_path != base and base not in search_path.parents:
            return ToolResult(success=False, error=f"Search path outside workspace: {search_path}")
        if not search_path.exists():
            return ToolResult(success=False, error=f"Search path not found: {search_path}")

        try:
            backend = RipgrepBackend(ignore_files=[str(base / ".zenithignore")])
            matcher = get_matcher(workspace_root)
            matcher.refresh()
            if _find_rg() is not None:
                files = await backend.glob(pattern, str(search_path))
            else:
                files = []
                max_results = backend.max_results
                for file_path in sorted(
                    _iter_source_files(search_path, base, matcher),
                    key=lambda candidate: str(candidate),
                ):
                    relative_path = _safe_rel(file_path, base)
                    if relative_path is None:
                        continue
                    if _matches_glob(relative_path, pattern):
                        files.append(str(file_path))
                        if len(files) >= max_results:
                            break
            matched_rel_paths = []
            for file_name in files:
                file_path = Path(file_name)
                try:
                    relative_path = file_path.resolve().relative_to(base)
                except ValueError:
                    relative_path = file_path
                if not matcher.is_ignored(relative_path):
                    matched_rel_paths.append(relative_path)

            matched_rel_paths = sorted(set(matched_rel_paths))
            total = len(matched_rel_paths)
            if total == 0:
                return ToolResult(
                    success=True,
                    output="No files found matching pattern",
                    metadata={"count": 0, "shown": 0, "truncated": False, "files": []},
                )

            is_broad = total >= BROAD_PATTERN_THRESHOLD and _pattern_is_unscoped(pattern)
            summary_prefix = _build_directory_summary(matched_rel_paths) if is_broad else ""

            truncated = total > GLOB_MAX_RESULTS
            shown_paths = matched_rel_paths[:GLOB_MAX_RESULTS]
            file_strings = [str(p) for p in shown_paths]

            output_lines: list[str] = []
            if summary_prefix:
                output_lines.append(summary_prefix)
                output_lines.append("Files:")
            output_lines.extend(file_strings)

            if truncated:
                output_lines.append(
                    f"\n[Showing {GLOB_MAX_RESULTS} of {total} matches. "
                    f"Narrow your search with a subpath or file filter.]"
                )

            output = "\n".join(output_lines)
            if len(output) > GLOB_MAX_OUTPUT_CHARS:
                output = (
                    output[:GLOB_MAX_OUTPUT_CHARS]
                    + "\n[... output truncated; narrow the glob pattern or specify a subpath]"
                )

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "count": total,
                    "shown": len(file_strings),
                    "truncated": truncated or len(output) >= GLOB_MAX_OUTPUT_CHARS,
                    "files": file_strings,
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
