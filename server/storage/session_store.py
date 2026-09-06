"""File-backed session/message/checkpoint/sync-event repositories.

All state lives in ONE append-only JSONL per session (see
``session_file`` for the record format). Repository APIs are unchanged
from the previous per-session-directory design; only the on-disk model
changed.
"""

from __future__ import annotations

import asyncio
import logging
import uuid as _uuid
from datetime import datetime

from server.domain.events import Event, EventKind
from server.domain.message import Message
from server.domain.session import Session

from .atomic import append_jsonl_sync, read_jsonl, rewrite_jsonl_atomic
from .paths import StorageHome
from .session_file import (
    PATCH_EXCLUDE,
    append_record,
    forget,
    iter_session_files,
    load_snapshot,
    locate,
    remember,
    stats_record,
    to_session,
)

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now().isoformat()


def _require_fields(home: StorageHome, session_id: str) -> dict:
    snap = load_snapshot(home, session_id)
    if snap is None:
        raise ValueError(f"Session {session_id} not found")
    return snap["fields"]


# ── sessions ──────────────────────────────────────────────────────────


class FileSessionRepository:
    def __init__(self, home: StorageHome):
        self.home = home

    async def create(self, session: Session) -> Session:
        async with self.home.lock:
            directory = self.home.project_dir(session.workspace_root)
            directory.mkdir(parents=True, exist_ok=True)
            path = self.home.session_file(session.id, session.workspace_root)
            header = {"t": "header", "v": 1, **session.model_dump(mode="json")}
            seed_stats = stats_record(session.model_dump(mode="json"))
            rewrite_jsonl_atomic(path, [header, seed_stats])
            remember(self.home, session.id, path)
        return session

    async def get(self, session_id: str) -> Session | None:
        snap = await asyncio.to_thread(load_snapshot, self.home, session_id)
        return to_session(snap["fields"]) if snap else None

    async def set_model(self, session_id: str, model: str | None) -> bool:
        async with self.home.lock:
            if locate(self.home, session_id) is None:
                return False
            append_jsonl_sync(
                locate(self.home, session_id),  # type: ignore[arg-type]
                {"t": "meta", "patch": {"model": model, "updated_at": _now()}},
            )
            return True

    async def merge_metadata(self, session_id: str, updates: dict) -> dict | None:
        if not updates:
            return await self.get_metadata(session_id)
        async with self.home.lock:
            fields = _require_fields(self.home, session_id)
            current = fields.get("metadata")
            merged = dict(current) if isinstance(current, dict) else {}
            merged.update(updates)
            append_jsonl_sync(
                locate(self.home, session_id),  # type: ignore[arg-type]
                {"t": "meta", "patch": {"metadata": merged, "updated_at": _now()}},
            )
            return merged

    async def get_metadata(self, session_id: str) -> dict | None:
        snap = await asyncio.to_thread(load_snapshot, self.home, session_id)
        if snap is None:
            return None
        md = snap["fields"].get("metadata")
        return md if isinstance(md, dict) else {}

    async def list_active(self) -> list[Session]:
        return await self.list_all(include_archived=False, limit=10_000)

    async def list_all(
        self,
        limit: int = 50,
        offset: int = 0,
        include_archived: bool = False,
        search: str | None = None,
        state_filter: str | None = None,
    ) -> list[Session]:
        rows = await asyncio.to_thread(self._collect_field_rows)
        needle = search.lower() if search else None
        out: list[Session] = []
        for fields in rows:
            if not include_archived and not fields.get("is_active", True):
                continue
            if state_filter and fields.get("run_status") != state_filter:
                continue
            if needle and needle not in str(fields.get("title", "")).lower():
                continue
            out.append(to_session(fields))
        out.sort(key=lambda s: s.updated_at.isoformat(), reverse=True)
        return out[offset : offset + limit]

    def _collect_field_rows(self) -> list[dict]:
        from .session_file import tail_or_full_fields

        rows: list[dict] = []
        for path in iter_session_files(self.home):
            fields = tail_or_full_fields(path)
            if fields:
                rows.append(fields)
        return rows

    async def get_summaries(self, limit: int = 10, include_archived: bool = False) -> list[dict]:
        rows = await asyncio.to_thread(FileSessionRepository._summaries_sync, self.home)
        filtered = []
        for r in rows:
            if not include_archived and not r.get("is_active", True):
                continue
            effective = int(r.get("user_message_count", 0)) or int(r.get("message_count", 0))
            if effective <= 0 and int(r.get("total_tokens", 0)) <= 0:
                continue
            filtered.append(r)
        filtered.sort(key=lambda r: str(r["updated_at"]), reverse=True)
        return filtered[:limit]

    @staticmethod
    def _summaries_sync(home: StorageHome) -> list[dict]:
        from .session_file import tail_or_full_fields

        rows: list[dict] = []
        for path in iter_session_files(home):
            fields = tail_or_full_fields(path)
            if not fields:
                continue
            rows.append(
                {
                    "id": fields.get("id") or path.stem,
                    "title": fields.get("title", ""),
                    "mode": fields.get("mode", ""),
                    "status": fields.get("run_status", "idle"),
                    "provider": fields.get("provider"),
                    "model": fields.get("model"),
                    "message_count": int(fields.get("user_message_count", 0))
                    or int(fields.get("message_count", 0)),
                    "total_tokens": int(float(fields.get("total_tokens", 0))),
                    "total_cost": float(fields.get("total_cost", 0)),
                    "context_percent": float(fields.get("context_percent", 0)),
                    "created_at": fields.get("created_at", ""),
                    "updated_at": fields.get("updated_at", ""),
                    "is_active": bool(fields.get("is_active", True)),
                    "error_count": int(fields.get("error_count", 0)),
                    "last_error": fields.get("last_error"),
                    "parent_session_id": fields.get("parent_session_id"),
                }
            )
        return rows

    async def update(self, session: Session) -> Session:
        async with self.home.lock:
            patch = {
                k: v for k, v in session.model_dump(mode="json").items() if k not in PATCH_EXCLUDE
            }
            patch["updated_at"] = _now()
            append_record(self.home, session.id, {"t": "meta", "patch": patch})
        return session

    async def find_latest_with_plan(self) -> Session | None:
        for path in iter_session_files(self.home):
            sid = path.stem
            snap = await asyncio.to_thread(load_snapshot, self.home, sid)
            if snap is None:
                continue
            fields = snap["fields"]
            if fields.get("plan_output") and fields.get("is_active", True):
                return to_session(fields)
        return None

    async def delete(self, session_id: str) -> bool:
        async with self.home.lock:
            path = locate(self.home, session_id)
            existed = path is not None and path.exists()
            if existed:
                try:
                    path.unlink()  # type: ignore[union-attr]
                except OSError as exc:
                    logger.warning("Could not delete session file %s: %s", path, exc)
            forget(self.home, session_id)
        return existed

    async def add_tokens(self, session_id: str, tokens: int, cost: float = 0.0) -> Session | None:
        # Serialized RMW of the counter snapshot so concurrent updates
        # cannot lose increments.
        async with self.home.lock:
            fields = await asyncio.to_thread(_require_fields_safe, self.home, session_id)
            if fields is None:
                return None
            stats = stats_record(fields, bump_tokens=tokens, bump_cost=cost)
            append_jsonl_sync(locate(self.home, session_id), stats)  # type: ignore[arg-type]
            merged = dict(fields)
            for key in (
                "message_count",
                "user_message_count",
                "total_tokens",
                "total_cost",
                "context_percent",
            ):
                merged[key] = stats[key]
            merged["updated_at"] = stats["updated_at"]
        return to_session(merged)

    list = list_all  # alias kept from the DB repository


def _require_fields_safe(home: StorageHome, session_id: str) -> dict | None:
    snap = load_snapshot(home, session_id)
    return snap["fields"] if snap else None


# ── messages ──────────────────────────────────────────────────────────


class FileMessageRepository:
    def __init__(self, home: StorageHome):
        self.home = home

    @staticmethod
    def _to_line(message: Message) -> dict:
        d = message.model_dump(mode="json")
        d["t"] = "msg"
        return d

    @staticmethod
    def _from_line(rec: dict) -> Message:
        data = {k: v for k, v in rec.items() if k != "t"}
        events = data.pop("events", None) or []
        return Message(**data, events=[Event(**e) for e in events])

    async def create(self, message: Message) -> Message:
        async with self.home.lock:
            fields = _require_fields(self.home, message.session_id)
            path = locate(self.home, message.session_id)
            assert path is not None
            append_jsonl_sync(path, self._to_line(message))
            bump = 1 if message.role == "user" else 0
            append_jsonl_sync(path, stats_record(fields, bump_user=bump))
        return message

    append = create


    async def get_by_session(self, session_id: str, limit: int = 50) -> list[Message]:
        snap = await asyncio.to_thread(load_snapshot, self.home, session_id)
        if snap is None:
            return []
        lines = snap["messages"]
        selected = lines[-limit:] if limit else lines
        return [self._from_line(r) for r in selected]

    async def count_tokens(self, session_id: str) -> int:
        snap = await asyncio.to_thread(load_snapshot, self.home, session_id)
        if snap is None:
            return 0
        return sum(int(r.get("token_count", 0)) for r in snap["messages"])


    async def compact_history(self, session_id: str, metadata: dict, delete_ids: list[str]) -> int:
        doomed = set(delete_ids or [])
        async with self.home.lock:
            path = locate(self.home, session_id)
            if path is None:
                return 0
            records = read_jsonl(path)
            fields: dict = {}
            from .session_file import COUNT_KEYS

            for r in records:
                t = r.get("t")
                if t == "header":
                    fields.update({k: v for k, v in r.items() if k not in ("t", "v")})
                elif t == "meta" and isinstance(r.get("patch"), dict):
                    fields.update(r["patch"])
                elif t == "stats":
                    for key in COUNT_KEYS:
                        if key in r:
                            fields[key] = r[key]
            meta_count = int(fields.get("message_count", 0))
            msg_records = [r for r in records if r.get("t") == "msg"]
            if not msg_records and meta_count > 0:
                logger.error(
                    "compaction aborted for session %s: no message records while "
                    "stats report %s message(s)",
                    session_id,
                    meta_count,
                )
                return 0
            kept: list[dict] = []
            deleted = 0
            for rec in records:
                if rec.get("t") == "msg" and rec.get("id") in doomed:
                    deleted += 1
                    continue
                kept.append(rec)
            if deleted or metadata is not None:
                kept.append({"t": "meta", "patch": {"metadata": metadata, "updated_at": _now()}})
                user_left = sum(1 for r in kept if r.get("t") == "msg" and r.get("role") == "user")
                base = dict(fields)
                base["message_count"] = user_left
                base["user_message_count"] = user_left
                kept.append(stats_record(base))
            rewrite_jsonl_atomic(path, kept)
        return deleted

    async def delete_tool_results(self, session_id: str) -> int:
        async with self.home.lock:
            path = locate(self.home, session_id)
            if path is None:
                return 0
            records = read_jsonl(path)
            kept = [r for r in records if not (r.get("t") == "msg" and r.get("role") == "tool")]
            deleted = len(records) - len(kept)
            if deleted:
                rewrite_jsonl_atomic(path, kept)
        return deleted

    async def strip_tool_events(self, session_id: str) -> int:
        tool_result_kind = EventKind.TOOL_RESULT.value
        async with self.home.lock:
            path = locate(self.home, session_id)
            if path is None:
                return 0
            records = read_jsonl(path)
            touched = 0
            kept: list[dict] = []
            for rec in records:
                if rec.get("t") == "msg":
                    events = rec.get("events") or []
                    filtered = [e for e in events if e.get("kind") != tool_result_kind]
                    if len(filtered) != len(events):
                        rec = dict(rec)
                        rec["events"] = filtered
                        touched += 1
                kept.append(rec)
            if touched:
                rewrite_jsonl_atomic(path, kept)
        return touched


# ── checkpoints (latest-wins record inside the same file) ─────────────


class FileCheckpointRepository:
    def __init__(self, home: StorageHome):
        self.home = home

    async def create(
        self,
        session_id: str,
        checkpoint_type: str = "automatic",
        step_index: int = 0,
        snapshot_data: dict | None = None,
        token_count: int = 0,
        message_count: int = 0,
    ) -> str:
        cid = str(_uuid.uuid4())
        record = {
            "t": "checkpoint",
            "id": cid,
            "checkpoint_type": checkpoint_type,
            "step_index": step_index,
            "snapshot_data": snapshot_data or {},
            "token_count": token_count,
            "message_count": message_count,
            "created_at": _now(),
        }
        async with self.home.lock:
            append_record(self.home, session_id, record)
        return cid

    async def get_latest(self, session_id: str) -> dict | None:
        snap = await asyncio.to_thread(load_snapshot, self.home, session_id)
        cp = snap["checkpoint"] if snap else None
        return dict(cp) if isinstance(cp, dict) else None


# ── sync events ───────────────────────────────────────────────────────


class FileSyncEventRepository:
    def __init__(self, home: StorageHome):
        self.home = home

    @staticmethod
    def _from_line(rec: dict) -> dict:
        return {
            "id": rec.get("id"),
            "session_id": rec.get("session_id"),
            "event_type": rec.get("event_type"),
            "event_data": rec.get("event_data") or {},
            "sequence": int(rec.get("sequence", 0)),
            "created_at": rec.get("created_at"),
        }

    def _next_sequence_locked(self, session_id: str) -> int:
        seqs = [int(r.get("sequence", 0)) for r in load_snapshot_sync_syncs(self.home, session_id)]
        return (max(seqs) if seqs else 0) + 1

    async def record(
        self,
        session_id: str,
        event_type: str,
        event_data: dict,
        sequence: int | None = None,
        created_at: str | None = None,
    ) -> str:
        eid = str(_uuid.uuid4())
        async with self.home.lock:
            seq = sequence if sequence is not None else self._next_sequence_locked(session_id)
            append_jsonl_sync(
                locate(self.home, session_id),  # type: ignore[arg-type]
                {
                    "t": "sync",
                    "id": eid,
                    "session_id": session_id,
                    "event_type": event_type,
                    "event_data": event_data or {},
                    "sequence": seq,
                    "created_at": created_at or _now(),
                },
            )
        return eid

    async def get_since(self, session_id: str, sequence: int = 0) -> list[dict]:
        snap = await asyncio.to_thread(load_snapshot, self.home, session_id)
        syncs = snap["syncs"] if snap else []
        rows = [self._from_line(r) for r in syncs if int(r.get("sequence", 0)) > sequence]
        rows.sort(key=lambda d: d["sequence"])
        return rows

    async def get_latest_sequence(self, session_id: str) -> int:
        snap = await asyncio.to_thread(load_snapshot, self.home, session_id)
        syncs = snap["syncs"] if snap else []
        seqs = [int(r.get("sequence", 0)) for r in syncs]
        return max(seqs) if seqs else 0

    async def delete_by_session(self, session_id: str) -> None:
        async with self.home.lock:
            path = locate(self.home, session_id)
            if path is None:
                return
            records = read_jsonl(path)
            if not records:
                return
            kept = [r for r in records if r.get("t") != "sync"]
            if len(kept) != len(records):
                rewrite_jsonl_atomic(path, kept)


def load_snapshot_sync_syncs(home: StorageHome, session_id: str) -> list[dict]:
    snap = load_snapshot(home, session_id)
    return snap["syncs"] if snap else []
