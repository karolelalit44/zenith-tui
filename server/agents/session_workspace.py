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
import threading
from dataclasses import dataclass


@dataclass
class SessionFileRecord:
    path: str
    content_hash: str
    size: int
    writes: int = 0
    edits: int = 0


_STORE: dict[str, dict[str, SessionFileRecord]] = {}
_LOCK = threading.Lock()


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _session_map(session_id: str) -> dict[str, SessionFileRecord]:
    return _STORE.setdefault(session_id, {})


def record_write(session_id: str, path: str, content: str) -> None:
    """Record that ``path`` was written with this exact content this session."""
    with _LOCK:
        rec = _session_map(session_id).get(path)
        if rec is None:
            rec = SessionFileRecord(
                path=path,
                content_hash=_content_hash(content),
                size=len(content.encode("utf-8")),
            )
        else:
            rec.content_hash = _content_hash(content)
            rec.size = len(content.encode("utf-8"))
            rec.writes += 1
        _session_map(session_id)[path] = rec


def record_edit(session_id: str, path: str) -> None:
    """Mark ``path`` as modified this session (keeps the last known hash)."""
    with _LOCK:
        rec = _session_map(session_id).get(path)
        if rec is None:
            rec = SessionFileRecord(path=path, content_hash="", size=0)
        rec.edits += 1
        _session_map(session_id)[path] = rec


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
