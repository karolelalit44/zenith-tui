"""A shared, replayable record of file mutations for one session.

``apply_patch`` already snapshots every path it is about to touch and restores
them if a later hunk fails. That logic was correct but private to one tool, so
the other mutators — ``file_write``, ``file_edit``, ``file_delete`` — had no
rollback at all, and there was no record anywhere of what a session had changed.

The journal is that record, and it serves three purposes at once:

* **Rollback.** A mutation that fails part-way can be undone exactly, because
  the pre-image of every affected path is held in memory.
* **Revert.** The user can ask "undo that change", and the answer does not
  require re-deriving anything from git — the bytes are already here, including
  for files that were never committed.
* **Turn diffs.** A turn's net change can be rendered without re-reading the
  workspace, which matters because by the time a diff is displayed the file may
  already have moved on.

Entries are session-scoped and in-process. Nothing is persisted: a journal is a
recovery aid for the live session, not an audit log, and writing file bodies to
disk to maintain one would be a worse trade than losing it on restart.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

# Bytes of pre-image retained per path. A file larger than this is journaled by
# path and existence only: enough to report that it changed and to delete it on
# revert, without holding a copy of a large binary in memory for the session.
MAX_JOURNALLED_BYTES = 8 * 1024 * 1024

# Entries retained per session. Old entries are dropped oldest-first; the
# journal is for "undo the recent past", not an unbounded history.
MAX_ENTRIES_PER_SESSION = 500


@dataclass
class JournalEntry:
    """One mutation, with enough information to describe or undo it."""

    seq: int
    tool: str
    path: str
    action: Literal["create", "modify", "delete"]
    at: float
    bytes_before: int
    bytes_after: int = 0
    # Pre-image, or None when the file did not exist. None for a create; b"" for
    # a file that existed but was empty. Omitted when the content was too large.
    before: bytes | None = field(default=None, repr=False)
    after: bytes | None = field(default=None, repr=False)
    content_omitted: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        verb = {"create": "created", "modify": "modified", "delete": "deleted"}[self.action]
        detail = f"{self.bytes_before} -> {self.bytes_after} bytes"
        if self.content_omitted:
            detail += " (content too large to retain)"
        return f"#{self.seq} {verb} {self.path} ({detail})"


class MutationJournal:
    """Session-scoped mutation history with exact rollback."""

    def __init__(self) -> None:
        self._entries: dict[str, list[JournalEntry]] = {}
        self._seq = 0
        self._lock = threading.Lock()

    def record(
        self,
        session_id: str,
        *,
        tool: str,
        path: Path,
        action: Literal["create", "modify", "delete"],
        before: bytes | None,
        after: bytes | None,
        extra: dict[str, Any] | None = None,
    ) -> JournalEntry:
        """Record one completed mutation. ``before``/``after`` are pre/post images.

        A file too large to retain is recorded by size alone: revert can still
        report it, and a delete can still be undone by writing an empty file,
        which is the honest outcome rather than a silent no-op.
        """
        with self._lock:
            self._seq += 1
            keep = max(len(before or b""), len(after or b"")) <= MAX_JOURNALLED_BYTES
            entry = JournalEntry(
                seq=self._seq,
                tool=tool,
                path=str(path),
                action=action,
                at=time.time(),
                bytes_before=len(before or b""),
                bytes_after=len(after or b""),
                before=before if keep else None,
                after=after if keep else None,
                content_omitted=not keep,
                extra=dict(extra or {}),
            )
            log = self._entries.setdefault(session_id, [])
            log.append(entry)
            if len(log) > MAX_ENTRIES_PER_SESSION:
                del log[: len(log) - MAX_ENTRIES_PER_SESSION]
            return entry

    def entries(self, session_id: str, limit: int | None = None) -> list[JournalEntry]:
        with self._lock:
            log = list(self._entries.get(session_id, []))
        return log[-limit:] if limit else log

    def since(self, session_id: str, seq: int) -> list[JournalEntry]:
        with self._lock:
            return [e for e in self._entries.get(session_id, []) if e.seq > seq]

    def revert(self, session_id: str, seq: int) -> tuple[int, list[str], int]:
        """Undo every entry newer than ``seq``.

        Returns ``(restored, unrecoverable, remaining_seq)``. Entries are undone
        in reverse order, so overlapping edits unwind the way they were applied.
        A failure part-way through reports exactly which paths could not be put
        back rather than claiming a clean revert.
        """
        targets = self.since(session_id, seq)
        restored: list[str] = []
        failed: list[str] = []
        for entry in reversed(targets):
            if entry.content_omitted or entry.extra.get("directory"):
                failed.append(entry.path)
                continue
            target = Path(entry.path)
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                if entry.action == "create":
                    # The file did not exist before: revert means remove it.
                    if target.exists():
                        target.unlink()
                elif entry.before is not None:
                    target.write_bytes(entry.before)
                else:
                    failed.append(entry.path)
                    continue
                restored.append(entry.path)
            except OSError:
                failed.append(entry.path)
        with self._lock:
            log = self._entries.get(session_id)
            if log is not None:
                self._entries[session_id] = [e for e in log if e.seq <= seq]
        return len(restored), failed, seq

    def turn_diff(self, session_id: str, since_seq: int = 0) -> list[JournalEntry]:
        """Net mutations for a turn, oldest first, for rendering."""
        return self.since(session_id, since_seq)

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._entries.pop(session_id, None)

    def clear_all(self) -> None:
        with self._lock:
            self._entries.clear()


JOURNAL = MutationJournal()
