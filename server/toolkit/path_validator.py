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
