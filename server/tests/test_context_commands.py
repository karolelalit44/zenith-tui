import json

import pytest

from server.config.constants import DEFAULT_CONTEXT_WINDOW
from server.config.providers import ProviderConfig
from server.config.settings import AppSettings
from server.domain.events import Event, EventKind
from server.domain.message import Message
from server.domain.session import Session
from server.persistence.connection import Database
from server.providers.base import BaseProvider


class StubProvider(BaseProvider):
    def __init__(self, total_tokens: int = 0, context_window: int = DEFAULT_CONTEXT_WINDOW):
        super().__init__("test", "test-model")
        self._context_window = context_window
        self._cumulative_usage = {
            "total_tokens": total_tokens,
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }

    async def complete(self, messages: list[dict], tools=None) -> str:
        return "summarized"

    async def stream(
        self, messages: list[dict], tools=None, tool_choice=None, response_format=None
    ):
        for char in "summarized":
            yield (char, None)

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["test-model"]


def _fake_ws(captured: dict):
    async def send_text(_self, text):
        captured["text"] = text

    return type("W", (), {"send_text": send_text})()


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


@pytest.fixture
def registry():
    from server.providers.registry import ProviderRegistry

    reg = ProviderRegistry()
    reg.register("test", StubProvider())
    return reg


@pytest.fixture
def handler(test_config, test_db, registry):
    from server.api.websocket import ZenithHandler

    h = ZenithHandler(test_config, test_db, registry)
    events = []

    async def mock_send_event(self, session_id, event, **kw):
        events.append(event)

    h.handlers.manager = type("M", (), {"send_event": mock_send_event})()
    return (h, events)


class TestContextCommands:
    @pytest.mark.asyncio
    async def test_compact_summarizes_and_truncates_prefix(self, handler):
        import datetime

        h, events = handler
        session = await h.session_repo.create(Session(title="Compact Test"))
        turns = 5
        base = datetime.datetime(2026, 1, 1, 12, 0, 0)
        for i in range(turns):
            await h.message_repo.create(
                Message(
                    session_id=session.id,
                    role="user",
                    content=f"User prompt {i} " + "x" * 40000,
                    created_at=base + datetime.timedelta(milliseconds=2 * i),
                )
            )
            await h.message_repo.create(
                Message(
                    session_id=session.id,
                    role="assistant",
                    content=f"Assistant response {i}",
                    created_at=base + datetime.timedelta(milliseconds=2 * i + 1),
                )
            )
        ws = _fake_ws({})
        await h.handlers._context_compact(ws, 1, session.id)
        assert any(e.kind == EventKind.CONTEXT_COMPACTION_STARTED for e in events)
        ended = [e for e in events if e.kind == EventKind.CONTEXT_COMPACTION_ENDED]
        assert ended
        assert not ended[-1].data.get("failed")
        assert ended[-1].data.get("status") == "completed"
        assert ended[-1].data.get("trigger") == "manual"
        loaded = await h.message_repo.get_by_session(session.id)
        # Prefix is truncated but the recent tail survives — history is never wiped.
        assert 0 < len(loaded) < turns * 2
        assert loaded[-1].content == f"Assistant response {turns - 1}"
        assert any("User prompt" in m.content for m in loaded)
        updated = await h.session_repo.get(session.id)
        summary = (updated.metadata or {}).get("summary")
        assert summary
        # The truncated representation is resumable: rebuilding context from the
        # surviving tail + summary works.
        from server.agents.context import ContextManager

        rebuilt = ContextManager(h.config).build_messages(
            loaded, "System.", "More.", "test-model", summary=summary
        )
        assert any("[Previous conversation summary]" in m.get("content", "") for m in rebuilt)

    @pytest.mark.asyncio
    async def test_compact_small_session_is_a_noop(self, handler):
        h, events = handler
        session = await h.session_repo.create(Session(title="Compact Small"))
        for i in range(3):
            await h.message_repo.create(
                Message(session_id=session.id, role="user", content=f"Small prompt {i}")
            )
            await h.message_repo.create(
                Message(session_id=session.id, role="assistant", content=f"Small reply {i}")
            )
        ws = _fake_ws({})
        await h.handlers._context_compact(ws, 1, session.id)
        ended = [e for e in events if e.kind == EventKind.CONTEXT_COMPACTION_ENDED]
        assert ended and not ended[-1].data.get("failed")
        loaded = await h.message_repo.get_by_session(session.id)
        assert len(loaded) == 6
        updated = await h.session_repo.get(session.id)
        assert not (updated.metadata or {}).get("summary")

    @pytest.mark.asyncio
    async def test_compact_no_session_returns_error(self, handler):
        h, _ = handler
        captured = {}
        ws = _fake_ws(captured)
        await h.handlers._context_compact(ws, 1, None)
        assert "-32602" in captured["text"]

    @pytest.mark.asyncio
    async def test_clear_tools_removes_tool_events(self, handler):
        h, _ = handler
        session = await h.session_repo.create(Session(title="Clear Tools Test"))
        msg = Message(
            session_id=session.id,
            role="assistant",
            content="done",
            events=[
                Event(
                    kind=EventKind.TOOL_CALL,
                    data={"tool": "bash", "params": {"command": "ls"}},
                    session_id=session.id,
                ),
                Event(
                    kind=EventKind.TOOL_RESULT,
                    data={"tool": "bash", "output": "file1\nfile2"},
                    session_id=session.id,
                ),
                Event(kind=EventKind.MESSAGE, data={"text": "listed files"}, session_id=session.id),
            ],
        )
        await h.message_repo.create(msg)
        captured = {}
        ws = _fake_ws(captured)
        await h.handlers._context_clear_tools(ws, 1, session.id)
        result_doc = json.loads(captured["text"])
        result = result_doc.get("result", {})
        assert result.get("removed", 0) >= 1
        loaded = await h.message_repo.get_by_session(session.id)
        assert len(loaded) == 1
        kinds = [e.kind.value for e in loaded[0].events]
        assert "tool_result" not in kinds
        assert "tool_call" in kinds
        assert "message" in kinds
