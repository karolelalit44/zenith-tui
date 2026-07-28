"""Context files — loads project-specific instructions from AGENTS.md, CLAUDE.md, etc."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# File names to search for, in priority order (first match wins per directory)
_CONTEXT_FILE_NAMES = [
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "CRUSH.md",
    ".cursorrules",
    ".clinerules",
    ".github/copilot-instructions.md",
]

# Directories to search (workspace root, then up to 3 parent dirs)
_MAX_PARENT_DEPTH = 3


@dataclass(frozen=True)
class ContextFile:
    """A loaded context file with its path and content."""

    path: str
    content: str
    scope: str  # "project" for workspace root, "parent" for parent dirs


def load_context_files(workspace_root: str) -> list[ContextFile]:
    """Load project context files from the workspace root and parent directories.

    Searches for AGENTS.md, CLAUDE.md, etc. in:
    1. The workspace root (scope="project")
    2. Up to 3 parent directories (scope="parent")

    Files in the workspace root take precedence. Deduplication is by
    resolved path so the same file isn't loaded twice.
    """
    root = Path(workspace_root).resolve()
    results: list[ContextFile] = []
    seen: set[Path] = set()

    # 1. Search workspace root
    for name in _CONTEXT_FILE_NAMES:
        candidate = root / name
        if candidate.is_file() and candidate.resolve() not in seen:
            content = _read_file(candidate)
            if content:
                results.append(ContextFile(
                    path=str(candidate),
                    content=content,
                    scope="project",
                ))
                seen.add(candidate.resolve())

    # 2. Search parent directories (up to MAX_PARENT_DEPTH levels)
    current = root.parent
    for _ in range(_MAX_PARENT_DEPTH):
        if current == current.parent:
            break
        for name in _CONTEXT_FILE_NAMES:
            candidate = current / name
            if candidate.is_file() and candidate.resolve() not in seen:
                content = _read_file(candidate)
                if content:
                    results.append(ContextFile(
                        path=str(candidate),
                        content=content,
                        scope="parent",
                    ))
                    seen.add(candidate.resolve())
        current = current.parent

    if results:
        logger.info(
            "Loaded %d context file(s): %s",
            len(results),
            [f.path for f in results],
        )

    return results


def _read_file(path: Path, max_bytes: int = 64_000) -> str | None:
    """Read a file safely, returning None on error or if too large."""
    try:
        stat = path.stat()
        if stat.st_size > max_bytes:
            logger.warning("Context file too large (%d bytes), skipping: %s", stat.st_size, path)
            return None
        content = path.read_text(encoding="utf-8", errors="replace")
        # Strip very long files to avoid consuming excessive prompt tokens
        lines = content.split("\n")
        if len(lines) > 500:
            content = "\n".join(lines[:500]) + "\n\n... (truncated at 500 lines)"
        return content.strip() if content.strip() else None
    except (OSError, PermissionError) as e:
        logger.warning("Failed to read context file %s: %s", path, e)
        return None


def format_context_files(files: list[ContextFile]) -> str:
    """Format context files for injection into the system prompt."""
    if not files:
        return ""

    parts: list[str] = []
    for f in files:
        parts.append(f'<file path="{f.path}" scope="{f.scope}">\n{f.content}\n</file>')
    return "\n".join(parts)
