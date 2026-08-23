"""Single-file session format: discovery, record access, fold loader.

One append-only JSONL per session at
``<home>/projects/<workspace-slug>/<session-id>.jsonl`` (industry pattern:
Claude Code project folders + Codex header-record rollouts).

Record types (``t`` discriminator):

    header      first line — full initial Session dump
    meta        {"patch": {...}} later-wins session-field updates
    stats       counter snapshot (counts/tokens/cost/updated_at)
    msg | sync | usage     chronological event rows
    checkpoint  latest-wins restore point
    wsfile      workspace file-state upsert for one path

Resume = read top-to-bottom and fold. A crash mid-append can only lose
the final partial line (skipped on load), never persisted records.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from server.domain.session import Session

from .atomic import append_jsonl_sync, read_jsonl
from .paths import StorageHome

logger = logging.getLogger(__name__)

COUNT_KEYS = (
    "message_count",
    "user_message_count",
    "total_tokens",
    "total_cost",
    "context_percent",
)
# Identity never changes after creation; everything else is patchable
# (callers may legitimately carry updated counters in meta patches).
PATCH_EXCLUDE = {"id", "workspace_root", "t", "v"}

_path_cache: dict[tuple[str, str], Path] = {}


def locate(home: StorageHome, session_id: str) -> Path | None:
    key = (str(home.root), session_id)
    cached = _path_cache.get(key)
    if cached is not None and cached.exists():
        return cached
    try:
        hits = sorted(home.projects_dir.glob(f"*/{session_id}.jsonl"))
    except OSError:
        return None
    if not hits:
        return None
    _path_cache[key] = hits[0]
    return hits[0]


def remember(home: StorageHome, session_id: str, path: Path) -> None:
    _path_cache[(str(home.root), session_id)] = path


def forget(home: StorageHome, session_id: str) -> None:
    _path_cache.pop((str(home.root), session_id), None)


def iter_session_files(home: StorageHome) -> list[Path]:
    """Every session file across all projects, newest-modified first."""

    def _mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0

    try:
        files = [p for p in home.projects_dir.glob("*/*.jsonl") if p.is_file()]
    except OSError:
        return []
    return sorted(files, key=_mtime, reverse=True)


def iter_records(home: StorageHome, session_id: str) -> list[dict]:
    """All records of one session, chronological. Missing file -> []."""
    path = locate(home, session_id)
    if path is None:
        return []
    return read_jsonl(path)


def load_snapshot(home: StorageHome, session_id: str) -> dict | None:
    """Fold a session file into current state; ``None`` when absent.

    Shape: ``{fields, messages, syncs, usage, workspace, checkpoint}``.
    """
    path = locate(home, session_id)
    if path is None:
        return None
    return fold_records(read_jsonl(path), fallback_id=session_id) or None


def fold_records(records: list[dict], *, fallback_id: str | None = None) -> dict | None:
    """Fold chronological records into the session state snapshot."""
    if not records:
        return None

    fields: dict = {}
    snap: dict = {
        "fields": fields,
        "messages": [],
        "syncs": [],
        "usage": [],
        "workspace": {},
        "checkpoint": None,
    }
    for rec in records:
        t = rec.get("t")
        if t == "header":
            fields.update({k: v for k, v in rec.items() if k not in ("t", "v")})
        elif t == "meta":
            patch = rec.get("patch")
            if isinstance(patch, dict):
                fields.update(patch)
        elif t == "stats":
            for key in COUNT_KEYS:
                if key in rec:
                    fields[key] = rec[key]
            if "updated_at" in rec:
                fields["updated_at"] = rec["updated_at"]
        elif t == "msg":
            snap["messages"].append(rec)
        elif t == "sync":
            snap["syncs"].append(rec)
        elif t == "usage":
            snap["usage"].append(rec)
        elif t == "checkpoint":
            snap["checkpoint"] = rec
        elif t == "wsfile":
            ws_path = rec.get("path")
            if ws_path:
                snap["workspace"][str(ws_path)] = {
                    k: v for k, v in rec.items() if k != "t"
                }
    if not fields:
        return None
    if fallback_id:
        fields.setdefault("id", fallback_id)
    return snap


def to_session(fields: dict) -> Session:
    data = {k: v for k, v in fields.items() if k != "user_message_count"}
    return Session(**data)


def append_record(home: StorageHome, session_id: str, record: dict) -> None:
    path = locate(home, session_id)
    if path is None:
        raise ValueError(f"Session {session_id} not found")
    append_jsonl_sync(path, record)


def stats_record(fields: dict, *, bump_user: int = 0, bump_tokens: int = 0,
                 bump_cost: float = 0.0) -> dict:
    now = datetime.now().isoformat()
    return {
        "t": "stats",
        "updated_at": now,
        "message_count": int(fields.get("message_count", 0)) + bump_user,
        "user_message_count": int(fields.get("user_message_count", 0)) + bump_user,
        "total_tokens": float(fields.get("total_tokens", 0)) + bump_tokens,
        "total_cost": round(float(fields.get("total_cost", 0)) + bump_cost, 6),
        "context_percent": float(fields.get("context_percent", 0)),
    }


def tail_or_full_fields(path: Path) -> dict:
    """Fields for listing: cheap head+tail fold, full fold as fallback."""
    fields = _head_tail_fields(path)
    if fields:
        return fields
    try:
        snap = fold_records(read_jsonl(path), fallback_id=path.stem)
    except OSError:
        return {}
    return snap["fields"] if snap else {}


def _fold_field_lines(lines: list[bytes], fields: dict) -> bool:
    """Apply header/meta/stats lines onto ``fields``; True if header seen."""
    import json

    saw_header = False
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        if not isinstance(rec, dict):
            continue
        t = rec.get("t")
        if t == "header":
            fields.update({k: v for k, v in rec.items() if k not in ("t", "v")})
            saw_header = True
        elif t == "meta" and isinstance(rec.get("patch"), dict):
            fields.update(rec["patch"])
        elif t == "stats":
            for key in COUNT_KEYS:
                if key in rec:
                    fields[key] = rec[key]
            if "updated_at" in rec:
                fields["updated_at"] = rec["updated_at"]
    return saw_header


def _head_tail_fields(path: Path, chunk: int = 65_536) -> dict:
    """Identity from the file head, latest state from the tail."""
    try:
        size = path.stat().st_size
        with open(path, "rb") as f:
            head = f.read(chunk)
            if size > chunk:
                f.seek(-chunk, 2)
                tail_data = f.read()
                tail_lines = tail_data.split(b"\n")[1:]  # drop partial first line
            else:
                tail_lines = head.split(b"\n")
    except OSError:
        return {}

    fields: dict = {}
    saw_header = _fold_field_lines(head.split(b"\n"), fields)
    if not saw_header:
        return {}
    _fold_field_lines(tail_lines, fields)
    return fields


def tail_fields(path: Path, chunk: int = 65_536) -> dict:
    """Tail-only fold (legacy helper; listings use _head_tail_fields)."""
    try:
        size = path.stat().st_size
        with open(path, "rb") as f:
            if size > chunk:
                f.seek(-chunk, 2)
                data = f.read()
                lines = data.split(b"\n")[1:]  # drop partial first line
            else:
                data = f.read()
                lines = data.split(b"\n")
    except OSError:
        return {}
    fields: dict = {}
    _fold_field_lines(lines, fields)
    return fields
