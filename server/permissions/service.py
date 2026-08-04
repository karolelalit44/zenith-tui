
from __future__ import annotations
import asyncio
import logging
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field
from server.domain.domain import PermissionDecision, RiskLevel

logger = logging.getLogger(__name__)

PermissionCallback = Callable[["PermissionRequest"], PermissionDecision]


class PermissionRequest(BaseModel):
    pass

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tool_name: str
    description: str
    risk_level: RiskLevel
    params: dict[str, Any] = Field(default_factory=dict)
    session_id: str
    timestamp: datetime = Field(default_factory=datetime.now)


class PermissionGrant(BaseModel):
    pass

    tool_name: str
    decision: PermissionDecision
    expires_at: datetime | None = None
    session_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)


class PermissionService:
    pass

    async def request(self, tool_name: str, description: str, risk_level: RiskLevel, params: dict[str, Any], session_id: str) -> PermissionDecision: ...

    async def grant_persistent(self, tool_name: str, decision: PermissionDecision, session_id: str | None = None) -> None: ...

    async def revoke_persistent(self, tool_name: str, session_id: str | None = None) -> None: ...

    async def get_grants(self, session_id: str) -> list[PermissionGrant]: ...

    async def clear_session(self, session_id: str) -> None: ...

    def set_callback(self, callback: PermissionCallback) -> None: ...

    async def get_decision(self, tool_name: str, session_id: str) -> PermissionDecision | None:
        pass


class DefaultPermissionService(PermissionService):
    pass

    def __init__(self, repo=None) -> None:
        self._grants: list[PermissionGrant] = []
        self._repo = repo
        self._callback: PermissionCallback | None = None
        self._pending: dict[str, asyncio.Future[PermissionDecision]] = {}
        self._load_started = False

    async def _ensure_loaded(self) -> None:
        if self._repo is None or self._load_started:
            return
        self._load_started = True
        try:
            self._grants = await self._repo.load_all()
            logger.info("Loaded %d persisted permission grants", len(self._grants))
        except Exception as e:
            logger.warning("Failed to load persisted permission grants: %s", e)

    async def refresh(self) -> None:
        self._load_started = False
        await self._ensure_loaded()

    def set_callback(self, callback: PermissionCallback) -> None:
        self._callback = callback

    async def get_decision(self, tool_name: str, session_id: str) -> PermissionDecision | None:
        await self._ensure_loaded()
        for grant in self._grants:
            if grant.tool_name != tool_name:
                continue
            if grant.session_id is not None and grant.session_id != session_id:
                continue
            if grant.expires_at and grant.expires_at < datetime.now():
                continue
            return grant.decision
        return None

    async def request(self, tool_name: str, description: str, risk_level: RiskLevel, params: dict[str, Any], session_id: str) -> PermissionDecision:
        await self._ensure_loaded()
        for grant in self._grants:
            if grant.tool_name != tool_name:
                continue
            if grant.session_id is not None and grant.session_id != session_id:
                continue
            if grant.expires_at and grant.expires_at < datetime.now():
                continue
            return grant.decision

        if risk_level == RiskLevel.LOW:
            return PermissionDecision.ALLOW

        req = PermissionRequest(tool_name=tool_name, description=description, risk_level=risk_level, params=params, session_id=session_id)

        if self._callback is None:
            logger.warning("No permission callback set, defaulting to DENY for %s", tool_name)
            return PermissionDecision.DENY

        try:
            decision = self._callback(req)
            if asyncio.iscoroutine(decision):
                decision = await decision
        except Exception:
            logger.exception("Permission callback error")
            return PermissionDecision.DENY

        return decision

    async def grant_persistent(self, tool_name: str, decision: PermissionDecision, session_id: str | None = None) -> None:
        self._grants = [g for g in self._grants if not (g.tool_name == tool_name and g.session_id == session_id)]
        grant = PermissionGrant(tool_name=tool_name, decision=decision, session_id=session_id)
        self._grants.append(grant)
        logger.info("Persistent grant: %s → %s (session=%s)", tool_name, decision.value, session_id)
        if self._repo is not None:
            try:
                await self._repo.save(grant)
            except Exception as e:
                logger.warning("Failed to persist permission grant: %s", e)

    async def revoke_persistent(self, tool_name: str, session_id: str | None = None) -> None:
        self._grants = [g for g in self._grants if not (g.tool_name == tool_name and g.session_id == session_id)]
        if self._repo is not None:
            try:
                await self._repo.revoke(tool_name, session_id)
            except Exception as e:
                logger.warning("Failed to revoke persisted permission: %s", e)

    async def get_grants(self, session_id: str) -> list[PermissionGrant]:
        await self._ensure_loaded()
        return [g for g in self._grants if g.session_id is None or g.session_id == session_id]

    async def clear_session(self, session_id: str) -> None:
        self._grants = [g for g in self._grants if g.session_id != session_id]
        if self._repo is not None:
            try:
                await self._repo.clear_session(session_id)
            except Exception as e:
                logger.warning("Failed to clear persisted permissions: %s", e)
