"""Permission store — manages tool approval persistence."""

from __future__ import annotations

import logging
from datetime import datetime

from zenith.db.connection import Database

logger = logging.getLogger(__name__)


class PermissionStore:
    """Stores and retrieves tool permissions from SQLite."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def is_approved(self, tool_name: str, pattern: str = "*") -> bool:
        """Check if a tool is approved."""
        row = await self.db.fetch_one(
            "SELECT approved FROM tool_permissions WHERE tool_name = ? AND pattern = ?",
            (tool_name, pattern),
        )
        if row:
            return bool(row["approved"])

        row_default = await self.db.fetch_one(
            "SELECT approved FROM tool_permissions WHERE tool_name = ? AND pattern = '*'",
            (tool_name,),
        )
        return bool(row_default["approved"]) if row_default else False

    async def approve(self, tool_name: str, pattern: str = "*") -> None:
        """Approve a tool."""
        now = datetime.now().isoformat()
        await self.db.execute(
            """INSERT INTO tool_permissions (tool_name, pattern, approved, created_at, updated_at)
            VALUES (?, ?, 1, ?, ?)
            ON CONFLICT(tool_name, pattern) DO UPDATE SET approved = 1, updated_at = ?""",
            (tool_name, pattern, now, now, now),
        )
        await self.db.commit()
        logger.info("Approved tool: %s (pattern=%s)", tool_name, pattern)

    async def deny(self, tool_name: str, pattern: str = "*") -> None:
        """Deny a tool."""
        now = datetime.now().isoformat()
        await self.db.execute(
            """INSERT INTO tool_permissions (tool_name, pattern, approved, created_at, updated_at)
            VALUES (?, ?, 0, ?, ?)
            ON CONFLICT(tool_name, pattern) DO UPDATE SET approved = 0, updated_at = ?""",
            (tool_name, pattern, now, now, now),
        )
        await self.db.commit()
        logger.info("Denied tool: %s (pattern=%s)", tool_name, pattern)

    async def revoke(self, tool_name: str, pattern: str = "*") -> None:
        """Revoke a permission entry."""
        await self.db.execute(
            "DELETE FROM tool_permissions WHERE tool_name = ? AND pattern = ?",
            (tool_name, pattern),
        )
        await self.db.commit()
        logger.info("Revoked permission: %s (pattern=%s)", tool_name, pattern)

    async def list_approved(self) -> list[dict]:
        """List all approved permissions."""
        rows = await self.db.fetch_all(
            "SELECT tool_name, pattern, approved, created_at FROM tool_permissions WHERE approved = 1"
        )
        return [dict(r) for r in rows]

    async def list_all(self) -> list[dict]:
        """List all permission entries."""
        rows = await self.db.fetch_all(
            "SELECT tool_name, pattern, approved, created_at FROM tool_permissions"
        )
        return [dict(r) for r in rows]

    async def clear_all(self) -> None:
        """Clear all permission entries."""
        await self.db.execute("DELETE FROM tool_permissions")
        await self.db.commit()
        logger.info("Cleared all tool permissions")
