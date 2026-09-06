import asyncio
import json
from pathlib import Path

import pytest

from server.agents.prompt_executor import (
    ATTACHMENT_MAX_FILE,
    FOLDER_INLINE_MAX_ENTRIES,
    PromptExecutor,
    list_attachment,
    read_attachment,
)
from server.config.constants import DEFAULT_LLM_MAX_TOKENS, DEFAULT_LLM_TEMPERATURE
from server.config.providers import ProviderConfig
from server.config.settings import AppSettings
from server.domain.events import EventKind
from server.domain.session import Session
from server.providers.base import BaseProvider


class RecordingProvider(BaseProvider):
    def __init__(self, model: str = "base-model", slow: bool = False):
        super().__init__("rec", model)
        self.slow = slow
        self.calls: list[dict] = []

    async def complete(self, messages, tools=None):
        user_msg = messages[-1]["content"] if messages else ""
        return f"Echo: {user_msg}"

    async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
        self.calls.append(
            {"model": self.model, "temperature": self.temperature, "max_tokens": self.max_tokens}
        )
        response = await self.complete(messages)
        if self.slow:
            for ch in response:
                yield (ch, None)
                await asyncio.sleep(0.02)
            return
        for chunk in response.split(" "):
            yield (chunk + " ", None)

    async def validate(self):
        return True

    async def list_models(self):
        return ["base-model"]


def _fake_ws(captured: dict):
    async def send_text(_self, text):
        captured["text"] = text

    return type("W", (), {"send_text": send_text})()


@pytest.fixture
def test_config(temp_dir):
    return AppSettings(
        providers={"test": ProviderConfig(model="base-model", is_active=True)},
        active_provider="test",
        db_path=str(temp_dir / "test.db"),
        workspace_root=str(temp_dir),
    )


@pytest.fixture
def storage_home(temp_dir):
    from server.storage import StorageHome, ensure_materialized

    h = StorageHome(temp_dir)
    ensure_materialized(h)
    return h


@pytest.fixture
def registry():
    from server.providers.registry import ProviderRegistry

    reg = ProviderRegistry()
    reg.register("test", RecordingProvider(slow=True))
    return reg


@pytest.fixture
def handler(test_config, storage_home, registry):
    from server.api.websocket import ZenithHandler

    h = ZenithHandler(test_config, storage_home, registry)
    events = []

    async def mock_send_event(self, session_id, event, **kw):
        events.append(event)

    h.handlers.manager = type("M", (), {"send_event": mock_send_event})()
    return (h, events)


def _make_executor(config, provider, home):
    from server.storage.session_store import FileMessageRepository, FileSessionRepository
    from server.toolkit import create_default_registry

    return PromptExecutor(
        config,
        provider,
        create_default_registry(),
        FileSessionRepository(home),
        FileMessageRepository(home),
    )


class TestProviderOverrides:
    @pytest.mark.asyncio
    async def test_overrides_applied_and_restored(self, test_config, storage_home):
        provider = RecordingProvider()
        executor = _make_executor(test_config, provider, storage_home)
        session = await executor._session_repo.create(Session(title="Override Test"))
        await executor._execute(
            session.id,
            "hello",
            "build",
            None,
            None,
            model_override="override-model",
            temperature=0.2,
            max_tokens=123,
            attachments=[],
        )
        assert provider.calls, "provider.stream was never called"
        observed = provider.calls[0]
        assert observed["model"] == "override-model"
        assert observed["temperature"] == 0.2
        assert observed["max_tokens"] == 123
        assert provider.model == "base-model"
        assert provider.temperature == DEFAULT_LLM_TEMPERATURE
        assert provider.max_tokens == DEFAULT_LLM_MAX_TOKENS

    @pytest.mark.asyncio
    async def test_no_override_when_not_provided(self, test_config, storage_home):
        provider = RecordingProvider()
        executor = _make_executor(test_config, provider, storage_home)
        session = await executor._session_repo.create(Session(title="No Override"))
        await executor._execute(session.id, "hello", "build", None, None)
        assert provider.calls[0]["model"] == "base-model"
        assert provider.calls[0]["temperature"] == DEFAULT_LLM_TEMPERATURE
        assert provider.calls[0]["max_tokens"] == DEFAULT_LLM_MAX_TOKENS
        assert provider.model == "base-model"


class TestPromptPersistence:
    @pytest.mark.asyncio
    async def test_message_metadata_and_session_row(self, handler, temp_dir):
        h, _ = handler
        session = await h.session_repo.create(Session(title="Meta Test"))
        (temp_dir / "notes.txt").write_text("important notes")
        captured = {}
        ws = _fake_ws(captured)
        sid = await h.handlers._prompt(
            ws,
            1,
            {
                "content": "Use the file",
                "mode": "build",
                "provider": "test",
                "model": "override-model",
                "temperature": 0.1,
                "max_tokens": 777,
                "attachments": [
                    {"path": "notes.txt"},
                    {"path": "notes.txt"},
                    {"path": "missing.txt"},
                ],
            },
            session.id,
        )
        assert sid == session.id
        executor = h.handlers._session_executors[session.id]
        await executor._active_task
        messages = await h.message_repo.get_by_session(session.id)
        user_msg = next(m for m in messages if m.role == "user")
        assert user_msg.metadata.get("model") == "override-model"
        assert user_msg.metadata.get("attachment_paths") == ["notes.txt", "missing.txt"]
        updated = await h.session_repo.get(session.id)
        assert updated.model == "override-model"
        assert updated.metadata.get("last_model") == "override-model"

    @pytest.mark.asyncio
    async def test_no_model_keeps_session_model(self, handler):
        h, _ = handler
        session = await h.session_repo.create(Session(title="No Model", model="prev-model"))
        captured = {}
        ws = _fake_ws(captured)
        await h.handlers._prompt(
            ws, 1, {"content": "hello", "mode": "build", "provider": "test"}, session.id
        )
        executor = h.handlers._session_executors[session.id]
        await executor._active_task
        updated = await h.session_repo.get(session.id)
        assert updated.model == "prev-model"
        assert "last_model" not in (updated.metadata or {})

    @pytest.mark.asyncio
    async def test_invalid_temperature_rejected(self, handler):
        h, _ = handler
        captured = {}
        ws = _fake_ws(captured)
        await h.handlers._prompt(ws, 1, {"content": "hello", "temperature": 2.5}, None)
        assert "-32602" in captured["text"]
        assert "temperature" in captured["text"]

    @pytest.mark.asyncio
    async def test_invalid_max_tokens_rejected(self, handler):
        h, _ = handler
        captured = {}
        ws = _fake_ws(captured)
        await h.handlers._prompt(ws, 1, {"content": "hello", "max_tokens": 0}, None)
        assert "-32602" in captured["text"]
        assert "max_tokens" in captured["text"]


class TestPromptCancel:
    @pytest.mark.asyncio
    async def test_cancel_inflight_task(self, handler):
        h, _ = handler
        session = await h.session_repo.create(Session(title="Cancel Test"))
        captured = {}
        ws = _fake_ws(captured)
        sid = await h.handlers._prompt(
            ws, 1, {"content": "Slow prompt", "mode": "build", "provider": "test"}, session.id
        )
        assert sid == session.id
        await asyncio.sleep(0.05)
        assert not h.handlers._session_executors[session.id]._active_task.done()
        captured2 = {}
        ws2 = _fake_ws(captured2)
        await h.handlers._cancel_prompt(ws2, 2, session.id)
        assert json.loads(captured2["text"])["result"]["cancelled"] is True
        await asyncio.sleep(0.05)
        task = h.handlers._session_executors[session.id]._active_task
        assert task.done()
        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_cancel_idempotent_no_executor(self, handler):
        h, _ = handler
        session = await h.session_repo.create(Session(title="No Executor"))
        captured = {}
        ws = _fake_ws(captured)
        await h.handlers._cancel_prompt(ws, 3, session.id)
        assert json.loads(captured["text"])["result"]["cancelled"] is False


class TestAttachmentGuards:
    @pytest.mark.asyncio
    async def test_read_attachment_guards(self, temp_dir):
        (temp_dir / "ok.txt").write_text("hello world")
        outside = temp_dir.parent / "outside.txt"
        outside.write_text("secrets")
        big = temp_dir / "big.txt"
        big.write_bytes(b"x" * (ATTACHMENT_MAX_FILE + 1))
        binary = temp_dir / "bin.dat"
        binary.write_bytes(b"abc\x00def")
        content, error = await read_attachment("ok.txt", str(temp_dir))
        assert content == "hello world"
        assert error is None
        content, error = await read_attachment("../outside.txt", str(temp_dir))
        assert content is None
        assert error == "path escapes workspace"
        content, error = await read_attachment(str(outside), str(temp_dir))
        assert content is None
        assert error == "path escapes workspace"
        content, error = await read_attachment("big.txt", str(temp_dir))
        assert content is None
        assert "too large" in error
        content, error = await read_attachment("bin.dat", str(temp_dir))
        assert content is None
        assert error == "binary file"
        content, error = await read_attachment("nope.txt", str(temp_dir))
        assert content is None
        assert error == "file not found"

    @pytest.mark.asyncio
    async def test_inject_attachments_prepends_and_warns(self, test_config, storage_home, temp_dir):
        provider = RecordingProvider()
        executor = _make_executor(test_config, provider, storage_home)
        (temp_dir / "a.txt").write_text("AAA")
        events = []
        injected = await executor._inject_attachments(
            "user text", [{"path": "a.txt"}, {"path": "missing.txt"}], "s1", None, events
        )
        assert '<attachment path="a.txt" kind="file">\nAAA\n</attachment>' in injected
        assert injected.endswith("user text")
        assert any(e.kind == EventKind.WARNING for e in events)
        assert any("missing.txt" in e.data.get("message", "") for e in events)

    @pytest.mark.asyncio
    async def test_inject_attachments_inline_content_escape_hatch(self, test_config, storage_home):
        provider = RecordingProvider()
        executor = _make_executor(test_config, provider, storage_home)
        events = []
        injected = await executor._inject_attachments(
            "user text", [{"path": "virtual.py", "content": "print('x')"}], "s1", None, events
        )
        assert '<attachment path="virtual.py" kind="file">\nprint(\'x\')\n</attachment>' in injected
        assert events == []

    @pytest.mark.asyncio
    async def test_attachment_blocks_reach_assistant_message(self, handler, temp_dir):
        h, _ = handler
        session = await h.session_repo.create(Session(title="Attach E2E"))
        (temp_dir / "data.txt").write_text("payload content")
        captured = {}
        ws = _fake_ws(captured)
        await h.handlers._prompt(
            ws,
            1,
            {
                "content": "Read the file",
                "mode": "build",
                "provider": "test",
                "attachments": [{"path": "data.txt"}],
            },
            session.id,
        )
        executor = h.handlers._session_executors[session.id]
        await executor._active_task
        messages = await h.message_repo.get_by_session(session.id)
        user_msg = next(m for m in messages if m.role == "user")
        assert user_msg.metadata.get("attachment_paths") == ["data.txt"]
        stored = await h.message_repo.get_by_session(session.id)
        assistant_msgs = [m for m in stored if m.role == "assistant"]
        assert assistant_msgs
        assert "<attachment path=" in assistant_msgs[-1].content


class TestNormalizeAttachments:
    def test_dedupes_caps_and_filters(self):
        from server.api.handlers import _normalize_attachments

        raw = [
            {"path": "a.txt"},
            {"path": "a.txt"},
            {"path": " b.txt "},
            {"path": ""},
            "not-a-dict",
            {"path": "c.txt", "name": "C", "content": "inline"},
        ]
        result = _normalize_attachments(raw)
        assert result == [
            {"path": "a.txt"},
            {"path": "b.txt"},
            {"path": "c.txt", "name": "C", "content": "inline"},
        ]

    def test_caps_at_25(self):
        from server.api.handlers import _normalize_attachments

        raw = [{"path": f"f{i}.txt"} for i in range(40)]
        result = _normalize_attachments(raw)
        assert len(result) == 25

    def test_non_list_returns_empty(self):
        from server.api.handlers import _normalize_attachments

        assert _normalize_attachments(None) == []
        assert _normalize_attachments("nope") == []

    def test_passes_through_kind_and_size(self):
        from server.api.handlers import _normalize_attachments

        raw = [
            {"path": "a.txt", "name": "a.txt", "kind": "file", "size": 100},
            {"path": "src", "name": "src", "kind": "folder", "size": 0},
        ]
        result = _normalize_attachments(raw)
        assert result == [
            {"path": "a.txt", "name": "a.txt", "kind": "file", "size": 100},
            {"path": "src", "name": "src", "kind": "folder", "size": 0},
        ]

    def test_defaults_kind_to_file(self):
        from server.api.handlers import _normalize_attachments

        result = _normalize_attachments([{"path": "a.txt"}])
        assert result == [{"path": "a.txt"}]


class TestFolderAttachments:
    @pytest.mark.asyncio
    async def test_list_attachment_walks_tree_and_reports_sizes(self, temp_dir):
        (temp_dir / "src").mkdir()
        (temp_dir / "src" / "a.ts").write_text("x" * 10)
        (temp_dir / "src" / "b.ts").write_text("y" * 20)
        data, error = await list_attachment("src", str(temp_dir))
        assert error is None
        names = {e["name"]: e for e in data["entries"]}
        assert names["a.ts"]["kind"] == "file"
        assert names["a.ts"]["size"] == 10
        assert data["total"] == 30
        assert data["truncated"] is False

    @pytest.mark.asyncio
    async def test_list_attachment_respects_zenithignore(self, temp_dir):
        (temp_dir / ".zenithignore").write_text("vendor/\nsecrets.txt\n")
        (temp_dir / "vendor").mkdir()
        (temp_dir / "vendor" / "dep.js").write_text("x")
        (temp_dir / "secrets.txt").write_text("s3cr3t")
        (temp_dir / "keep.txt").write_text("ok")
        data, error = await list_attachment("", str(temp_dir))
        assert error is None
        names = {e["name"] for e in data["entries"]}
        assert "keep.txt" in names
        assert "secrets.txt" not in names
        assert "dep.js" not in names

    @pytest.mark.asyncio
    async def test_list_attachment_escape_guard(self, temp_dir):
        outside = temp_dir.parent / "outside_dir"
        outside.mkdir(exist_ok=True)
        data, error = await list_attachment("../outside_dir", str(temp_dir))
        assert data is None
        assert error == "path escapes workspace"

    @pytest.mark.asyncio
    async def test_list_attachment_missing_folder(self, temp_dir):
        data, error = await list_attachment("nope", str(temp_dir))
        assert data is None
        assert error == "folder not found"

    @pytest.mark.asyncio
    async def test_folder_injection_inlines_tiny_folder(self, test_config, storage_home):
        provider = RecordingProvider()
        executor = _make_executor(test_config, provider, storage_home)
        wr = Path(test_config.workspace_root)
        (wr / "pkg").mkdir()
        (wr / "pkg" / "one.txt").write_text("111")
        (wr / "pkg" / "two.txt").write_text("222")
        events = []
        injected = await executor._inject_attachments(
            "user text", [{"path": "pkg", "kind": "folder"}], "s1", None, events
        )
        assert '<file path="pkg/one.txt">\n111\n</file>' in injected
        assert '<file path="pkg/two.txt">\n222\n</file>' in injected
        assert events == []

    @pytest.mark.asyncio
    async def test_folder_injection_references_large_folder(self, test_config, storage_home):
        provider = RecordingProvider()
        executor = _make_executor(test_config, provider, storage_home)
        root = Path(test_config.workspace_root) / "big"
        root.mkdir()
        for i in range(FOLDER_INLINE_MAX_ENTRIES + 5):
            (root / f"f{i}.txt").write_text("x" * 100)
        events = []
        injected = await executor._inject_attachments(
            "user text", [{"path": "big", "kind": "folder"}], "s1", None, events
        )
        # Large folders become a tree/scope reference, not individual file dumps.
        assert "<file path=" not in injected
        assert "directory `big`" in injected
        assert events == []

    @pytest.mark.asyncio
    async def test_folder_injection_isolates_by_kind(self, test_config, storage_home):
        provider = RecordingProvider()
        executor = _make_executor(test_config, provider, storage_home)
        root = Path(test_config.workspace_root) / "mix"
        root.mkdir()
        (root / "seen.txt").write_text("content")
        outsider = Path(test_config.workspace_root) / "outsider.txt"
        outsider.write_text("should not appear here")
        events = []
        injected = await executor._inject_attachments(
            "user text", [{"path": "mix", "kind": "folder"}], "s1", None, events
        )
        assert "seen.txt" in injected
        assert "outsider.txt" not in injected


class TestLoopWiring:
    """J1: the executor must run the new SimpleLoop and route its event stream
    through the module-10 transport event-adapter (iter_client_events)."""

    @pytest.mark.asyncio
    async def test_executor_runs_simple_loop_to_terminal_success(self, test_config, storage_home):
        provider = RecordingProvider()
        executor = _make_executor(test_config, provider, storage_home)
        session = await executor._session_repo.create(Session(title="Loop Wiring"))
        terminal: list[EventKind] = []

        async def _send(self, session_id, event):
            terminal.append(event.kind)

        await executor._execute(
            session.id,
            "say hello",
            "build",
            None,
            type("M", (), {"send_event": _send})(),
        )

        # The new SimpleLoop must terminate with a SUCCESS event forwarded to
        # the manager (terminal events are held for after the run-state snapshot).
        assert EventKind.SUCCESS in terminal, "expected a terminal SUCCESS event"

        # The turn completed and persisted an assistant message — the concrete
        # observable contract of wiring the new engine into the executor.
        messages = await executor._message_repo.get_by_session(session.id)
        assert any(m.role == "assistant" for m in messages)
        assert provider.calls, "SimpleLoop must have streamed via the provider"


class TestRunStatusAdoption:
    """The executor drives the module-07 (opencode `status.ts`) busy/idle flag.

    The session flips to busy while a turn is in flight (persisted so observers
    see it), and returns to idle last — after all run persistence has settled.
    """

    @pytest.mark.asyncio
    async def test_session_busy_during_turn_then_idle_after(self, test_config, storage_home):
        gate = asyncio.Event()
        released = asyncio.Event()

        class _GatedProvider(BaseProvider):
            def __init__(self):
                super().__init__("gated", "base-model")

            async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
                yield ("working", None)
                gate.set()
                await released.wait()
                yield ("done", None)

            async def complete(self, messages, tools=None):
                return "done"

            async def validate(self):
                return True

            async def list_models(self):
                return ["base-model"]

        provider = _GatedProvider()
        executor = _make_executor(test_config, provider, storage_home)
        session = await executor._session_repo.create(Session(title="Status Adoption"))

        run = asyncio.create_task(executor._execute(session.id, "do it", "build", None, None))

        # Wait for the turn to start streaming, then assert the persisted row
        # is BUSY while the SimpleLoop is mid-flight.
        await asyncio.wait_for(gate.wait(), timeout=5)
        active = await executor._session_repo.get(session.id)
        assert active.run_status.value == "busy", "session should be BUSY during the turn"

        # Release the turn and let it settle to idle.
        released.set()
        await run

        settled = await executor._session_repo.get(session.id)
        assert settled.run_status.value == "idle", "session should return to IDLE after the turn"
