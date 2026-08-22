"""Project memory repository — cross-session key-value memory per workspace."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, delete as sa_delete

from ..connection import Database
from ..models import ProjectMemoryRecord
from ..safe import safe_db

logger = logging.getLogger(__name__)

MAX_PROJECT_MEMORY_ENTRIES = 20


class ProjectMemoryRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    @safe_db("get_all_project_memory", table="project_memory")
    async def get_all(self, workspace_root: str) -> list[ProjectMemoryRecord]:
        async with self.db.session() as s:
            stmt = (
                select(ProjectMemoryRecord)
                .where(ProjectMemoryRecord.workspace_root == workspace_root)
                .order_by(ProjectMemoryRecord.updated_at.desc())
            )
            result = await s.execute(stmt)
            return list(result.scalars().all())

    @safe_db("get_project_memory_value", table="project_memory")
    async def get_value(self, workspace_root: str, key: str) -> str | None:
        async with self.db.session() as s:
            stmt = select(ProjectMemoryRecord).where(
                ProjectMemoryRecord.workspace_root == workspace_root,
                ProjectMemoryRecord.key == key,
            )
            result = await s.execute(stmt)
            record = result.scalar_one_or_none()
            return record.value if record else None

    @safe_db("upsert_project_memory", table="project_memory")
    async def upsert(self, workspace_root: str, key: str, value: str) -> ProjectMemoryRecord:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        async with self.db.session() as s:
            stmt = select(ProjectMemoryRecord).where(
                ProjectMemoryRecord.workspace_root == workspace_root,
                ProjectMemoryRecord.key == key,
            )
            result = await s.execute(stmt)
            record = result.scalar_one_or_none()
            if record:
                record.value = value
                record.updated_at = now
            else:
                count_stmt = select(ProjectMemoryRecord).where(
                    ProjectMemoryRecord.workspace_root == workspace_root,
                )
                count_result = await s.execute(count_stmt)
                existing = list(count_result.scalars().all())
                if len(existing) >= MAX_PROJECT_MEMORY_ENTRIES:
                    oldest = min(existing, key=lambda r: r.updated_at)
                    await s.delete(oldest)
                    await s.flush()
                record = ProjectMemoryRecord(
                    id=str(uuid.uuid4()),
                    workspace_root=workspace_root,
                    key=key,
                    value=value,
                    created_at=now,
                    updated_at=now,
                )
                s.add(record)
            await s.commit()
            return record

    @safe_db("delete_project_memory", table="project_memory")
    async def delete(self, workspace_root: str, key: str) -> bool:
        async with self.db.session() as s:
            stmt = select(ProjectMemoryRecord).where(
                ProjectMemoryRecord.workspace_root == workspace_root,
                ProjectMemoryRecord.key == key,
            )
            result = await s.execute(stmt)
            record = result.scalar_one_or_none()
            if not record:
                return False
            await s.delete(record)
            await s.commit()
            return True

    @safe_db("delete_workspace_project_memory", table="project_memory")
    async def delete_workspace(self, workspace_root: str) -> int:
        async with self.db.session() as s:
            stmt = sa_delete(ProjectMemoryRecord).where(
                ProjectMemoryRecord.workspace_root == workspace_root
            )
            result = await s.execute(stmt)
            await s.commit()
            return result.rowcount  # type: ignore[return-value]
