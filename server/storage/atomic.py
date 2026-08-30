"""Atomic file primitives for the file-based storage layer.

Every mutable JSON document is written via :func:`write_json_atomic`
(unique tempfile -> fsync -> os.replace) with a ``.bak`` sibling holding
the *previous known-good* content (written atomically before the replace),
so external corruption of the primary can always be rolled back one
version. JSONL files are strictly append-only except when an explicit
rewrite is requested (compaction, tool-event stripping), which goes
through the atomic replace path.
"""

from __future__ import annotations
import json
import logging
import os
import sys
import threading
import time
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any

__all__ = [
    "append_jsonl_sync",
    "read_json",
    "read_jsonl",
    "rewrite_jsonl_atomic",
    "write_json_atomic",
]

logger = logging.getLogger(__name__)

_replace_locks: dict[str, threading.RLock] = {}
_replace_locks_guard = threading.Lock()
_REPLACE_RETRIES = 20
_REPLACE_RETRY_DELAY = 0.025


def _target_lock(path: Path) -> threading.RLock:
    key = os.path.normcase(str(path))
    with _replace_locks_guard:
        lock = _replace_locks.get(key)
        if lock is None:
            lock = threading.RLock()
            _replace_locks[key] = lock
    return lock


def _tmp_name(target: Path) -> Path:
    """Unique-per-write temp name: PID + random suffix (thread/process safe)."""
    return target.with_name(f".{target.name}.tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}")


def _fsync_dir(path: Path) -> None:
    if sys.platform == "win32":
        return  # best-effort only on Windows
    try:
        fd = os.open(str(path), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def _replace_with_fsync(tmp: Path, target: Path, *, fsync: bool) -> None:
    last_exc: OSError | None = None
    for attempt in range(_REPLACE_RETRIES):
        try:
            with _target_lock(target):
                os.replace(tmp, target)
            if fsync:
                _fsync_dir(target.parent)
            return
        except PermissionError as exc:
            # Windows: destination momentarily held open by another handle.
            last_exc = exc
            time.sleep(_REPLACE_RETRY_DELAY * (attempt + 1))
    assert last_exc is not None
    raise last_exc


def _write_previous_to_bak(path: Path, *, fsync: bool) -> None:
    """Snapshot the *current* (pre-replace) content into ``path.bak``.

    Runs atomically (own temp + replace) BEFORE the main replace so the
    backup always holds the last known-good version, never a torn mix.
    """
    bak = path.with_suffix(path.suffix + ".bak")
    tmp = _tmp_name(bak)
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return  # first write ever — no previous version to keep
    except OSError as exc:
        logger.warning("Backup read failed for %s: %s", path, exc)
        return
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            if fsync:
                f.flush()
                os.fsync(f.fileno())
        _replace_with_fsync(tmp, bak, fsync=fsync)
    except OSError as exc:
        logger.warning("Backup write failed for %s: %s", bak, exc)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def write_json_atomic(
    path: Path,
    data: object,
    *,
    backup: bool = True,
    fsync: bool = True,
    private: bool = False,
) -> None:
    """Atomically replace ``path`` with ``data`` serialized as JSON.

    The previous known-good content is kept in a ``.bak`` sibling (updated
    atomically before the swap), enabling one-version rollback when the
    primary is later corrupted externally. With ``private=True`` the file
    is restricted to the owner on POSIX (0o600); no guarantee is claimed
    on platforms where the mode cannot be enforced.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, ensure_ascii=False, default=str)
    tmp = _tmp_name(path)
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(payload)
            if fsync:
                f.flush()
                os.fsync(f.fileno())
        if private and os.name == "posix":
            try:
                os.chmod(tmp, 0o600)
            except OSError as exc:
                logger.warning("Could not restrict permissions on %s: %s", path, exc)
        # One critical section for backup-read + swap: another writer can
        # never observe (or replace under) an open primary.
        with _target_lock(path):
            if backup:
                _write_previous_to_bak(path, fsync=fsync)
            _replace_with_fsync(tmp, path, fsync=fsync)
    finally:
        if tmp.exists():
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass


def read_json(path: Path, default: Any = None) -> Any:
    """Read a JSON document, tolerating absence and corruption.

    Falls back to the ``.bak`` sibling (last known-good version) when the
    primary is corrupt, then to ``default``. Every fallback is logged;
    contents are never logged.
    """
    bak = path.with_suffix(path.suffix + ".bak")
    for candidate, role in ((path, "primary"), (bak, "backup")):
        try:
            if not candidate.exists():
                continue
            return json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Storage %s unreadable (%s): %s", role, type(exc).__name__, candidate)
            continue
    return default


def append_jsonl_sync(path: Path, record: dict) -> None:
    """Append one JSON line; caller is expected to hold the storage lock."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, default=str)
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())


def rewrite_jsonl_atomic(path: Path, records: Iterable[dict[str, Any]]) -> int:
    """Replace the whole JSONL file atomically; returns record count."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for rec in records:
        lines.append(json.dumps(rec, ensure_ascii=False, default=str))
    tmp = _tmp_name(path)
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.writelines(line + "\n" for line in lines)
            f.flush()
            os.fsync(f.fileno())
        _replace_with_fsync(tmp, path, fsync=True)
    finally:
        if tmp.exists():
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
    return len(lines)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read all records from a JSONL file.

    A missing file yields ``[]``. A corrupt/partial trailing line (crash
    during append) is skipped with a logged warning. Other OS-level read
    failures PROPAGATE: callers must never mistake an I/O error for an
    empty log, or a subsequent rewrite would destroy valid history.
    """
    out: list[dict[str, Any]] = []
    if not path.exists():
        return out
    skipped = 0
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                skipped += 1
                continue
            if isinstance(rec, dict):
                out.append(rec)
    if skipped:
        logger.warning("%s: skipped %d corrupt/partial line(s)", path, skipped)
    return out
