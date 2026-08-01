"""Permission service — request/grant/deny lifecycle for tool execution.

Following Crush's permission model:
- Request → Grant/Deny → Persistent grant (remembered for session)
- Hook pre-approval integration
- Session-scoped and global grants
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from core.domain import PermissionDecision, RiskLevel

logger = logging.getLogger(__name__)

# Callback type for permission confirmation: (request) -> PermissionDecision
PermissionCallback = Callable[["PermissionRequest"], PermissionDecision]


class PermissionRequest(BaseModel):
    """A pending permission request."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tool_name: str
    description: str
    risk_level: RiskLevel
    params: dict[str, Any] = Field(default_factory=dict)
    session_id: str
    timestamp: datetime = Field(default_factory=datetime.now)


class PermissionGrant(BaseModel):
    """A stored permission grant."""
    tool_name: str
    decision: PermissionDecision
    expires_at: datetime | None = None
    session_id: str | None = None  # None = global
    created_at: datetime = Field(default_factory=datetime.now)


class PermissionService:
    """Abstract permission service interface."""

    async def request(
        self,
        tool_name: str,
        description: str,
        risk_level: RiskLevel,
        params: dict[str, Any],
        session_id: str,
    ) -> PermissionDecision:
        ...

    def grant_persistent(
        self,
        tool_name: str,
        decision: PermissionDecision,
        session_id: str | None = None,
    ) -> None:
        ...

    def revoke_persistent(self, tool_name: str) -> None:
        ...

    def get_grants(self, session_id: str) -> list[PermissionGrant]:
        ...

    def clear_session(self, session_id: str) -> None:
        ...

    def set_callback(self, callback: PermissionCallback) -> None:
        ...


class DefaultPermissionService(PermissionService):
    """In-memory permission service with callback-based confirmation.

    When a tool requires permission:
    1. Check existing persistent grants
    2. If no grant, create a PermissionRequest
    3. Invoke the callback (which may show a confirmation UI)
    4. Optionally store as persistent grant
    """

    def __init__(self) -> None:
        self._grants: list[PermissionGrant] = []
        self._callback: PermissionCallback | None = None
        self._pending: dict[str, asyncio.Future[PermissionDecision]] = {}

    def set_callback(self, callback: PermissionCallback) -> None:
        self._callback = callback

    async def request(
        self,
        tool_name: str,
        description: str,
        risk_level: RiskLevel,
        params: dict[str, Any],
        session_id: str,
    ) -> PermissionDecision:
        # 1. Check existing grants
        for grant in self._grants:
            if grant.tool_name != tool_name:
                continue
            # Check session match (None = global grant)
            if grant.session_id is not None and grant.session_id != session_id:
                continue
            # Check expiry
            if grant.expires_at and grant.expires_at < datetime.now():
                continue
            return grant.decision

        # 2. No existing grant — request permission
        if risk_level == RiskLevel.LOW:
            return PermissionDecision.ALLOW

        req = PermissionRequest(
            tool_name=tool_name,
            description=description,
            risk_level=risk_level,
            params=params,
            session_id=session_id,
        )

        # 3. Invoke callback
        if self._callback is None:
            logger.warning("No permission callback set, defaulting to DENY for %s", tool_name)
            return PermissionDecision.DENY

        try:
            decision = self._callback(req)
            if asyncio.iscoroutine(decision):
                decision = await decision
        except Exception as e:
            logger.exception("Permission callback error: %s", e)
            return PermissionDecision.DENY

        return decision

    def grant_persistent(
        self,
        tool_name: str,
        decision: PermissionDecision,
        session_id: str | None = None,
    ) -> None:
        # Remove existing grant for this tool+session
        self._grants = [
            g for g in self._grants
            if not (g.tool_name == tool_name and g.session_id == session_id)
        ]
        self._grants.append(PermissionGrant(
            tool_name=tool_name,
            decision=decision,
            session_id=session_id,
        ))
        logger.info("Persistent grant: %s → %s (session=%s)", tool_name, decision.value, session_id)

    def revoke_persistent(self, tool_name: str) -> None:
        self._grants = [g for g in self._grants if g.tool_name != tool_name]

    def get_grants(self, session_id: str) -> list[PermissionGrant]:
        return [
            g for g in self._grants
            if g.session_id is None or g.session_id == session_id
        ]

    def clear_session(self, session_id: str) -> None:
        self._grants = [g for g in self._grants if g.session_id != session_id]
