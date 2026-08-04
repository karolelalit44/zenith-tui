from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)
MEMORY_DIR = "memory"
PROJECT_MEMORY_FILE = "PROJECT.md"
MAX_FILE_CHARS = 8000
NO_CONTEXT_SENTINEL = "No prior context available."
_ROLLOVER_HEADER = "# Zenith memory (rolled over)"
_PROJECT_HEADER = "# Zenith project memory (cross-session)"


def _sanitize(name: str) -> str:
    return re.sub("[^\\w-]", "_", name)


class MemoryStore:
    def __init__(self, workspace_root: str, max_chars: int = MAX_FILE_CHARS) -> None:
        self.root = Path(workspace_root)
        self.dir = self.root / MEMORY_DIR
        self.max_chars = max_chars

    def _ensure_dir(self) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        return self.dir

    def path_for(self, session_id: str) -> Path:
        return self._ensure_dir() / f"{_sanitize(session_id)}.md"

    def project_path(self) -> Path:
        return self._ensure_dir() / PROJECT_MEMORY_FILE

    def append(self, session_id: str, facts: str) -> Path:
        if not facts or not facts.strip():
            return self.path_for(session_id)
        path = self.path_for(session_id)
        block = (
            f"## Durable facts — {datetime.now().isoformat(timespec='seconds')}\n{facts.strip()}\n"
        )
        existing = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        combined = (existing + "\n" + block).strip() + "\n"
        if len(combined) > self.max_chars:
            combined = self._trim_to_fit(combined)
        path.write_text(combined, encoding="utf-8")
        logger.info("Memory updated for session %s: %s (%d chars)", session_id, path, len(combined))
        return path

    def append_project(self, facts: str) -> Path:
        if not facts or not facts.strip():
            return self.project_path()
        path = self.project_path()
        block = (
            f"## Project facts — {datetime.now().isoformat(timespec='seconds')}\n{facts.strip()}\n"
        )
        existing = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        combined = (existing + "\n" + block).strip() + "\n"
        if len(combined) > self.max_chars:
            combined = self._trim_project_to_fit(combined)
        path.write_text(combined, encoding="utf-8")
        logger.info("Project memory updated: %s (%d chars)", path, len(combined))
        return path

    def _split_blocks(self, text: str) -> list[str]:
        cleaned = text.replace(_ROLLOVER_HEADER, "").strip()
        if not cleaned:
            return []
        parts = re.split("(?=^## )", cleaned, flags=re.MULTILINE)
        return [p.strip() for p in parts if p.strip()]

    def _split_project_blocks(self, text: str) -> list[str]:
        cleaned = text.replace(_PROJECT_HEADER, "").strip()
        if not cleaned:
            return []
        parts = re.split("(?=^## )", cleaned, flags=re.MULTILINE)
        return [p.strip() for p in parts if p.strip()]

    def _trim_to_fit(self, text: str) -> str:
        header = _ROLLOVER_HEADER + "\n\n"
        blocks = self._split_blocks(text)
        if not blocks:
            return text
        kept: list[str] = []
        for block in reversed(blocks):
            if len(header + "\n\n".join([block, *kept])) > self.max_chars:
                break
            kept.insert(0, block)
        if not kept:
            out = header + blocks[-1]
            if len(out) > self.max_chars:
                out = out[: self.max_chars].rstrip() + "\n"
            return out + "\n"
        return header + "\n\n".join(kept) + "\n"

    def _trim_project_to_fit(self, text: str) -> str:
        header = _PROJECT_HEADER + "\n\n"
        blocks = self._split_project_blocks(text)
        if not blocks:
            return text
        kept: list[str] = []
        for block in reversed(blocks):
            if len(header + "\n\n".join([block, *kept])) > self.max_chars:
                break
            kept.insert(0, block)
        if not kept:
            out = header + blocks[-1]
            if len(out) > self.max_chars:
                out = out[: self.max_chars].rstrip() + "\n"
            return out + "\n"
        return header + "\n\n".join(kept) + "\n"

    def load(self) -> str:
        if not self.dir.exists():
            return ""
        blocks: list[str] = []
        project_path = self.project_path()
        if project_path.exists():
            try:
                text = project_path.read_text(encoding="utf-8", errors="replace").strip()
                if text:
                    blocks.append(
                        f'<memory_file src="{PROJECT_MEMORY_FILE}">\n{text}\n</memory_file>'
                    )
            except Exception as e:
                logger.warning("Failed to read project memory file %s: %s", project_path, e)
        for path in sorted(self.dir.glob("*.md")):
            if path.name == PROJECT_MEMORY_FILE:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace").strip()
            except Exception as e:
                logger.warning("Failed to read memory file %s: %s", path, e)
                continue
            if text:
                blocks.append(f'<memory_file src="{path.name}">\n{text}\n</memory_file>')
        return "\n\n".join(blocks)

    def load_plain(self) -> str:
        if not self.dir.exists():
            return ""
        parts: list[str] = []
        project_path = self.project_path()
        if project_path.exists():
            try:
                text = project_path.read_text(encoding="utf-8", errors="replace").strip()
                if text:
                    parts.append(text)
            except Exception as e:
                logger.warning("Failed to read project memory file %s: %s", project_path, e)
        for path in sorted(self.dir.glob("*.md")):
            if path.name == PROJECT_MEMORY_FILE:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace").strip()
            except Exception as e:
                logger.warning("Failed to read memory file %s: %s", path, e)
                continue
            if text:
                parts.append(text)
        return "\n\n".join(parts)
