import asyncio

import pytest

from server.domain.enums import AgentRole, DeliveryMode, RiskLevel, ScenarioMode
from server.domain.errors import (
    ConfigError,
    ProviderError,
    RateLimitError,
    SessionNotFound,
    ZenithError,
)
from server.domain.events import AsyncEventBus, Event, EventBus, EventKind
from server.domain.message import Message, ToolCall
from server.domain.session import Session


class TestDomainEnums:
    def test_scenario_mode_values(self):
        assert ScenarioMode.BUILD.value == "build"
        assert ScenarioMode.PLAN.value == "plan"

    def test_risk_level_values(self):
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.HIGH.value == "high"

    def test_agent_role_values(self):
        assert AgentRole.CODER.value == "coder"

    def test_delivery_mode_values(self):
        assert DeliveryMode.LOSSY.value == "lossy"
        assert DeliveryMode.BLOCKING.value == "blocking"


class TestAsyncEventBus:
    def test_event_bus_cannot_instantiate(self):
        with pytest.raises(TypeError):
            EventBus()

    @pytest.mark.asyncio
    async def test_publish_subscribe(self):
        bus = AsyncEventBus()
        sub = bus.subscribe()
        event = Event(kind=EventKind.MESSAGE, data={"text": "hi"})
        bus.publish(event)
        received = await sub.next(timeout=0.1)
        assert received is not None
        assert received.kind == EventKind.MESSAGE
        sub.cancel()

    @pytest.mark.asyncio
    async def test_subscribe_with_filter(self):
        bus = AsyncEventBus()
        sub = bus.subscribe(event_type=EventKind.ERROR)
        bus.publish(Event(kind=EventKind.MESSAGE, data={}))
        bus.publish(Event(kind=EventKind.ERROR, data={"msg": "fail"}))
        received = await sub.next(timeout=0.1)
        assert received is not None
        assert received.kind == EventKind.ERROR
        sub.cancel()

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        bus = AsyncEventBus()
        sub = bus.subscribe()
        sub.cancel()
        bus.publish(Event(kind=EventKind.MESSAGE, data={}))
        received = await sub.next(timeout=0.05)
        assert received is None

    def test_lossy_drops_full_queue_but_blocking_raises(self):
        bus = AsyncEventBus(buffer_size=1)
        bus.subscribe()
        bus.publish(Event(kind=EventKind.MESSAGE, data={"seq": 1}))
        bus.publish(Event(kind=EventKind.MESSAGE, data={"seq": 2}), mode=DeliveryMode.LOSSY)
        with pytest.raises(asyncio.QueueFull):
            bus.publish(Event(kind=EventKind.MESSAGE, data={"seq": 3}), mode=DeliveryMode.BLOCKING)


class TestMessage:
    def test_create_message(self):
        msg = Message(role="user", content="hello", session_id="s1")
        assert msg.role == "user"
        assert msg.content == "hello"
        assert msg.id

    def test_message_with_tool_calls(self):
        tc = ToolCall(id="call_1", name="bash", arguments={"command": "ls"})
        msg = Message(role="assistant", content="", session_id="s1", tool_calls=[tc])
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].name == "bash"

    def test_message_with_parent(self):
        msg = Message(role="user", content="hi", session_id="s1", parent_message_id="msg_parent")
        assert msg.parent_message_id == "msg_parent"


class TestSession:
    def test_create_session(self):
        session = Session(title="Test")
        assert session.title == "Test"
        assert session.status == "idle"


class TestErrors:
    def test_zenith_error(self):
        err = ZenithError("test error", code="TEST")
        assert str(err) == "test error"
        assert err.code == "TEST"

    def test_config_error(self):
        err = ConfigError("bad config")
        assert isinstance(err, ZenithError)

    def test_provider_error(self):
        err = ProviderError("api fail", provider="openai", recoverable=True)
        assert err.provider == "openai"
        assert err.recoverable is True

    def test_session_not_found(self):
        err = SessionNotFound("sess_123")
        assert "sess_123" in str(err)

    def test_rate_limit_error(self):
        err = RateLimitError("rate limited", retry_after=5.0)
        assert err.retry_after == 5.0
