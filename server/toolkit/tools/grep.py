from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

from server.config.constants import (
    CONCURRENCY_GROUP_READONLY,
    GREP_MAX_FILES,
    GREP_MAX_OUTPUT_CHARS,
    GREP_MAX_RESULTS,
    PERMISSION_READ,
    TOOL_DOMAIN_READ,
)
from server.workspace.ignore import ZenithIgnoreMatcher, get_matcher

from ..base import BaseTool, ToolResult
from ..brace_expand import expand_braces


def _safe_rel(path: Path, base: Path) -> Path | None:
    try:
        return path.relative_to(base)
    except ValueError:
        return None


def _build_dir_hints(matches: list[str], top_n: int = 8) -> str:
    """Summarise which subdirectories contain the most matches.

    Gives the agent a concrete scoping hint when a broad grep returns too many
    results, so it can re-run with ``path`` narrowed to the relevant subdir.
    """
    dir_counts: Counter[str] = Counter()
    for m in matches:
        # match format: "relative/path:line: content"
        parts = m.split(":", 1)
        if parts:
            p = Path(parts[0])
            if len(p.parts) > 1:
                dir_counts[p.parts[0] + "/"] += 1
            else:
                dir_counts["."] += 1
    if not dir_counts:
        return ""
    lines = ["Matches by directory:"]
    for d, count in dir_counts.most_common(top_n):
        lines.append(f"  {d} ({count})")
    total_dirs = len(dir_counts)
    if total_dirs > top_n:
        lines.append(f"  ... and {total_dirs - top_n} more directories")
    lines.append("")
    return "\n".join(lines)


def _iter_source_files(root: Path, base: Path, matcher: ZenithIgnoreMatcher):
    """Yield non-ignored files under root, pruning ignored directories before
    descending so large vendored trees are never walked at all."""
    stack: list[Path] = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        dirs: list[Path] = []
        for entry in entries:
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                continue
            rel = _safe_rel(Path(entry.path), base)
            if is_dir:
                if rel is None or not matcher.is_ignored_dir(rel):
                    dirs.append(Path(entry.path))
                continue
            if rel is not None and matcher.is_ignored(rel):
                continue
            yield Path(entry.path)
        stack.extend(reversed(dirs))


class GrepTool(BaseTool):
    name = "grep"
    description = (
        "Search file contents by regex pattern. Paths matched by .zenithignore are skipped. "
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

        matcher = get_matcher(workspace_root)
        matcher.refresh()
        ignored_file = search_path.is_file() and matcher.is_ignored(
            _safe_rel(search_path, base) or search_path
        )

        try:
            matches: list[str] = []
            files_to_search: list[Path] = []

            if search_path.is_file():
                if not ignored_file:
                    files_to_search = [search_path]
            else:
                raw_patterns = expand_braces(include) if include else ["**/*"]
                patterns = []
                for p in raw_patterns:
                    if "**/" not in p and not p.startswith("**"):
                        patterns.append("**/" + p)
                    else:
                        patterns.append(p)
                for glob_pattern in patterns:
                    if glob_pattern in ("**", "**/*"):
                        for f in _iter_source_files(search_path, base, matcher):
                            files_to_search.append(f)
                            if len(files_to_search) >= GREP_MAX_FILES:
                                break
                    else:
                        for f in search_path.glob(glob_pattern):
                            if not f.is_file():
                                continue
                            rel = _safe_rel(f, base)
                            if rel is None or matcher.is_ignored(rel):
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
            truncated = total_matches > GREP_MAX_RESULTS or files_searched >= GREP_MAX_FILES

            output_lines: list[str] = []
            if truncated and files_searched > 20:
                output_lines.append(_build_dir_hints(matches))
                # Add actionable narrowing instruction
                top_dirs = sorted(
                    set(
                        m.split(":", 1)[0].split("/")[0] + "/"
                        for m in matches
                        if "/" in m.split(":", 1)[0]
                    ),
                    key=lambda d: sum(1 for m in matches if m.startswith(d)),
                    reverse=True,
                )
                if top_dirs:
                    output_lines.append(
                        f'Re-run with path="{top_dirs[0].rstrip("/")}" to focus on the '
                        f"most relevant directory, or narrow the include filter."
                    )
            output_lines.extend(shown_matches)
            if truncated:
                output_lines.append(
                    f"\n[Showing {len(shown_matches)} of {total_matches}+ matches across {files_searched} files. "
                    f"Re-run with 'path' narrowed to the directory above, or add an 'include' filter.]"
                )

            output = "\n".join(output_lines)
            if len(output) > GREP_MAX_OUTPUT_CHARS:
                output = (
                    output[:GREP_MAX_OUTPUT_CHARS]
                    + "\n[... output truncated; narrow 'path' to a specific subdirectory or add 'include' filter]"
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
