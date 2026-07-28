"""Tests for core architecture — domain, events, message, session, errors."""

import pytest
from core.domain import (
    ScenarioMode, RiskLevel, AgentRole, AgentState,
    SessionState, PermissionDecision, DeliveryMode, FinishReason,
)
from core.events import Event, EventKind, AsyncEventBus, Subscription, make_event
from core.message import Message, ToolCall, ToolResult
from core.session import Session
from core.errors import (
    ZenithError, ConfigError, ProviderError, ToolError,
    SessionNotFound, SessionTransitionError, MaxIterationsError,
    RateLimitError, TransportError, AgentError,
)


# ── Domain enums ─────────────────────────────────────────────────────────

class TestDomainEnums:
    def test_scenario_mode_values(self):
        assert ScenarioMode.BUILD.value == "build"
        assert ScenarioMode.PLAN.value == "plan"

    def test_risk_level_values(self):
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.HIGH.value == "high"

    def test_agent_role_values(self):
        assert AgentRole.CODER.value == "coder"

    def test_session_state_values(self):
        assert SessionState.CREATED.value == "created"
        assert SessionState.ACTIVE.value == "active"

    def test_delivery_mode_values(self):
        assert DeliveryMode.LOSSY.value == "lossy"
        assert DeliveryMode.BLOCKING.value == "blocking"


# ── EventBus ─────────────────────────────────────────────────────────────

class TestAsyncEventBus:
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


# ── Message ──────────────────────────────────────────────────────────────

class TestMessage:
    def test_create_message(self):
        msg = Message(role="user", content="hello", session_id="s1")
        assert msg.role == "user"
        assert msg.content == "hello"
        assert msg.id  # UUID string

    def test_message_with_tool_calls(self):
        tc = ToolCall(id="call_1", name="bash", arguments={"command": "ls"})
        msg = Message(role="assistant", content="", session_id="s1", tool_calls=[tc])
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].name == "bash"

    def test_message_with_parent(self):
        msg = Message(role="user", content="hi", session_id="s1", parent_message_id="msg_parent")
        assert msg.parent_message_id == "msg_parent"


# ── Session ──────────────────────────────────────────────────────────────

class TestSession:
    def test_create_session(self):
        session = Session(title="Test")
        assert session.title == "Test"
        assert session.state == SessionState.CREATED

    def test_session_transition(self):
        session = Session(title="Test")
        session.transition(SessionState.ACTIVE)
        assert session.state == SessionState.ACTIVE

    def test_session_invalid_transition(self):
        session = Session(title="Test")
        session.transition(SessionState.ACTIVE)
        with pytest.raises((SessionTransitionError, ValueError)):
            session.transition(SessionState.CREATED)


# ── Errors ───────────────────────────────────────────────────────────────

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
