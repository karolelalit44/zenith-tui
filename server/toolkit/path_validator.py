
from __future__ import annotations
from pathlib import Path


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
        return resolved
    except ValueError:
        return None
