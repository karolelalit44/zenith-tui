from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from server.config.constants import (
    BROAD_PATTERN_THRESHOLD,
    CONCURRENCY_GROUP_READONLY,
    DEFAULT_SEARCH_EXCLUDED_DIRS,
    DEFAULT_SEARCH_EXCLUDED_FILES,
    GLOB_MAX_OUTPUT_CHARS,
    GLOB_MAX_RESULTS,
    PERMISSION_READ,
    TOOL_DOMAIN_WORKSPACE_DISCOVERY,
)

from ..base import BaseTool, ToolResult


def _is_excluded(rel_path: Path, excluded_dirs: set[str], excluded_files: set[str]) -> bool:
    for part in rel_path.parts[:-1]:
        if part in excluded_dirs or part.startswith(".git"):
            return True
    filename = rel_path.name
    if filename in excluded_files:
        return True
    return len(rel_path.parts) == 1 and rel_path.parts[0] in excluded_dirs


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
        "Find files by glob pattern. Automatically excludes node_modules, .git, .venv, etc. "
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
                        "Default exclusions (.git, node_modules, .venv, __pycache__) are applied automatically."
                    ),
                },
                "path": {
                    "type": "string",
                    "description": "Directory to search (defaults to the workspace root)",
                },
                "include_ignored": {
                    "type": "boolean",
                    "description": "If true, include default ignored folders like node_modules, .git, and .venv",
                    "default": False,
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
        include_ignored = bool(params.get("include_ignored", False))

        search_path = (
            Path(requested) if Path(requested).is_absolute() else base / requested
        ).resolve()
        if search_path != base and base not in search_path.parents:
            return ToolResult(success=False, error=f"Search path outside workspace: {search_path}")
        if not search_path.exists():
            return ToolResult(success=False, error=f"Search path not found: {search_path}")

        excluded_dirs = set(DEFAULT_SEARCH_EXCLUDED_DIRS)
        excluded_files = set(DEFAULT_SEARCH_EXCLUDED_FILES)

        try:
            matched_rel_paths: list[Path] = []
            for f in search_path.glob(pattern):
                if not f.is_file():
                    continue
                try:
                    rel = f.relative_to(base)
                except ValueError:
                    rel = f
                if not include_ignored and _is_excluded(rel, excluded_dirs, excluded_files):
                    continue
                matched_rel_paths.append(rel)

            matched_rel_paths.sort()
            total = len(matched_rel_paths)
            if total == 0:
                return ToolResult(
                    success=True,
                    output="No files found matching pattern",
                    metadata={"count": 0, "shown": 0, "truncated": False, "files": []},
                )

            is_broad = pattern in ("*", "**", "**/*", "*/*") and total >= BROAD_PATTERN_THRESHOLD
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
