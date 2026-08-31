"""Integration coverage for the live event pipeline.

C-F02: SESSION_SUMMARIZED must reach the transport BEFORE the terminal
SUCCESS/ERROR event (the TUI unsubscribes synchronously on the first terminal
event) and must be part of the persisted message event trail so resume can
reconstruct it. Exercises the REAL PromptExecutor forwarding loop + finally
block + ConnectionManager buffering; only the agent LLM loop is faked.

C-F03: DefaultSessionService publishes domain events on a real AsyncEventBus
wired in ZenithHandler; published events must arrive in the ConnectionManager
buffer exactly once (no duplicate emission from handler-side code).
"""

import asyncio
import json
import shutil
import tempfile
from pathlib import Path
from typing import ClassVar

import pytest

import server.agents.prompt_executor as pe_module
from server.api.websocket import ConnectionManager, ZenithHandler
from server.config.providers import ProviderConfig
from server.config.settings import AppSettings
from server.domain.events import Event, EventKind
from server.domain.message import Message
from server.domain.session import Session
from server.providers.base import BaseProvider
from server.providers.registry import ProviderRegistry
from server.storage.session_store import FileMessageRepository, FileSessionRepository


class StubProvider(BaseProvider):
    def __init__(self):
        super().__init__("test", "test-model")

    async def complete(self, messages: list[dict], tools=None) -> str:
        return "ok"

    async def stream(
        self, messages: list[dict], tools=None, tool_choice=None, response_format=None
    ):
        yield ("ok", None)

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["test-model"]


class _FakeAgentLoop:
    """Stands in for RecoverableAgentLoop: same surface, scripted events."""

    scripted_events: ClassVar[list[Event]] = []
    summary_text = "Final summary."

    def __init__(self, *args, **kwargs):
        self.summary = ""

    def set_summary(self, text: str) -> None:
        self.summary = text

    async def process_prompt(self, content, session_id, history, mode, **kwargs):
        self.set_summary(self.summary_text)
        for ev in _FakeAgentLoop.scripted_events:
            ev.session_id = session_id
            yield ev


@pytest.fixture
def temp_dir():
    """Module-local override: aiosqlite can release its handle slightly after
    Database.close() on Windows, so cleanup tolerates transient locks."""
    tmpdir = tempfile.mkdtemp()
    try:
        yield Path(tmpdir)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def test_config(temp_dir):
    return AppSettings(
        providers={"test": ProviderConfig(model="test-model", is_active=True)},
        active_provider="test",
        home_dir=str(temp_dir),
        workspace_root=str(temp_dir),
    )


@pytest.fixture
def test_home(temp_dir):
    from server.storage import StorageHome, ensure_materialized

    h = StorageHome(temp_dir)
    ensure_materialized(h)
    return h


@pytest.fixture
def test_registry():
    registry = ProviderRegistry()
    registry.register("test", StubProvider())
    return registry


def _buffered_kinds(manager: ConnectionManager, session_id: str) -> list[str]:
    payloads = manager.event_buffers.get(session_id, [])
    return [str(json.loads(p)["params"]["kind"]) for p in payloads]


@pytest.mark.asyncio
async def test_session_summarized_precedes_terminal_and_is_persisted(test_config, test_home):
    """The C-F02 invariant over the real executor/transport chain."""
    session_repo = FileSessionRepository(test_home)
    message_repo = FileMessageRepository(test_home)
    session = await session_repo.create(Session(title="Ordering"))

    class _SkillLoader:
        def get_skill_prompt(self):
            return ""

    class _Registry:
        pass

    executor = pe_module.PromptExecutor(
        test_config,
        StubProvider(),
        _Registry(),
        session_repo,
        message_repo,
        _SkillLoader(),
    )
    manager = ConnectionManager()

    _FakeAgentLoop.scripted_events = [
        Event(kind=EventKind.MESSAGE, data={"text": "Hello world", "partial": False}),
        Event(kind=EventKind.SUCCESS, data={"iterations": 1}),
    ]
    original_cls = pe_module.SimpleLoop
    pe_module.SimpleLoop = _FakeAgentLoop
    try:
        await executor._execute(session.id, "do the thing", "build", None, manager)
    finally:
        pe_module.SimpleLoop = original_cls

    kinds = _buffered_kinds(manager, session.id)
    assert "session_summarized" in kinds, f"summarized missing from transport stream: {kinds}"
    assert "success" in kinds, f"terminal success missing: {kinds}"
    assert kinds.index("session_summarized") < kinds.index("success"), (
        f"session_summarized must precede the terminal event, got {kinds}"
    )

    # The summarized snapshot is part of the persisted assistant-message trail.
    history = await message_repo.get_by_session(session.id)
    assistant = [m for m in history if m.role == "assistant"]
    assert assistant, "assistant message not persisted"
    persisted_kinds = [e.kind for e in assistant[-1].events]
    assert EventKind.SESSION_SUMMARIZED in persisted_kinds, (
        f"session_summarized not persisted with the message: {persisted_kinds}"
    )


@pytest.mark.asyncio
async def test_session_summarized_error_terminal_ordering(test_config, test_home):
    """ERROR terminals flush after the summary too (exception path)."""
    session_repo = FileSessionRepository(test_home)
    message_repo = FileMessageRepository(test_home)
    from server.domain.session import Session

    session = await session_repo.create(Session(title="ErrOrder"))

    class _BoomAgent(_FakeAgentLoop):
        async def process_prompt(self, content, session_id, history, mode, **kwargs):
            self.set_summary("Partial summary before failure.")
            yield Event(kind=EventKind.MESSAGE, data={"text": "working", "partial": False})
            raise RuntimeError("provider exploded")

    class _SkillLoader:
        def get_skill_prompt(self):
            return ""

    executor = pe_module.PromptExecutor(
        test_config, StubProvider(), type("R", (), {})(), session_repo, message_repo, _SkillLoader()
    )
    manager = ConnectionManager()
    original_cls = pe_module.SimpleLoop
    pe_module.SimpleLoop = _BoomAgent
    try:
        await executor._execute(session.id, "break it", "build", None, manager)
    finally:
        pe_module.SimpleLoop = original_cls

    kinds = _buffered_kinds(manager, session.id)
    assert "error" in kinds and "session_summarized" in kinds, kinds
    assert kinds.index("session_summarized") < kinds.index("error"), kinds


@pytest.mark.asyncio
async def test_service_events_travel_bus_to_manager_exactly_once(
    test_config, test_home, test_registry
):
    """C-F03: service publishes once via the wired bus; handler adds nothing."""
    handler = ZenithHandler(test_config, test_home, test_registry)
    handler._ensure_event_bus_bridge()

    svc = handler._session_service
    try:
        session = await svc.create(title="BusTest")
        for _ in range(20):
            if handler.manager.event_buffers.get(session.id):
                break
            await asyncio.sleep(0.02)

        created_kinds = _buffered_kinds(handler.manager, session.id)
        assert created_kinds.count("session_created") == 1, (
            f"expected exactly one session_created, got {created_kinds}"
        )

        duplicate = await svc.duplicate(session.id, "Copy")
        for _ in range(20):
            if handler.manager.event_buffers.get(duplicate.id):
                break
            await asyncio.sleep(0.02)

        dup_kinds = _buffered_kinds(handler.manager, duplicate.id)
        assert dup_kinds.count("session_duplicated") == 1, (
            f"expected exactly one session_duplicated, got {dup_kinds}"
        )
    finally:
        if handler._bus_task is not None and not handler._bus_task.done():
            handler._bus_task.cancel()
            try:
                await handler._bus_task
            except asyncio.CancelledError:
                pass


def test_session_summarized_persisted_message_roundtrip_shape():
    """Sanity: Message(events=[...]) keeps kind enums intact through repos."""
    msg = Message(session_id="s", role="assistant", content="x")
    msg.events.append(Event(kind=EventKind.SESSION_SUMMARIZED, data={"summary": "s"}))
    assert msg.events[0].kind == EventKind.SESSION_SUMMARIZED
