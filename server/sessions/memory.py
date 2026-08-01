"""Durable memory store (HP-7) — `memory/*.md` facts persisted per workspace.

When the agent loop summarises a conversation, the durable facts extracted
during compaction are appended to `memory/<session>.md`. On later sessions in
the same workspace, the stored facts are loaded back into the model context so
knowledge survives across sessions.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

MEMORY_DIR = "memory"
MAX_FILE_CHARS = 8000
NO_CONTEXT_SENTINEL = "No prior context available."


def _sanitize(name: str) -> str:
    return re.sub(r"[^\w-]", "_", name)


class MemoryStore:
    """File-backed durable memory under ``<workspace>/memory/*.md``."""

    def __init__(self, workspace_root: str, max_chars: int = MAX_FILE_CHARS) -> None:
        self.root = Path(workspace_root)
        self.dir = self.root / MEMORY_DIR
        self.max_chars = max_chars

    def _ensure_dir(self) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        return self.dir

    def path_for(self, session_id: str) -> Path:
        """Resolve the memory file path for a session (creates the dir)."""
        return self._ensure_dir() / f"{_sanitize(session_id)}.md"

    def append(self, session_id: str, facts: str) -> Path:
        """Append a durable-facts block for a session. Returns the file path."""
        if not facts or not facts.strip():
            return self.path_for(session_id)
        path = self.path_for(session_id)
        block = (
            f"## Durable facts — {datetime.now().isoformat(timespec='seconds')}\n"
            f"{facts.strip()}\n"
        )
        existing = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        combined = (existing + "\n" + block).strip() + "\n"
        if len(combined) > self.max_chars:
            combined = combined[-self.max_chars:].lstrip("\n")
            combined = "# Zenith memory (rolled over)\n" + combined
        path.write_text(combined, encoding="utf-8")
        logger.info("Memory updated for session %s: %s (%d chars)", session_id, path, len(combined))
        return path

    def load(self) -> str:
        """Load all `memory/*.md` facts as one XML-framed block ("" when none)."""
        if not self.dir.exists():
            return ""
        blocks: list[str] = []
        for path in sorted(self.dir.glob("*.md")):
            try:
                text = path.read_text(encoding="utf-8", errors="replace").strip()
            except Exception as e:
                logger.warning("Failed to read memory file %s: %s", path, e)
                continue
            if text:
                blocks.append(f"<memory_file src=\"{path.name}\">\n{text}\n</memory_file>")
        return "\n\n".join(blocks)

    def load_plain(self) -> str:
        """Load all memory facts as plain text (no XML framing)."""
        if not self.dir.exists():
            return ""
        parts: list[str] = []
        for path in sorted(self.dir.glob("*.md")):
            try:
                text = path.read_text(encoding="utf-8", errors="replace").strip()
            except Exception as e:
                logger.warning("Failed to read memory file %s: %s", path, e)
                continue
            if text:
                parts.append(text)
        return "\n\n".join(parts)
