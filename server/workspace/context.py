from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)
_CONTEXT_FILE_NAMES = [
    "zenith.md",
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "CRUSH.md",
    ".cursorrules",
    ".clinerules",
    ".github/copilot-instructions.md",
]
_MAX_PARENT_DEPTH = 3


@dataclass(frozen=True)
class ContextFile:
    path: str
    content: str
    scope: str


def load_context_files(workspace_root: str) -> list[ContextFile]:
    root = Path(workspace_root).resolve()
    results: list[ContextFile] = []
    seen: set[Path] = set()
    for name in _CONTEXT_FILE_NAMES:
        candidate = root / name
        if candidate.is_file() and candidate.resolve() not in seen:
            content = _read_file(candidate)
            if content:
                results.append(ContextFile(path=str(candidate), content=content, scope="project"))
                seen.add(candidate.resolve())
    current = root.parent
    for _ in range(_MAX_PARENT_DEPTH):
        if current == current.parent:
            break
        for name in _CONTEXT_FILE_NAMES:
            candidate = current / name
            if candidate.is_file() and candidate.resolve() not in seen:
                content = _read_file(candidate)
                if content:
                    results.append(
                        ContextFile(path=str(candidate), content=content, scope="parent")
                    )
                    seen.add(candidate.resolve())
        current = current.parent
    if results:
        logger.info("Loaded %d context file(s): %s", len(results), [f.path for f in results])
    return results


def _read_file(path: Path, max_bytes: int = 64000) -> str | None:
    try:
        stat = path.stat()
        if stat.st_size > max_bytes:
            logger.warning("Context file too large (%d bytes), skipping: %s", stat.st_size, path)
            return None
        content = path.read_text(encoding="utf-8", errors="replace")
        lines = content.split("\n")
        if len(lines) > 500:
            content = "\n".join(lines[:500]) + "\n\n... (truncated at 500 lines)"
        return content.strip() if content.strip() else None
    except (OSError, PermissionError) as e:
        logger.warning("Failed to read context file %s: %s", path, e)
        return None


def format_context_files(files: list[ContextFile]) -> str:
    if not files:
        return ""
    parts: list[str] = []
    for f in files:
        parts.append(f'<file path="{f.path}" scope="{f.scope}">\n{f.content}\n</file>')
    return "\n".join(parts)
