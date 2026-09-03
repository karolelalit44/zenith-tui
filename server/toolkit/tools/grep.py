from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

from server.config.constants import (
    CONCURRENCY_GROUP_READONLY,
    GREP_MAX_OUTPUT_CHARS,
    GREP_MAX_RESULTS,
    PERMISSION_READ,
    TOOL_DOMAIN_READ,
)
from server.workspace.ignore import ZenithIgnoreMatcher
from server.workspace.search import RipgrepBackend, SearchMatch, _find_rg

from ..base import BaseTool, ToolResult


def _split_top_level(body: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    start = 0
    for i, ch in enumerate(body):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(body[start:i])
            start = i + 1
    parts.append(body[start:])
    return parts


def _split_brace_group(pattern: str) -> tuple[str, list[str], str] | None:
    open_idx = pattern.find("{")
    if open_idx == -1:
        return None
    depth = 0
    for i in range(open_idx, len(pattern)):
        ch = pattern[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                body = pattern[open_idx + 1 : i]
                if not body:
                    return None
                options = _split_top_level(body)
                if len(options) <= 1:
                    return None
                return pattern[:open_idx], options, pattern[i + 1 :]
    return None


def _expand_braces(pattern: str) -> list[str]:
    patterns = [pattern]
    seen: set[str] = set()
    changed = True
    while changed:
        changed = False
        expanded: list[str] = []
        for p in patterns:
            group = _split_brace_group(p)
            if group is None:
                expanded.append(p)
                continue
            changed = True
            prefix, options, suffix = group
            expanded.extend(prefix + opt + suffix for opt in options)
        patterns = expanded

    result: list[str] = []
    for p in patterns:
        if p not in seen:
            seen.add(p)
            result.append(p)
    return result


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
    if root.is_file():
        rel = _safe_rel(root, base)
        if rel is not None and not matcher.is_ignored(rel):
            yield root
        return
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


def _matches_glob(path: Path, pattern: str) -> bool:
    """Return True when *path* matches a shell glob pattern."""
    for candidate in _expand_braces(pattern):
        if path.match(candidate):
            return True
        if len(path.parts) == 1 and candidate.startswith("**/") and path.match(candidate[3:]):
            return True
    return False


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

        try:
            backend = RipgrepBackend(
                ignore_files=[str(base / ".zenithignore")], max_results=GREP_MAX_RESULTS * 2
            )
            if _find_rg() is not None:
                backend_matches = await backend.grep(pattern, str(search_path), include=include)
            else:
                matcher = ZenithIgnoreMatcher(workspace_root)
                matcher.refresh()
                backend_matches = []
                include_patterns = _expand_braces(include) if include else []
                max_matches = backend.max_results
                for file_path in sorted(
                    _iter_source_files(search_path, base, matcher),
                    key=lambda candidate: str(candidate),
                ):
                    rel_path = _safe_rel(file_path, base)
                    if rel_path is None:
                        continue
                    if include_patterns and not any(
                        _matches_glob(rel_path, candidate) for candidate in include_patterns
                    ):
                        continue
                    try:
                        content = file_path.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        continue
                    for line_number, line in enumerate(content.splitlines(), start=1):
                        if regex.search(line):
                            backend_matches.append(
                                SearchMatch(path=str(file_path), line_number=line_number, text=line)
                            )
                            if len(backend_matches) >= max_matches:
                                break
                    if len(backend_matches) >= max_matches:
                        break
            matches = []
            for match in backend_matches:
                file_path = Path(match.path)
                try:
                    rel_path = file_path.resolve().relative_to(base)
                except ValueError:
                    rel_path = file_path
                line_preview = match.text.strip()
                if len(line_preview) > 300:
                    line_preview = line_preview[:300] + "..."
                matches.append(f"{rel_path}:{match.line_number}: {line_preview}")

            total_matches = len(matches)
            files_searched = len({match.path for match in backend_matches})
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
            truncated = total_matches > GREP_MAX_RESULTS

            output_lines: list[str] = []
            if truncated and files_searched > 20:
                output_lines.append(_build_dir_hints(matches))
                # Add actionable narrowing instruction
                top_dirs = sorted(
                    {
                        m.split(":", 1)[0].split("/")[0] + "/"
                        for m in matches
                        if "/" in m.split(":", 1)[0]
                    },
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
