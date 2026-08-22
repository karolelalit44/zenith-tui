"""Session-scoped file-state registry.

Tracks which relative paths this session has already written (and with what
content hash) so a later turn of the same session can (a) be told the files
already exist and (b) have byte-identical re-writes of its own earlier work
blocked. Records come only from real write/edit events — nothing here is
inferred or hardcoded per scenario.

The store is keyed by ``session_id`` and lives in-process for the lifetime of
the server process, which matches the lifespan of a websocket session.

Persistence: unsaved changes are tracked via ``_dirty_sessions``. Call
``flush_to_db`` after each prompt turn to batch-persist to the DB, and
``load_from_db`` on session resume to hydrate from disk.
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
# Per-session read cache: path -> {content_hash, output, ts}. A repeated read of
# an unchanged file within the same session returns the cached output instead of
# re-reading (and re-injecting) the full content. Cleared when the file changes.
# Bounded per session (oldest entries evicted) so long-lived sessions cannot
# grow it without limit.
_READ_CACHE: dict[str, dict[str, dict]] = {}
# Per-session full outputs of heavy tool calls (keyed by the relative path the
# output was stored under). Survives only for the process lifetime; the file
# itself is on disk under the workspace's hidden directory. Also bounded.
_HEAVY_OUTPUTS: dict[str, dict[str, str]] = {}
_MAX_READ_CACHE_ENTRIES = 200
_MAX_HEAVY_OUTPUT_ENTRIES = 100
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


def record_write(session_id: str, path: str, content: str) -> None:
    """Record that ``path`` was written with this exact content this session."""
    now = _time.time()
    with _LOCK:
        rec = _session_map(session_id).get(path)
        if rec is None:
            rec = SessionFileRecord(
                path=path,
                content_hash=_content_hash(content),
                size=len(content.encode("utf-8")),
                writes=1,
                last_edited_at=now,
            )
        else:
            rec.content_hash = _content_hash(content)
            rec.size = len(content.encode("utf-8"))
            rec.writes += 1
            rec.last_edited_at = now
        _session_map(session_id)[path] = rec
        _READ_CACHE.get(session_id, {}).pop(path, None)
        _mark_dirty_locked(session_id)


def record_edit(session_id: str, path: str) -> None:
    """Mark ``path`` as modified this session (keeps the last known hash)."""
    now = _time.time()
    with _LOCK:
        rec = _session_map(session_id).get(path)
        if rec is None:
            rec = SessionFileRecord(
                path=path, content_hash="", size=0, edits=1, last_edited_at=now
            )
        else:
            rec.edits += 1
            rec.last_edited_at = now
        _session_map(session_id)[path] = rec
        _READ_CACHE.get(session_id, {}).pop(path, None)
        _mark_dirty_locked(session_id)


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
        _dirty_sessions_add_locked(session_id)


def is_stale(session_id: str, path: str) -> bool:
    """Return True if ``path`` was read before its last edit in this session."""
    with _LOCK:
        rec = _session_map(session_id).get(path)
        if rec is None or rec.last_read_at == 0.0 or rec.last_edited_at == 0.0:
            return False
        return rec.last_edited_at > rec.last_read_at


def is_identical_replay(session_id: str, path: str, content: str) -> bool:
    """True when this exact content was already written for this path in this session."""
    with _LOCK:
        rec = _session_map(session_id).get(path)
        if rec is None or not rec.content_hash:
            return False
        return rec.content_hash == _content_hash(content)


def store_cached_read(session_id: str, path: str, output: str, content_hash: str) -> None:
    """Cache a successful file-read output under ``(session, path)``.

    Only the exact content hash that produced ``output`` is stored; a later read
    returns the cache only while the on-disk hash still matches.
    """
    with _LOCK:
        _READ_CACHE.setdefault(session_id, {})[path] = {
            "content_hash": content_hash,
            "output": output,
            "ts": _time.monotonic(),
        }
        _bound_entries(_READ_CACHE, session_id, _MAX_READ_CACHE_ENTRIES)


def store_cached_read_output(session_id: str, path: str, output: str) -> None:
    """Convenience: cache ``output`` for ``path``, hashing it internally."""
    store_cached_read(session_id, path, output, _content_hash(output))


def cached_read_for(session_id: str, path: str, current_hash: str) -> str | None:
    """Return the cached read output for ``path`` only while unchanged.

    ``current_hash`` is the hash of the file's current content; the cache is
    returned only when it matches the hash the cached output was produced from.
    """
    return get_cached_read(session_id, path, current_hash)


def current_path_hash(path_text: str) -> str:
    """Hash a text value (used to fingerprint a file's current content)."""
    return _content_hash(path_text)


def get_cached_read(session_id: str, path: str, content_hash: str) -> str | None:
    """Return the cached read output for ``path`` if unchanged (hash matches)."""
    with _LOCK:
        entry = _READ_CACHE.get(session_id, {}).get(path)
        if entry is None:
            return None
        if entry.get("content_hash") != content_hash:
            _READ_CACHE.get(session_id, {}).pop(path, None)
            return None
        return entry.get("output")


def invalidate_read_cache(session_id: str, path: str | None = None) -> None:
    """Drop cached reads for a session (or a single path) after a mutation."""
    with _LOCK:
        if path is not None:
            _READ_CACHE.get(session_id, {}).pop(path, None)
        else:
            _READ_CACHE.pop(session_id, None)


def store_heavy_output(session_id: str, rel_path: str, output: str) -> None:
    """Keep the full output of a heavy tool call for re-read within the session."""
    with _LOCK:
        _HEAVY_OUTPUTS.setdefault(session_id, {})[rel_path] = output
        _bound_entries(_HEAVY_OUTPUTS, session_id, _MAX_HEAVY_OUTPUT_ENTRIES)


def read_heavy_output(session_id: str, rel_path: str) -> str | None:
    """Return the stored full output of a heavy tool call, or ``None``."""
    with _LOCK:
        return _HEAVY_OUTPUTS.get(session_id, {}).get(rel_path)


def known_files(session_id: str) -> dict[str, SessionFileRecord]:
    with _LOCK:
        return dict(_session_map(session_id))


def reset_session(session_id: str) -> None:
    with _LOCK:
        _STORE.pop(session_id, None)
        _READ_CACHE.pop(session_id, None)
        _HEAVY_OUTPUTS.pop(session_id, None)
        _dirty_sessions.discard(session_id)
        _dirty_epochs.pop(session_id, None)


_dirty_sessions: set[str] = set()
# Monotonic per-session counter bumped on every mutation. flush_to_db uses it
# to detect writes that landed while an upsert was in flight: without this,
# mark_clean after a slow await would silently discard those newer changes.
_dirty_epochs: dict[str, int] = {}


def _dirty_sessions_add_locked(session_id: str) -> None:
    """Register a mutation (caller holds ``_LOCK``): dirty flag + epoch bump."""
    _dirty_sessions.add(session_id)
    _dirty_epochs[session_id] = _dirty_epochs.get(session_id, 0) + 1


def _mark_dirty_locked(session_id: str) -> None:
    _dirty_sessions_add_locked(session_id)


def _mark_dirty(session_id: str) -> None:
    with _LOCK:
        _mark_dirty_locked(session_id)


def get_dirty_sessions() -> set[str]:
    """Return snapshot of session IDs with unsaved workspace changes."""
    with _LOCK:
        return set(_dirty_sessions)


def mark_clean(session_id: str) -> None:
    """Clear dirty flag for ``session_id`` (called after successful DB flush)."""
    with _LOCK:
        _dirty_sessions.discard(session_id)


def _snapshot_epoch(session_id: str) -> int:
    with _LOCK:
        return _dirty_epochs.get(session_id, 0)


def _mark_clean_if_unchanged(session_id: str, epoch: int) -> bool:
    """Clear the dirty flag only if no mutation happened since ``epoch``.

    Returns True when the flag was cleared; False means newer writes are
    still pending and must be flushed by a later call.
    """
    with _LOCK:
        if _dirty_epochs.get(session_id, 0) != epoch:
            return False
        _dirty_sessions.discard(session_id)
        return True


async def flush_to_db(session_id: str, repo) -> None:
    """Persist all workspace records for ``session_id`` to the DB.

    ``repo`` must be a ``SessionWorkspaceRepository`` instance.  This is a
    no-op when there are no dirty records for the session.

    Concurrency: the record snapshot is taken before the await; if another
    turn mutates the workspace while ``upsert_batch`` is in flight, the
    post-flush clean-up only clears the dirty flag when nothing changed in
    the meantime (C-F07 lost-update guard).
    """
    start_epoch = _snapshot_epoch(session_id)
    if session_id not in get_dirty_sessions():
        return
    records = known_files(session_id)
    if not records:
        try:
            await repo.delete_session(session_id)
        except Exception:
            logger.warning("flush_to_db: failed to delete workspace for %s", session_id)
        _mark_clean_if_unchanged(session_id, start_epoch)
        return
    batch = [
        {
            "path": rec.path,
            "content_hash": rec.content_hash,
            "size": rec.size,
            "writes": rec.writes,
            "edits": rec.edits,
            "last_read_at": rec.last_read_at,
            "last_edited_at": rec.last_edited_at,
        }
        for rec in records.values()
    ]
    try:
        await repo.upsert_batch(session_id, batch)
    except Exception as exc:
        logger.warning("flush_to_db: failed to persist workspace for %s: %s", session_id, exc)
        return
    _mark_clean_if_unchanged(session_id, start_epoch)


async def load_from_db(session_id: str, repo) -> None:
    """Hydrate in-memory ``_STORE`` from the DB for ``session_id``.

    Called on session resume so file tracking survives server restarts.  Existing
    in-memory state for the session is replaced wholesale.
    """
    try:
        rows = await repo.get_all(session_id)
    except Exception:
        logger.debug("load_from_db: failed to load workspace for %s", session_id)
        return
    if not rows:
        return
    with _LOCK:
        session_map: dict[str, SessionFileRecord] = {}
        for row in rows:
            session_map[row["path"]] = SessionFileRecord(
                path=row["path"],
                content_hash=row.get("content_hash", ""),
                size=row.get("size", 0),
                writes=row.get("writes", 0),
                edits=row.get("edits", 0),
                last_read_at=row.get("last_read_at", 0.0),
                last_edited_at=row.get("last_edited_at", 0.0),
            )
        _STORE[session_id] = session_map
    logger.info("Loaded %d workspace records for session %s", len(rows), session_id)
