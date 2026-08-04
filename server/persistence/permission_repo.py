from __future__ import annotations

import logging
import uuid
from datetime import datetime

from sqlalchemy import delete, select

from server.domain.domain import PermissionDecision
from server.permissions.service import PermissionGrant
from server.persistence.models import PermissionRecord

logger = logging.getLogger(__name__)


class PermissionRepository:
    def __init__(self, db) -> None:
        self.db = db

    async def load_all(self) -> list[PermissionGrant]:
        async with self.db.session() as s:
            rows = (await s.execute(select(PermissionRecord))).scalars().all()
        return [self._row_to_grant(r) for r in rows]

    async def save(self, grant: PermissionGrant) -> None:
        async with self.db.session() as s:
            s.add(
                PermissionRecord(
                    id=str(uuid.uuid4()),
                    tool_name=grant.tool_name,
                    decision=(
                        grant.decision.value
                        if hasattr(grant.decision, "value")
                        else str(grant.decision)
                    ),
                    session_id=grant.session_id,
                    expires_at=grant.expires_at.isoformat() if grant.expires_at else None,
                    created_at=grant.created_at.isoformat(),
                )
            )
            await s.commit()

    async def revoke(self, tool_name: str, session_id: str | None = None) -> None:
        async with self.db.session() as s:
            stmt = delete(PermissionRecord).where(PermissionRecord.tool_name == tool_name)
            if session_id is not None:
                stmt = stmt.where(PermissionRecord.session_id == session_id)
            await s.execute(stmt)
            await s.commit()

    async def clear_session(self, session_id: str) -> None:
        async with self.db.session() as s:
            await s.execute(
                delete(PermissionRecord).where(PermissionRecord.session_id == session_id)
            )
            await s.commit()

    def _row_to_grant(self, row: PermissionRecord) -> PermissionGrant:
        return PermissionGrant(
            tool_name=row.tool_name,
            decision=PermissionDecision(row.decision),
            session_id=row.session_id,
            expires_at=datetime.fromisoformat(row.expires_at) if row.expires_at else None,
            created_at=datetime.fromisoformat(row.created_at),
        )
