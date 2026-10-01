from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from server.config.constants import (
    MISSING_PATH_ENTRIES_KEY,
    MISSING_PATH_HINT_KEY,
    MISSING_PATH_HINT_LEAD,
    MISSING_PATH_HINT_MAX_ENTRIES,
    MISSING_PATH_KEY,
    MISSING_PATH_RECOVERABLE_KEY,
)


class MissingPathHint(TypedDict):
    """Metadata a search tool writes when the caller named a path that is absent.

    Declared once because it crosses the server/TUI boundary: the TUI reads
    ``recoverable_miss`` to render a miss as a recoverable miss rather than a
    broken tool. Both producers (``GlobTool``, ``GrepTool``) import this rather
    than spelling the keys out, so the contract has one owner.
    """

    recoverable_miss: bool
    missing_path: str
    workspace_entries: list[str]
    hint: str


def workspace_path_hint(base: Path, requested: str | object) -> MissingPathHint:
    """Describe a missing path in terms of paths that do exist.

    A wrong path is a recoverable mistake, and the cheapest recovery is being
    told what is actually there. Listing the workspace root costs one directory
    read and is bounded, so it is done on the miss path rather than on every call.
    """
    requested_text = str(requested or "")
    entries: list[str] = []
    try:
        for child in sorted(base.iterdir(), key=lambda p: p.name.lower()):
            if child.name.startswith("."):
                continue
            suffix = "/" if child.is_dir() else ""
            entries.append(f"{child.name}{suffix}")
            if len(entries) >= MISSING_PATH_HINT_MAX_ENTRIES:
                break
    except OSError:
        entries = []
    hint = MISSING_PATH_HINT_LEAD
    if entries:
        hint += ": " + ", ".join(entries)
    return {
        MISSING_PATH_RECOVERABLE_KEY: True,
        MISSING_PATH_KEY: requested_text,
        MISSING_PATH_ENTRIES_KEY: entries,
        MISSING_PATH_HINT_KEY: hint,
    }