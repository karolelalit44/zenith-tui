from __future__ import annotations

import platform
import re
from pathlib import Path

_WIN_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$", re.IGNORECASE)
_WIN_INVALID_CHARS = re.compile(r'[<>:"|?*\x00-\x1F]')


def validate_path(rel_path: str, workspace_root: str) -> Path | None:
    if not rel_path:
        return None
    workspace = Path(workspace_root).resolve()
    try:
        resolved = (workspace / rel_path).resolve()
    except (OSError, ValueError):
        return None
    try:
        resolved.relative_to(workspace)
    except ValueError:
        return None
    # Windows reserved name check (codex shell_spec.rs). The invalid-char
    # check targets the leaf name (e.g. "a<b>.txt"), not the full absolute
    # path which legitimately contains a drive colon and separators.
    if platform.system() == "Windows":
        if _WIN_RESERVED.match(resolved.name):
            return None
        if _WIN_INVALID_CHARS.search(resolved.name):
            return None
    return resolved


def is_destructive_write(target: Path, workspace_root: str) -> bool:
    """Codex-style destructive write check: verify resolved target before write.

    Checks if the write would overwrite an existing file, or target a system
    location. Codex shell_spec.rs:339-344 - no cross-shell deletion composition,
    verify resolved target before recursive delete.
    """
    try:
        ws = Path(workspace_root).resolve()
        target_resolved = target.resolve()
        target_resolved.relative_to(ws)
    except (OSError, ValueError):
        return True  # outside workspace = destructive
    if target_resolved.exists():
        return True  # overwriting existing = destructive
    return False


def is_destructive_delete(target: Path, workspace_root: str) -> bool:
    """Codex-style delete safety: verify target exists, is in workspace, not system."""
    try:
        ws = Path(workspace_root).resolve()
        target_resolved = target.resolve()
        target_resolved.relative_to(ws)
    except (OSError, ValueError):
        return True
    if not target_resolved.exists():
        return True  # deleting non-existent = suspicious
    return False
