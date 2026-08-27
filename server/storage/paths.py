"""Storage home resolution — replaces the SQLite database path.

All server-side persistent state lives under a single directory (the
"storage home"), defaulting to ``~/.zenith`` and overridden by the
``ZENITH_HOME`` environment variable (.env driven).

Sessions follow the industry pattern (Claude Code / Codex): ONE
append-only JSONL file per session, grouped in a folder per project
workspace:

    <home>/projects/<workspace-slug>/<session-id>.jsonl

The slug is the absolute workspace path with every non-alphanumeric
character replaced by ``-`` (e.g. ``D-vdo-code-zenith``). The real path
is stored inside the file's header record.
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

HOME_ENV_VAR = "ZENITH_HOME"

__all__ = ["HOME_ENV_VAR", "StorageHome", "default_home", "project_slug", "resolve_home"]


def default_home() -> Path:
    return Path.home() / ".zenith"


def resolve_home() -> Path:
    raw = os.environ.get(HOME_ENV_VAR, "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return default_home().resolve()


def project_slug(workspace_root: str) -> str:
    """Absolute workspace path -> filesystem-safe folder name."""
    try:
        abs_path = str(Path(workspace_root).expanduser().resolve())
    except OSError:
        abs_path = str(workspace_root)
    slug = re.sub(r"[^A-Za-z0-9]", "-", abs_path).strip("-")
    return slug[:200] or "default"


class StorageHome:
    """Typed handles for every file in the storage layout + the write lock."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root: Path = Path(root).expanduser().resolve() if root else resolve_home()
        self.lock = asyncio.Lock()

        self.profile_path = self.root / "user_profile.json"
        self.providers_path = self.root / "providers.json"
        self.models_path = self.root / "models.json"
        self.memory_index_path = self.root / "memory" / "index.json"
        self.projects_dir = self.root / "projects"

    # -- layout ------------------------------------------------------------
    @property
    def memory_path(self) -> Path:
        return self.root / "memory"

    def ensure_layout(self) -> None:
        for d in (
            self.root,
            self.projects_dir,
            self.memory_path,
        ):
            d.mkdir(parents=True, exist_ok=True)

    # -- per-project / per-session paths ------------------------------------
    def project_dir(self, workspace_root: str) -> Path:
        return self.projects_dir / project_slug(workspace_root)

    def session_file(self, session_id: str, workspace_root: str) -> Path:
        safe = "".join(c for c in session_id if c.isalnum() or c in "-_")
        if not safe or safe != session_id:
            raise ValueError(f"Invalid session id: {session_id!r}")
        return self.project_dir(workspace_root) / f"{safe}.jsonl"

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"StorageHome({str(self.root)!r})"
