import pytest
import asyncio
import json
import tempfile
from pathlib import Path
from httpx import AsyncClient, ASGITransport
from zenith.transport.server import create_app
from zenith.config.settings import AppSettings
from zenith.config.providers import ProviderConfig
from zenith.db.connection import Database
from zenith.providers.registry import ProviderRegistry
from zenith.providers.base import BaseProvider
from zenith.transport.websocket import ZenithHandler
from zenith.core.events import EventKind


class EchoProvider(BaseProvider):
    """Test provider that echoes the prompt back."""

    def __init__(self):
        super().__init__("test", "test-model")

    async def complete(self, messages: list[dict]) -> str:
        user_msg = messages[-1]["content"] if messages else ""
        return f"Echo: {user_msg}"

    async def stream(self, messages: list[dict]):
        response = await self.complete(messages)
        for word in response.split():
            yield word + " "

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
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


@pytest.fixture
def test_registry():
    registry = ProviderRegistry()
    registry.register("test", EchoProvider())
    return registry


@pytest.mark.asyncio
async def test_e2e_health(test_config, test_db, test_registry):
    handler = ZenithHandler(test_config, test_db, test_registry)
    app = create_app()
    app.state.handler = handler

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_e2e_session_create(test_config, test_db, test_registry):
    handler = ZenithHandler(test_config, test_db, test_registry)
    session = await handler.session_repo.create(
        __import__("zenith.core.session", fromlist=["Session"]).Session(title="Test")
    )
    loaded = await handler.session_repo.get(session.id)
    assert loaded is not None
    assert loaded.title == "Test"


@pytest.mark.asyncio
async def test_e2e_prompt_processing(test_config, test_db, test_registry):
    handler = ZenithHandler(test_config, test_db, test_registry)
    agent = __import__("zenith.agent.loop", fromlist=["AgentLoop"]).AgentLoop(
        test_config, EchoProvider()
    )

    events = []
    async for event in agent.process_prompt("Hello world", "session-1", [], "build"):
        events.append(event)

    assert len(events) >= 2
    assert events[0].kind == EventKind.THINKING
    assert any(e.kind == EventKind.MESSAGE for e in events)
    assert events[-1].kind == EventKind.SUCCESS


@pytest.mark.asyncio
async def test_e2e_full_workflow(test_config, test_db, test_registry):
    handler = ZenithHandler(test_config, test_db, test_registry)

    from zenith.core.session import Session
    from zenith.core.message import Message
    from datetime import datetime, timedelta

    session = Session(title="E2E Test")
    await handler.session_repo.create(session)

    # Create user message with earlier timestamp to ensure ordering
    earlier = datetime.now() - timedelta(seconds=1)
    user_msg = Message(
        session_id=session.id,
        role="user",
        content="Test prompt",
        created_at=earlier,
    )
    await handler.message_repo.create(user_msg)

    history = await handler.message_repo.get_by_session(session.id)
    assert len(history) == 1
    assert history[0].content == "Test prompt"

    agent = __import__("zenith.agent.loop", fromlist=["AgentLoop"]).AgentLoop(
        test_config, EchoProvider()
    )
    events = []
    async for event in agent.process_prompt("Test prompt", session.id, history, "build"):
        events.append(event)

    # Collect response text from non-partial messages only
    response_text = ""
    for e in events:
        if e.kind == EventKind.MESSAGE and not e.data.get("partial"):
            response_text += e.data.get("text", "")

    assistant_msg = Message(
        session_id=session.id,
        role="assistant",
        content=response_text,
        events=events,
    )
    await handler.message_repo.create(assistant_msg)

    all_messages = await handler.message_repo.get_by_session(session.id)
    assert len(all_messages) == 2
    assert all_messages[0].role == "user"
    assert all_messages[1].role == "assistant"


@pytest.mark.asyncio
async def test_e2e_provider_list_models(test_config, test_db, test_registry):
    provider = test_registry.require("test")
    models = await provider.list_models()
    assert "test-model" in models


@pytest.mark.asyncio
async def test_e2e_provider_validate(test_config, test_db, test_registry):
    provider = test_registry.require("test")
    valid = await provider.validate()
    assert valid is True


@pytest.mark.asyncio
async def test_e2e_config_bootstrap(temp_dir):
    from zenith.config.loader import create_default_config, load_config
    config_path = create_default_config(str(temp_dir))
    assert config_path.exists()
    config = load_config(str(temp_dir))
    assert config.active_provider == "openai"


@pytest.mark.asyncio
async def test_e2e_error_handling():
    from zenith.core.errors import ProviderError, ToolError, ConfigError
    try:
        raise ProviderError("test error", provider="openai")
    except ProviderError as e:
        assert e.code == "PROVIDER_ERROR"
        assert e.provider == "openai"
        assert e.recoverable is True

    try:
        raise ConfigError("bad config")
    except ConfigError as e:
        assert e.code == "CONFIG_ERROR"
        assert e.recoverable is False
