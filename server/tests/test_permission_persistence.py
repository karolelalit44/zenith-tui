"""Tests for HP-8 — persistent permission decisions + middleware wiring."""

from __future__ import annotations

import pytest

from server.domain.domain import PermissionDecision, RiskLevel
from server.permissions.service import DefaultPermissionService, PermissionGrant
from server.persistence.connection import Database
from server.persistence.permission_repo import PermissionRepository
from server.toolkit import create_default_registry
from server.toolkit.base import ToolContext, ToolResult
from server.toolkit.middleware import PermissionMiddleware, SafetyCheckMiddleware


class TestPermissionRepository:
    @pytest.mark.asyncio
    async def test_save_and_load_roundtrip(self, temp_dir):
        db = Database(str(temp_dir / "test.db"))
        await db.connect()
        try:
            repo = PermissionRepository(db)
            await repo.save(
                PermissionGrant(tool_name="bash", decision=PermissionDecision.DENY, session_id=None)
            )
            grants = await repo.load_all()
            assert len(grants) == 1
            assert grants[0].tool_name == "bash"
            assert grants[0].decision == PermissionDecision.DENY
            assert grants[0].session_id is None
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_session_scoped_and_global(self, temp_dir):
        db = Database(str(temp_dir / "test.db"))
        await db.connect()
        try:
            repo = PermissionRepository(db)
            await repo.save(
                PermissionGrant(
                    tool_name="file_write", decision=PermissionDecision.DENY, session_id="s1"
                )
            )
            await repo.save(
                PermissionGrant(
                    tool_name="file_delete", decision=PermissionDecision.ALLOW, session_id=None
                )
            )
            grants = await repo.load_all()
            assert len(grants) == 2
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_revoke(self, temp_dir):
        db = Database(str(temp_dir / "test.db"))
        await db.connect()
        try:
            repo = PermissionRepository(db)
            await repo.save(
                PermissionGrant(tool_name="bash", decision=PermissionDecision.DENY, session_id="s1")
            )
            await repo.save(
                PermissionGrant(tool_name="bash", decision=PermissionDecision.DENY, session_id=None)
            )
            await repo.revoke("bash", "s1")
            grants = await repo.load_all()
            assert len(grants) == 1
            assert grants[0].session_id is None
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_clear_session(self, temp_dir):
        db = Database(str(temp_dir / "test.db"))
        await db.connect()
        try:
            repo = PermissionRepository(db)
            await repo.save(
                PermissionGrant(tool_name="bash", decision=PermissionDecision.DENY, session_id="s1")
            )
            await repo.save(
                PermissionGrant(tool_name="bash", decision=PermissionDecision.DENY, session_id="s2")
            )
            await repo.clear_session("s1")
            grants = await repo.load_all()
            assert len(grants) == 1
            assert grants[0].session_id == "s2"
        finally:
            await db.close()


class TestDefaultPermissionServicePersistence:
    @pytest.mark.asyncio
    async def test_deny_persists_across_service_instances(self, temp_dir):
        """A deny rule survives a restart (new service instance) and is applied
        without any UI round-trip (no callback set)."""
        db = Database(str(temp_dir / "test.db"))
        await db.connect()
        try:
            repo = PermissionRepository(db)
            svc1 = DefaultPermissionService(repo=repo)
            await svc1.grant_persistent("file_delete", PermissionDecision.DENY)

            svc2 = DefaultPermissionService(repo=repo)  # simulates server restart
            decision = await svc2.get_decision("file_delete", "s1")
            assert decision == PermissionDecision.DENY

            decision = await svc2.request("file_delete", "Delete file", RiskLevel.MEDIUM, {}, "s1")
            assert decision == PermissionDecision.DENY
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_no_rule_returns_none(self, temp_dir):
        db = Database(str(temp_dir / "test.db"))
        await db.connect()
        try:
            repo = PermissionRepository(db)
            svc = DefaultPermissionService(repo=repo)
            assert await svc.get_decision("bash", "s1") is None
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_revoke_persists(self, temp_dir):
        db = Database(str(temp_dir / "test.db"))
        await db.connect()
        try:
            repo = PermissionRepository(db)
            svc1 = DefaultPermissionService(repo=repo)
            await svc1.grant_persistent("bash", PermissionDecision.DENY)
            await svc1.revoke_persistent("bash")
            svc2 = DefaultPermissionService(repo=repo)
            assert await svc2.get_decision("bash", "s1") is None
        finally:
            await db.close()


class TestMiddlewareWiring:
    @pytest.mark.asyncio
    async def test_safety_middleware_wired_into_registry(self, temp_dir):
        create_default_registry()
        ctx = ToolContext(request_id="r1", mode="build")
        mw = SafetyCheckMiddleware()
        result = await mw.before_execute("bash", {"command": "sudo rm -rf /"}, ctx)
        assert isinstance(result, ToolResult)
        assert not result.success

    @pytest.mark.asyncio
    async def test_permission_middleware_blocks_persisted_deny(self, temp_dir):
        db = Database(str(temp_dir / "test.db"))
        await db.connect()
        try:
            repo = PermissionRepository(db)
            svc = DefaultPermissionService(repo=repo)
            await svc.grant_persistent("file_delete", PermissionDecision.DENY)
            mw = PermissionMiddleware(service=svc)
            ctx = ToolContext(request_id="r1", mode="build", session_id="s1")
            result = await mw.before_execute("file_delete", {"filepath": "x.txt"}, ctx)
            assert isinstance(result, ToolResult)
            assert not result.success
            assert "denied" in result.error
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_permission_middleware_passes_through_without_rule(self, temp_dir):
        db = Database(str(temp_dir / "test.db"))
        await db.connect()
        try:
            repo = PermissionRepository(db)
            svc = DefaultPermissionService(repo=repo)
            mw = PermissionMiddleware(service=svc)
            ctx = ToolContext(request_id="r1", mode="build", session_id="s1")
            assert await mw.before_execute("file_write", {"filepath": "x.txt"}, ctx) is True
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_registry_execute_enforces_persisted_deny(self, temp_dir):
        """End-to-end: a persisted deny rule blocks a real tool through the
        registry without an interactive confirmation."""
        db = Database(str(temp_dir / "test.db"))
        await db.connect()
        try:
            repo = PermissionRepository(db)
            svc = DefaultPermissionService(repo=repo)
            await svc.grant_persistent("file_write", PermissionDecision.DENY)
            reg = create_default_registry(permission_service=svc)
            target = temp_dir / "out.txt"
            result = await reg.execute(
                "file_write",
                {"path": str(target), "content": "hello"},
                str(temp_dir),
                mode="build",
                session_id="s1",
            )
            assert not result.success
            assert "denied" in result.error
            assert not target.exists()
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_registry_execute_allows_when_rule_is_allow(self, temp_dir):
        db = Database(str(temp_dir / "test.db"))
        await db.connect()
        try:
            repo = PermissionRepository(db)
            svc = DefaultPermissionService(repo=repo)
            await svc.grant_persistent("file_write", PermissionDecision.ALLOW)
            reg = create_default_registry(permission_service=svc)
            target = temp_dir / "out.txt"
            result = await reg.execute(
                "file_write",
                {"path": str(target), "content": "hello"},
                str(temp_dir),
                mode="build",
                session_id="s1",
            )
            assert result.success
            assert target.exists()
        finally:
            await db.close()
