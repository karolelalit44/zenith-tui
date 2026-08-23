"""File-backed project memory (cross-session key-value store per workspace).

Replaces ``ProjectMemoryRepository`` (project_memory table). Entries live in
``memory/index.json``; the human-readable facts remain in the markdown
MemoryStore files, which stay canonical (decision D16).
"""

from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass
from datetime import datetime

from .atomic import read_json, write_json_atomic
from .paths import StorageHome

MAX_PROJECT_MEMORY_ENTRIES = 20


@dataclass
class ProjectMemoryEntry:
    id: str
    workspace_root: str
    key: str
    value: str
    created_at: str
    updated_at: str


def _read_doc(home: StorageHome) -> dict:
    doc = read_json(home.memory_index_path, None)
    if isinstance(doc, dict) and isinstance(doc.get("workspaces"), dict):
        return doc
    return {"version": 1, "workspaces": {}}


def _write_doc(home: StorageHome, doc: dict) -> None:
    write_json_atomic(home.memory_index_path, doc)


def _entries_for(doc: dict, workspace_root: str) -> list[dict]:
    bucket = doc["workspaces"].setdefault(workspace_root, {})
    entries = bucket.get("entries")
    if not isinstance(entries, list):
        entries = []
        bucket["entries"] = entries
    return entries


def _to_entry(raw: dict, workspace_root: str) -> ProjectMemoryEntry:
    return ProjectMemoryEntry(
        id=str(raw.get("id", "")),
        workspace_root=workspace_root,
        key=str(raw.get("key", "")),
        value=str(raw.get("value", "")),
        created_at=str(raw.get("created_at", "")),
        updated_at=str(raw.get("updated_at", "")),
    )


class FileProjectMemoryRepository:
    def __init__(self, home: StorageHome):
        self.home = home

    async def get_all(self, workspace_root: str) -> list[ProjectMemoryEntry]:
        async with self.home.lock:
            doc = _read_doc(self.home)
            raw = sorted(
                _entries_for(doc, workspace_root),
                key=lambda e: str(e.get("updated_at", "")),
                reverse=True,
            )
        return [_to_entry(e, workspace_root) for e in raw]

    async def get_value(self, workspace_root: str, key: str) -> str | None:
        async with self.home.lock:
            doc = _read_doc(self.home)
            for e in _entries_for(doc, workspace_root):
                if e.get("key") == key:
                    return str(e.get("value", ""))
        return None

    async def upsert(self, workspace_root: str, key: str, value: str) -> ProjectMemoryEntry:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        async with self.home.lock:
            doc = _read_doc(self.home)
            entries = _entries_for(doc, workspace_root)
            target = next((e for e in entries if e.get("key") == key), None)
            if target is not None:
                target["value"] = value
                target["updated_at"] = now
                entry_id = str(target.get("id", ""))
                created = str(target.get("created_at", now))
            else:
                if len(entries) >= MAX_PROJECT_MEMORY_ENTRIES:
                    oldest = min(entries, key=lambda e: str(e.get("updated_at", "")))
                    entries.remove(oldest)
                entry_id = str(_uuid.uuid4())
                created = now
                entries.append(
                    {"id": entry_id, "key": key, "value": value,
                     "created_at": created, "updated_at": now}
                )
            _write_doc(self.home, doc)
        return ProjectMemoryEntry(
            id=entry_id,
            workspace_root=workspace_root,
            key=key,
            value=value,
            created_at=created,
            updated_at=now,
        )

    async def delete(self, workspace_root: str, key: str) -> bool:
        async with self.home.lock:
            doc = _read_doc(self.home)
            entries = _entries_for(doc, workspace_root)
            remaining = [e for e in entries if e.get("key") != key]
            if len(remaining) == len(entries):
                return False
            doc["workspaces"][workspace_root]["entries"] = remaining
            _write_doc(self.home, doc)
            return True

    async def delete_workspace(self, workspace_root: str) -> int:
        async with self.home.lock:
            doc = _read_doc(self.home)
            removed = len(_entries_for(doc, workspace_root))
            doc["workspaces"].pop(workspace_root, None)
            _write_doc(self.home, doc)
            return removed
