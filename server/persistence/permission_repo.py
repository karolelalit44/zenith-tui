from __future__ import annotations

import logging
import uuid
from datetime import datetime

from server.domain.domain import PermissionDecision
from server.permissions.service import PermissionGrant

logger = logging.getLogger(__name__)


class PermissionRepository:
    def __init__(self, db) -> None:
        self.db = db

    async def load_all(self) -> list[PermissionGrant]:
        rows = await self.db.fetch_all("SELECT * FROM permissions")
        return [self._row_to_grant(r) for r in rows]

    async def save(self, grant: PermissionGrant) -> None:
        await self.db.execute(
            "INSERT INTO permissions (id, tool_name, decision, session_id, expires_at, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                grant.tool_name,
                grant.decision.value if hasattr(grant.decision, "value") else str(grant.decision),
                grant.session_id,
                grant.expires_at.isoformat() if grant.expires_at else None,
                grant.created_at.isoformat(),
            ),
        )
        await self.db.commit()

    async def revoke(self, tool_name: str, session_id: str | None = None) -> None:
        if session_id is None:
            await self.db.execute("DELETE FROM permissions WHERE tool_name = ?", (tool_name,))
        else:
            await self.db.execute(
                "DELETE FROM permissions WHERE tool_name = ? AND session_id = ?",
                (tool_name, session_id),
            )
        await self.db.commit()

    async def clear_session(self, session_id: str) -> None:
        await self.db.execute("DELETE FROM permissions WHERE session_id = ?", (session_id,))
        await self.db.commit()

    def _row_to_grant(self, row: dict) -> PermissionGrant:
        return PermissionGrant(
            tool_name=row["tool_name"],
            decision=PermissionDecision(row["decision"]),
            session_id=row.get("session_id"),
            expires_at=datetime.fromisoformat(row["expires_at"]) if row.get("expires_at") else None,
            created_at=datetime.fromisoformat(row["created_at"]),
        )
