"""Cached workspace statistics used to steer exploration.

Provides a cheap, ignore-aware file count and top-level directory map for the
active workspace. Consumers:

- ``bash`` recursion guard: estimates the blast radius of whole-tree commands
  *before* executing them, so unbounded enumerations fail fast with guidance
  instead of dumping megabytes into the context.
- Future context seeding / explore delegation.

The scan is bounded (``MAX_INDEX_FILES``) so multi-million-file workspaces
degrade to an approximate count rather than stalling the server.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from server.workspace.ignore import get_matcher

logger = logging.getLogger(__name__)

MAX_INDEX_FILES = 200_000
CACHE_TTL_SECONDS = 120.0


@dataclass
class WorkspaceStats:
    total_files: int
    top_level: dict[str, int] = field(default_factory=dict)
    truncated: bool = False

    def describe_top_level(self, max_entries: int = 12) -> str:
        parts = [
            f"{name}/ ({count})" if name else f"(root files: {count})"
            for name, count in sorted(self.top_level.items(), key=lambda kv: -kv[1])
        ]
        shown = parts[:max_entries]
        if len(parts) > max_entries:
            shown.append(f"... +{len(parts) - max_entries} more")
        return ", ".join(shown)


_CACHE: dict[str, tuple[float, WorkspaceStats]] = {}
_LOCK = threading.Lock()


def _scan(root: Path) -> WorkspaceStats:
    matcher = get_matcher(root)
    matcher.refresh()
    stats = WorkspaceStats(total_files=0)
    stack: list[str] = [""]
    while stack:
        prefix = stack.pop()
        current = root / prefix if prefix else root
        try:
            entries = sorted(p.name for p in current.iterdir())
        except OSError:
            continue
        dirs: list[str] = []
        for name in entries:
            rel = f"{prefix}/{name}" if prefix else name
            try:
                is_dir = (root / rel).is_dir()
            except OSError:
                continue
            if matcher.is_ignored_dir(rel) if is_dir else matcher.is_ignored(rel):
                continue
            if is_dir:
                dirs.append(rel)
            elif stats.total_files < MAX_INDEX_FILES:
                stats.total_files += 1
                top = rel.split("/", 1)[0] if "/" in rel else ""
                stats.top_level[top] = stats.top_level.get(top, 0) + 1
            else:
                stats.truncated = True
        # Depth-first via stack; reversed keeps alphabetical order stable.
        stack.extend(reversed(dirs))
    return stats


def get_workspace_stats(root: str | Path, force_refresh: bool = False) -> WorkspaceStats:
    """Return cached stats for ``root``, rebuilding when stale or missing."""
    key = str(Path(root).resolve())
    now = time.monotonic()
    with _LOCK:
        cached = _CACHE.get(key)
        if cached and not force_refresh and (now - cached[0]) < CACHE_TTL_SECONDS:
            return cached[1]
    stats = _scan(Path(root))
    with _LOCK:
        _CACHE[key] = (now, stats)
    return stats


def invalidate_workspace_stats(root: str | Path) -> None:
    with _LOCK:
        _CACHE.pop(str(Path(root).resolve()), None)
