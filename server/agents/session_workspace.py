"""Session-scoped file-state registry.

Tracks which relative paths this session has already written (and with what
content hash) so a later turn of the same session can (a) be told the files
already exist and (b) have byte-identical re-writes of its own earlier work
blocked. Records come only from real write/edit events — nothing here is
inferred or hardcoded per scenario.

The store is keyed by ``session_id`` and lives in-process for the lifetime of
the server process, which matches the lifespan of a websocket session.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time as _time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)



@dataclass
class SessionFileRecord:
    path: str
    content_hash: str
    size: int
    writes: int = 0
    edits: int = 0
    last_read_at: float = 0.0
    last_edited_at: float = 0.0
    # Wall-clock epoch seconds: these fields are persisted to DB columns and
    # compared across process restarts; monotonic clocks are meaningless there.
    created_at: float = field(default_factory=_time.time)


_STORE: dict[str, dict[str, SessionFileRecord]] = {}
# Per-session read cache: path -> cache entry. A repeated read of an unchanged
# file within the same session returns the cached output instead of re-reading
# (and re-injecting) the full content. The entry is keyed by an mtime+size
# fingerprint of the file at read time; a later read returns the cache only
# while the on-disk fingerprint still matches. Cleared when the file changes.
# Bounded per session (oldest entries evicted) so long-lived sessions cannot
# grow it without limit.
#
# Entry shape:
#   {
#     "mtime_ns": int,          # stat().st_mtime_ns at read time
#     "size": int,              # stat().st_size at read time
#     "total_lines": int,       # total lines in the file at read time
#     "slices": {               # (offset, limit) -> formatted output
#         (offset, limit): {
#             "output": str,
#             "count": int,     # how many times this slice was served
#         },
#     },
#     "history": [(offset, limit), ...],  # all distinct ranges read for this path
#   }
_READ_CACHE: dict[str, dict[str, dict]] = {}
_MAX_READ_CACHE_ENTRIES = 200
_LOCK = threading.Lock()


def _bound_entries(store: dict, session_id: str, cap: int) -> None:
    """Evict oldest-inserted entries for a session beyond ``cap``.

    Caller must hold ``_LOCK``. Dicts preserve insertion order, so popping
    from the front approximates FIFO eviction, which matches how these caches
    are used (recent reads/outputs are the ones worth keeping).
    """
    entries = store.get(session_id)
    if entries is None:
        return
    while len(entries) > cap:
        entries.pop(next(iter(entries)))


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _session_map(session_id: str) -> dict[str, SessionFileRecord]:
    return _STORE.setdefault(session_id, {})



def record_read(session_id: str, path: str) -> None:
    """Mark ``path`` as read this session for staleness tracking."""
    now = _time.time()
    with _LOCK:
        rec = _session_map(session_id).get(path)
        if rec is None:
            rec = SessionFileRecord(path=path, content_hash="", size=0, last_read_at=now)
        else:
            rec.last_read_at = now
        _session_map(session_id)[path] = rec



def is_identical_replay(session_id: str, path: str, content: str) -> bool:
    """True when this exact content was already written for this path in this session."""
    with _LOCK:
        rec = _session_map(session_id).get(path)
        if rec is None or not rec.content_hash:
            return False
        return rec.content_hash == _content_hash(content)


def _cache_evict(session_id: str, path: str) -> None:
    """Drop the cached read entry for ``path``. Caller must hold ``_LOCK``."""
    paths = _READ_CACHE.get(session_id)
    if paths is not None:
        paths.pop(path, None)


def cache_file_read(
    session_id: str,
    path: str,
    offset: int,
    limit: int,
    output: str,
    mtime_ns: int,
    size: int,
    total_lines: int,
) -> None:
    """Cache a successful file-read slice under ``(session, path, offset, limit)``.

    The (``mtime_ns``, ``size``) pair is the staleness fingerprint — a later read
    returns the cache only while the on-disk stat still matches. This is the
    industry-standard O(1) change detection (matches Claude Code's approach).

    ``path`` must be an absolute, resolved path (callers use ``str(resolved)`` or
    ``str(validate_path(rel, root))``). No further normalization is done here;
    the caller owns the canonical key.
    """
    with _LOCK:
        entry = _READ_CACHE.get(session_id, {}).get(path)
        if entry is None or entry.get("mtime_ns") != mtime_ns or entry.get("size") != size:
            entry = {
                "mtime_ns": mtime_ns,
                "size": size,
                "total_lines": total_lines,
                "slices": {},
                "history": [],
            }
            _READ_CACHE.setdefault(session_id, {})[path] = entry
        entry["slices"][(offset, limit)] = {"output": output}
        if (offset, limit) not in entry["history"]:
            entry["history"].append((offset, limit))
        _bound_entries(_READ_CACHE, session_id, _MAX_READ_CACHE_ENTRIES)


def get_cached_read(
    session_id: str, path: str, offset: int, limit: int, mtime_ns: int, size: int
) -> str | None:
    """Return the cached read output for ``path`` slice if unchanged.

    ``mtime_ns``/``size`` is the file's current stat; the cache is returned only
    when it matches the fingerprint the cached output was produced from. On a
    fingerprint mismatch the stale entry is evicted.

    ``path`` must be an absolute, resolved path (same key space as ``cache_file_read``).
    """
    with _LOCK:
        entry = _READ_CACHE.get(session_id, {}).get(path)
        if entry is None:
            return None
        if entry.get("mtime_ns") != mtime_ns or entry.get("size") != size:
            _cache_evict(session_id, path)
            return None
        slice_entry = entry.get("slices", {}).get((offset, limit))
        if slice_entry is None:
            return None
        count = slice_entry.get("count", 0)
        slice_entry["count"] = count + 1
        return slice_entry.get("output")


def get_read_history(session_id: str, path: str) -> list[tuple[int, int]]:
    """Return all distinct ``(offset, limit)`` ranges read for ``path`` this session.

    ``path`` must be an absolute, resolved path (same key space as ``cache_file_read``).
    """
    with _LOCK:
        entry = _READ_CACHE.get(session_id, {}).get(path)
        if entry is None:
            return []
        return list(entry.get("history", []))


def cached_file_fingerprint(session_id: str, path: str, mtime_ns: int, size: int) -> bool:
    """True when a cache entry exists for ``path`` and the fingerprint still matches.

    ``path`` must be an absolute, resolved path (same key space as ``cache_file_read``).
    """
    with _LOCK:
        entry = _READ_CACHE.get(session_id, {}).get(path)
        return entry is not None and entry.get("mtime_ns") == mtime_ns and entry.get("size") == size


def is_range_covered(
    session_id: str, path: str, offset: int, limit: int, mtime_ns: int | None = None, size: int | None = None
) -> bool:
    """True when prior reads of ``path`` fully cover ``[offset, offset+limit)``.

    Used for overlap dedup: if the requested range is fully contained within the
    union of previously read ranges (with uncached-runs still accurate), a
    re-read is redundant and can be served from cache.

    ``mtime_ns``/``size`` (when given) are forwarded to ``covering_slice_for``
    so a stale cache entry (changed fingerprint) is correctly rejected here
    rather than causing a misleading "covered" result that get_cached_read then
    has to evict separately.

    ``path`` must be an absolute, resolved path (same key space as ``cache_file_read``).
    """
    return covering_slice_for(session_id, path, offset, limit, mtime_ns=mtime_ns, size=size) is not None


def covering_slice_for(
    session_id: str, path: str, offset: int, limit: int, mtime_ns: int | None = None, size: int | None = None
) -> tuple[int, int] | None:
    """Return the cached slice key that fully covers ``[offset, offset+limit)``.

    Returns ``None`` when no single prior read covers the whole requested range
    or when the cache entry is stale. ``mtime_ns``/``size`` (when given) must
    match the stale fingerprint; otherwise a fresh disk read is required.

    ``path`` must be an absolute, resolved path (same key space as ``cache_file_read``).
    """
    with _LOCK:
        entry = _READ_CACHE.get(session_id, {}).get(path)
        if entry is None:
            return None
        if mtime_ns is not None and entry.get("mtime_ns") != mtime_ns:
            _cache_evict(session_id, path)
            return None
        if size is not None and entry.get("size") != size:
            _cache_evict(session_id, path)
            return None
        end = offset + limit
        for h_off, h_lim in entry.get("history", []):
            if h_off <= offset and h_off + h_lim >= end:
                return (h_off, h_lim)
        return None



def known_files(session_id: str) -> dict[str, SessionFileRecord]:
    with _LOCK:
        return dict(_session_map(session_id))


def reset_session(session_id: str) -> None:
    with _LOCK:
        _STORE.pop(session_id, None)
        _READ_CACHE.pop(session_id, None)

