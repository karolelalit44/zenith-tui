from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from server.config.constants import (
    CONCURRENCY_GROUP_READONLY,
    DEFAULT_SEARCH_EXCLUDED_DIRS,
    DEFAULT_SEARCH_EXCLUDED_FILES,
    GREP_MAX_FILES,
    GREP_MAX_OUTPUT_CHARS,
    GREP_MAX_RESULTS,
    PERMISSION_READ,
    TOOL_DOMAIN_READ,
)

from ..base import BaseTool, ToolResult
from ..brace_expand import expand_braces


def _is_excluded(rel_path: Path, excluded_dirs: set[str], excluded_files: set[str]) -> bool:
    for part in rel_path.parts[:-1]:
        if part in excluded_dirs or part.startswith(".git"):
            return True
    filename = rel_path.name
    if filename in excluded_files:
        return True
    return len(rel_path.parts) == 1 and rel_path.parts[0] in excluded_dirs


def _iter_source_files(
    root: Path, excluded_dirs: set[str], excluded_files: set[str], include_ignored: bool
):
    """Yield files under root, pruning excluded directories before descending.

    Avoids the expensive `Path.glob("**/*")` walk that descends into
    node_modules/.git/.venv before filtering them out.
    """
    stack: list[Path] = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        dirs: list[str] = []
        for entry in entries:
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if is_dir:
                name = entry.name
                if include_ignored or (name not in excluded_dirs and not name.startswith(".git")):
                    dirs.append(entry.path)
                continue
            if entry.name in excluded_files:
                continue
            yield Path(entry.path)
        stack.extend(reversed(dirs))


class GrepTool(BaseTool):
    name = "grep"
    description = (
        "Search file contents by regex pattern. Automatically skips non-source folders (.git, node_modules, .venv, etc.). "
        "Use 'path' and 'include' filters to narrow search scope."
    )
    requires_mode = None
    capability_id = "content_search"
    read_only = True
    concurrency_group = CONCURRENCY_GROUP_READONLY
    permission_scope = PERMISSION_READ
    domains = (TOOL_DOMAIN_READ,)
    search_terms = (
        "grep",
        "search",
        "regex",
        "pattern",
        "find in files",
        "occurrences",
    )

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for"},
                "path": {
                    "type": "string",
                    "description": "Search directory or specific file (defaults to workspace root)",
                },
                "include": {
                    "type": "string",
                    "description": "File pattern filter (e.g. '*.py', '*.ts', 'src/**', '*.{ts,tsx}')",
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
        pattern = params.get("pattern", "")
        if not pattern:
            return ToolResult(success=False, error="Empty search pattern")

        base = Path(workspace_root).resolve()
        requested_path = params.get("path", ".")
        include = params.get("include", None)
        include_ignored = bool(params.get("include_ignored", False))

        search_path = (
            Path(requested_path) if Path(requested_path).is_absolute() else base / requested_path
        ).resolve()

        if search_path != base and base not in search_path.parents:
            return ToolResult(success=False, error=f"Search path outside workspace: {search_path}")
        if not search_path.exists():
            return ToolResult(success=False, error=f"Search path not found: {search_path}")

        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return ToolResult(success=False, error=f"Invalid regex: {e}")

        excluded_dirs = set(DEFAULT_SEARCH_EXCLUDED_DIRS)
        excluded_files = set(DEFAULT_SEARCH_EXCLUDED_FILES)

        try:
            matches: list[str] = []
            files_to_search: list[Path] = []

            if search_path.is_file():
                rel = search_path.relative_to(base) if search_path != base else search_path
                if include_ignored or not _is_excluded(rel, excluded_dirs, excluded_files):
                    files_to_search = [search_path]
            else:
                patterns = expand_braces(include) if include else ["**/*"]
                for glob_pattern in patterns:
                    if glob_pattern in ("**", "**/*"):
                        for f in _iter_source_files(
                            search_path, excluded_dirs, excluded_files, include_ignored
                        ):
                            files_to_search.append(f)
                            if len(files_to_search) >= GREP_MAX_FILES:
                                break
                    else:
                        for f in search_path.glob(glob_pattern):
                            if not f.is_file():
                                continue
                            try:
                                rel = f.relative_to(base)
                            except ValueError:
                                rel = f
                            if not include_ignored and _is_excluded(rel, excluded_dirs, excluded_files):
                                continue
                            files_to_search.append(f)
                            if len(files_to_search) >= GREP_MAX_FILES:
                                break
                    if len(files_to_search) >= GREP_MAX_FILES:
                        break

            files_searched = 0
            hit_limit = False

            for file_path in files_to_search:
                files_searched += 1
                try:
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                    try:
                        rel_str = str(file_path.relative_to(base))
                    except ValueError:
                        rel_str = str(file_path)

                    for i, line in enumerate(content.split("\n"), 1):
                        if regex.search(line):
                            line_preview = line.strip()
                            if len(line_preview) > 300:
                                line_preview = line_preview[:300] + "..."
                            matches.append(f"{rel_str}:{i}: {line_preview}")
                            if len(matches) >= GREP_MAX_RESULTS * 2:
                                hit_limit = True
                                break
                except Exception:
                    continue
                if hit_limit:
                    break

            total_matches = len(matches)
            if total_matches == 0:
                return ToolResult(
                    success=True,
                    output="No matches found",
                    metadata={
                        "count": 0,
                        "shown": 0,
                        "truncated": False,
                        "files_searched": files_searched,
                    },
                )

            shown_matches = matches[:GREP_MAX_RESULTS]
            truncated = total_matches > GREP_MAX_RESULTS or len(files_to_search) >= GREP_MAX_FILES

            output_lines = list(shown_matches)
            if truncated:
                output_lines.append(
                    f"\n[Showing {len(shown_matches)} of {total_matches}+ matches across {files_searched} files. "
                    f"Narrow your regex pattern, specify a file filter with 'include', or limit 'path'.]"
                )

            output = "\n".join(output_lines)
            if len(output) > GREP_MAX_OUTPUT_CHARS:
                output = (
                    output[:GREP_MAX_OUTPUT_CHARS]
                    + "\n[... output truncated; narrow the grep pattern or specify a path]"
                )

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "count": total_matches,
                    "shown": len(shown_matches),
                    "truncated": truncated or len(output) >= GREP_MAX_OUTPUT_CHARS,
                    "files_searched": files_searched,
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
