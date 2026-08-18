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
    created_at: float = field(default_factory=_time.monotonic)


_STORE: dict[str, dict[str, SessionFileRecord]] = {}
_LOCK = threading.Lock()


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _session_map(session_id: str) -> dict[str, SessionFileRecord]:
    return _STORE.setdefault(session_id, {})


def record_write(session_id: str, path: str, content: str) -> None:
    """Record that ``path`` was written with this exact content this session."""
    now = _time.monotonic()
    with _LOCK:
        rec = _session_map(session_id).get(path)
        if rec is None:
            rec = SessionFileRecord(
                path=path,
                content_hash=_content_hash(content),
                size=len(content.encode("utf-8")),
                last_edited_at=now,
            )
        else:
            rec.content_hash = _content_hash(content)
            rec.size = len(content.encode("utf-8"))
            rec.writes += 1
            rec.last_edited_at = now
        _session_map(session_id)[path] = rec
        _dirty_sessions.add(session_id)


def record_edit(session_id: str, path: str) -> None:
    """Mark ``path`` as modified this session (keeps the last known hash)."""
    now = _time.monotonic()
    with _LOCK:
        rec = _session_map(session_id).get(path)
        if rec is None:
            rec = SessionFileRecord(path=path, content_hash="", size=0, last_edited_at=now)
        else:
            rec.edits += 1
            rec.last_edited_at = now
        _session_map(session_id)[path] = rec
        _dirty_sessions.add(session_id)


def record_read(session_id: str, path: str) -> None:
    """Mark ``path`` as read this session for staleness tracking."""
    now = _time.monotonic()
    with _LOCK:
        rec = _session_map(session_id).get(path)
        if rec is None:
            rec = SessionFileRecord(path=path, content_hash="", size=0, last_read_at=now)
        else:
            rec.last_read_at = now
        _session_map(session_id)[path] = rec
        _dirty_sessions.add(session_id)


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


def known_files(session_id: str) -> dict[str, SessionFileRecord]:
    with _LOCK:
        return dict(_session_map(session_id))


def reset_session(session_id: str) -> None:
    with _LOCK:
        _STORE.pop(session_id, None)
        _dirty_sessions.discard(session_id)


_dirty_sessions: set[str] = set()


def _mark_dirty(session_id: str) -> None:
    with _LOCK:
        _dirty_sessions.add(session_id)


def get_dirty_sessions() -> set[str]:
    """Return snapshot of session IDs with unsaved workspace changes."""
    with _LOCK:
        return set(_dirty_sessions)


def mark_clean(session_id: str) -> None:
    """Clear dirty flag for ``session_id`` (called after successful DB flush)."""
    with _LOCK:
        _dirty_sessions.discard(session_id)


async def flush_to_db(session_id: str, repo) -> None:
    """Persist all workspace records for ``session_id`` to the DB.

    ``repo`` must be a ``SessionWorkspaceRepository`` instance.  This is a
    no-op when there are no dirty records for the session.
    """
    if session_id not in get_dirty_sessions():
        return
    records = known_files(session_id)
    if not records:
        try:
            await repo.delete_session(session_id)
        except Exception:
            logger.debug("flush_to_db: failed to delete workspace for %s", session_id)
        mark_clean(session_id)
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
        mark_clean(session_id)
    except Exception:
        logger.debug("flush_to_db: failed to persist workspace for %s", session_id)


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
