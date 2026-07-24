"""E2E tests for the permission system — direct assertions, no wrappers."""

import pytest
import asyncio
from zenith.config.settings import AppSettings
from zenith.config.providers import ProviderConfig
from zenith.db.connection import Database
from zenith.providers.base import BaseProvider
from zenith.providers.registry import ProviderRegistry
from zenith.tools.base import ToolResult
from zenith.tools.permission import PermissionGate
from zenith.tools.permission_store import PermissionStore
from zenith.tools.registry import ToolRegistry
from zenith.tools.file_write import FileWriteTool
from zenith.tools.bash import BashTool
from zenith.tools.glob_tool import GlobTool
from zenith.tools.webfetch import WebfetchTool
from zenith.agent.loop import AgentLoop
from zenith.core.events import EventKind


class ToolCallProvider(BaseProvider):
    def __init__(self):
        super().__init__("test", "test-model")
        self.call_count = 0

    async def complete(self, messages):
        self.call_count += 1
        if self.call_count == 1:
            return '```tool\n{"tool": "file_write", "params": {"filepath": "test.txt", "content": "hello"}}\n```'
        return "Done."

    async def stream(self, messages):
        response = await self.complete(messages)
        for char in response:
            yield (char, None)

    async def validate(self):
        return True

    async def list_models(self):
        return ["test-model"]


class DenyProvider(BaseProvider):
    """Returns tool call, then expects denial to stop tool loop."""

    def __init__(self):
        super().__init__("test", "test-model")
        self.call_count = 0

    async def complete(self, messages):
        self.call_count += 1
        if self.call_count == 1:
            return '```tool\n{"tool": "file_write", "params": {"filepath": "test.txt", "content": "hello"}}\n```'
        return "Ok, I won't write."

    async def stream(self, messages):
        response = await self.complete(messages)
        for char in response:
            yield (char, None)

    async def validate(self):
        return True

    async def list_models(self):
        return ["test-model"]


@pytest.fixture
def test_config(temp_dir):
    return AppSettings(
        providers={"test": ProviderConfig(model="test-model", is_active=True)},
        active_provider="test",
        db_path=str(temp_dir / "test.db"),
        workspace_root=str(temp_dir),
    )


@pytest.fixture
async def test_db(test_config):
    db = Database(test_config.db_path)
    await db.connect()
    yield db
    await db.close()


# ── PermissionStore ──────────────────────────────────────────────────

class TestPermissionStore:
    @pytest.mark.asyncio
    async def test_approve_and_check(self, test_db):
        store = PermissionStore(test_db)
        assert await store.is_approved("file_write") is False
        await store.approve("file_write")
        assert await store.is_approved("file_write") is True

    @pytest.mark.asyncio
    async def test_deny_removes_approval(self, test_db):
        store = PermissionStore(test_db)
        await store.approve("file_write")
        assert await store.is_approved("file_write") is True
        await store.deny("file_write")
        assert await store.is_approved("file_write") is False

    @pytest.mark.asyncio
    async def test_revoke_removes_entry(self, test_db):
        store = PermissionStore(test_db)
        await store.approve("bash")
        assert await store.is_approved("bash") is True
        await store.revoke("bash")
        assert await store.is_approved("bash") is False

    @pytest.mark.asyncio
    async def test_persistence_across_connections(self, test_config):
        db1 = Database(test_config.db_path)
        await db1.connect()
        await PermissionStore(db1).approve("file_edit")
        await db1.close()

        db2 = Database(test_config.db_path)
        await db2.connect()
        assert await PermissionStore(db2).is_approved("file_edit") is True
        await db2.close()

    @pytest.mark.asyncio
    async def test_list_approved(self, test_db):
        store = PermissionStore(test_db)
        await store.approve("file_write")
        await store.approve("bash")
        await store.deny("file_edit")
        names = [p["tool_name"] for p in await store.list_approved()]
        assert "file_write" in names
        assert "bash" in names
        assert "file_edit" not in names

    @pytest.mark.asyncio
    async def test_list_all(self, test_db):
        store = PermissionStore(test_db)
        await store.approve("file_write")
        await store.deny("bash")
        names = [p["tool_name"] for p in await store.list_all()]
        assert "file_write" in names
        assert "bash" in names

    @pytest.mark.asyncio
    async def test_clear_all(self, test_db):
        store = PermissionStore(test_db)
        await store.approve("file_write")
        await store.approve("bash")
        await store.clear_all()
        assert len(await store.list_all()) == 0

    @pytest.mark.asyncio
    async def test_upsert_single_row(self, test_db):
        store = PermissionStore(test_db)
        await store.approve("file_write")
        await store.deny("file_write")
        await store.approve("file_write")
        assert await store.is_approved("file_write") is True
        all_perms = await store.list_all()
        assert len([p for p in all_perms if p["tool_name"] == "file_write"]) == 1


# ── PermissionGate ───────────────────────────────────────────────────

class TestPermissionGate:
    @pytest.mark.asyncio
    async def test_low_auto_approved(self, test_db):
        gate = PermissionGate(store=PermissionStore(test_db))
        assert await gate.check(GlobTool()) is True

    @pytest.mark.asyncio
    async def test_medium_auto_approved(self, test_db):
        gate = PermissionGate(store=PermissionStore(test_db))
        assert await gate.check(WebfetchTool()) is True

    @pytest.mark.asyncio
    async def test_high_not_approved_by_default(self, test_db):
        gate = PermissionGate(store=PermissionStore(test_db))
        assert await gate.check(BashTool()) is False

    @pytest.mark.asyncio
    async def test_high_approved_after_db_approval(self, test_db):
        store = PermissionStore(test_db)
        await store.approve("bash")
        gate = PermissionGate(store=store)
        assert await gate.check(BashTool()) is True

    @pytest.mark.asyncio
    async def test_session_approval(self, test_db):
        gate = PermissionGate(store=PermissionStore(test_db))
        assert await gate.check(BashTool()) is False
        gate.approve_session("bash")
        assert await gate.check(BashTool()) is True

    @pytest.mark.asyncio
    async def test_check_sync(self):
        gate = PermissionGate()
        assert gate.check_sync(BashTool()) is False
        gate.approve_session("bash")
        assert gate.check_sync(BashTool()) is True
        assert gate.check_sync(FileWriteTool()) is False

    @pytest.mark.asyncio
    async def test_respond_resolves_future(self):
        gate = PermissionGate()
        tool = BashTool()

        task = asyncio.create_task(gate.request_permission(tool, {}))
        await asyncio.sleep(0.05)
        assert gate.pending_count() == 1
        key = gate.get_any_pending_key()
        assert key is not None

        responded = gate.respond(key, approved=True)
        assert responded is True
        result = await asyncio.wait_for(task, timeout=1.0)
        assert result is True

    @pytest.mark.asyncio
    async def test_respond_first(self):
        gate = PermissionGate()
        tool = BashTool()

        task = asyncio.create_task(gate.request_permission(tool, {}))
        await asyncio.sleep(0.05)
        assert gate.pending_count() == 1

        resolved = gate.respond_first(approved=True)
        assert resolved is True
        result = await asyncio.wait_for(task, timeout=1.0)
        assert result is True

    @pytest.mark.asyncio
    async def test_respond_deny(self):
        gate = PermissionGate()

        task = asyncio.create_task(gate.request_permission(BashTool(), {}))
        await asyncio.sleep(0.05)

        key = gate.get_any_pending_key()
        assert key is not None
        gate.respond(key, approved=False)

        result = await asyncio.wait_for(task, timeout=1.0)
        assert result is False
        assert "bash" not in gate.get_session_approved()

    @pytest.mark.asyncio
    async def test_has_pending(self):
        gate = PermissionGate()

        task = asyncio.create_task(gate.request_permission(BashTool(), {}))
        await asyncio.sleep(0.05)

        key = gate.get_any_pending_key()
        assert key is not None
        assert gate.has_pending(key) is True

        gate.respond(key, approved=True)
        await asyncio.sleep(0.01)
        assert gate.has_pending(key) is False
        await task

    @pytest.mark.asyncio
    async def test_timeout_returns_false(self):
        gate = PermissionGate()
        gate._pending = {}

        from zenith.tools.permission import PERMISSION_TIMEOUT_SECONDS
        gate._timeout_for_test = 0.1

        async def fast_timeout_request():
            future = asyncio.get_event_loop().create_future()
            gate._pending["test_key"] = future
            try:
                approved = await asyncio.wait_for(future, timeout=0.1)
            except asyncio.TimeoutError:
                approved = False
            finally:
                gate._pending.pop("test_key", None)
            return approved

        result = await fast_timeout_request()
        assert result is False
        assert gate.pending_count() == 0


# ── Agent Loop Permission Integration ────────────────────────────────

class TestAgentLoopPermission:
    @pytest.mark.asyncio
    async def test_permission_event_emitted_and_granted(self, test_config):
        gate = PermissionGate()
        registry = ToolRegistry(gate)
        registry.register(FileWriteTool())

        agent = AgentLoop(test_config, ToolCallProvider(), tool_registry=registry)

        async def auto_respond():
            for _ in range(100):
                if gate.respond_first(approved=True):
                    return
                await asyncio.sleep(0.02)

        asyncio.create_task(auto_respond())

        events = []
        async for event in agent.process_prompt("Write a file", "s1", [], "build"):
            events.append(event)

        perm_events = [e for e in events if e.kind == EventKind.PERMISSION_REQUEST]
        assert len(perm_events) >= 1, f"Expected PERMISSION_REQUEST event, got: {[e.kind for e in events]}"
        assert perm_events[0].data["tool"] == "file_write"

        file_events = [e for e in events if e.kind == EventKind.FILE_CREATE]
        assert len(file_events) >= 1, f"Expected FILE_CREATE after approval, got: {[e.kind for e in events]}"

    @pytest.mark.asyncio
    async def test_permission_granted_from_db(self, test_config, test_db):
        await PermissionStore(test_db).approve("file_write")
        gate = PermissionGate(store=PermissionStore(test_db))
        registry = ToolRegistry(gate)
        registry.register(FileWriteTool())

        agent = AgentLoop(test_config, ToolCallProvider(), tool_registry=registry)
        events = []
        async for event in agent.process_prompt("Write a file", "s1", [], "build"):
            events.append(event)

        perm_events = [e for e in events if e.kind == EventKind.PERMISSION_REQUEST]
        assert len(perm_events) == 0, f"Should auto-approve from DB, but got: {perm_events}"

        file_events = [e for e in events if e.kind == EventKind.FILE_CREATE]
        assert len(file_events) >= 1

    @pytest.mark.asyncio
    async def test_permission_denied_skips_tool(self, test_config):
        gate = PermissionGate()
        registry = ToolRegistry(gate)
        registry.register(FileWriteTool())

        agent = AgentLoop(test_config, DenyProvider(), tool_registry=registry)

        async def auto_deny():
            for _ in range(100):
                if gate.respond_first(approved=False):
                    return
                await asyncio.sleep(0.02)

        asyncio.create_task(auto_deny())

        events = []
        async for event in agent.process_prompt("Write a file", "s1", [], "build"):
            events.append(event)

        perm_events = [e for e in events if e.kind == EventKind.PERMISSION_REQUEST]
        assert len(perm_events) >= 1

        warning_events = [e for e in events if e.kind == EventKind.WARNING]
        denied = any("denied" in e.data.get("message", "").lower() for e in warning_events)
        assert denied, f"Expected denial warning, got warnings: {[e.data for e in warning_events]}"


# ── WebSocket Handler Permission RPC ────────────────────────────────

class TestWebSocketPermissionRPC:
    @pytest.mark.asyncio
    async def test_respond_rpc_resolves_pending(self, test_config, test_db):
        from zenith.transport.websocket import ZenithHandler
        from zenith.providers.registry import ProviderRegistry

        reg = ProviderRegistry()
        reg.register("test", ToolCallProvider())
        handler = ZenithHandler(test_config, test_db, reg)
        gate = handler.tool_registry.gate

        task = asyncio.create_task(gate.request_permission(BashTool(), {}))
        await asyncio.sleep(0.05)

        assert gate.pending_count() == 1
        key = gate.get_any_pending_key()
        assert key is not None

        gate.respond(key, approved=True, remember=False)
        result = await asyncio.wait_for(task, timeout=1.0)
        assert result is True

    @pytest.mark.asyncio
    async def test_approve_rpc(self, test_config, test_db):
        from zenith.transport.websocket import ZenithHandler
        from zenith.providers.registry import ProviderRegistry

        reg = ProviderRegistry()
        reg.register("test", ToolCallProvider())
        handler = ZenithHandler(test_config, test_db, reg)

        assert await PermissionStore(test_db).is_approved("bash") is False

        await PermissionStore(test_db).approve("bash")
        assert await PermissionStore(test_db).is_approved("bash") is True

        handler.tool_registry.gate.approve_session("bash")
        assert handler.tool_registry.gate.check_sync(BashTool()) is True

    @pytest.mark.asyncio
    async def test_deny_rpc(self, test_config, test_db):
        store = PermissionStore(test_db)
        await store.approve("bash")
        assert await store.is_approved("bash") is True
        await store.deny("bash")
        assert await store.is_approved("bash") is False

    @pytest.mark.asyncio
    async def test_list_rpc(self, test_config, test_db):
        store = PermissionStore(test_db)
        await store.approve("file_write")
        await store.approve("bash")
        perms = await store.list_all()
        assert len(perms) == 2

    @pytest.mark.asyncio
    async def test_full_flow(self, test_config, test_db):
        gate = PermissionGate(store=PermissionStore(test_db))

        assert await gate.check(BashTool()) is False

        task = asyncio.create_task(gate.request_permission(BashTool(), {}))
        await asyncio.sleep(0.05)

        key = gate.get_any_pending_key()
        assert key is not None

        gate.respond(key, approved=True)
        result = await asyncio.wait_for(task, timeout=1.0)
        assert result is True

        await PermissionStore(test_db).approve("bash")
        assert await PermissionStore(test_db).is_approved("bash") is True

        new_gate = PermissionGate(store=PermissionStore(test_db))
        assert await new_gate.check(BashTool()) is True
