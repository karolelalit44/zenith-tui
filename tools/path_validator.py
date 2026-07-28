"""Path validator — ensures file operations stay within workspace boundary."""

from __future__ import annotations

from pathlib import Path


def validate_path(rel_path: str, workspace_root: str) -> Path | None:
    """Validate that a relative path resolves within the workspace.

    Returns the resolved absolute Path if safe, or None if the path
    escapes the workspace boundary (e.g., '../../etc/passwd').
    """
    if not rel_path:
        return None

    workspace = Path(workspace_root).resolve()
    try:
        resolved = (workspace / rel_path).resolve()
    except (OSError, ValueError):
        return None

    # Check that resolved path is within workspace (or is the workspace itself)
    try:
        resolved.relative_to(workspace)
        return resolved
    except ValueError:
        return None
