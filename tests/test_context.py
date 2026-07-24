"""Tests for context window manager and history manager."""

import pytest
from zenith.agent.context import ContextManager, TokenInfo
from zenith.session.history import HistoryManager
from zenith.config.settings import AppSettings
from zenith.core.message import Message
from zenith.providers.base import BaseProvider


class TestContextManager:
    def test_build_messages_basic(self):
        config = AppSettings(max_context_tokens=128000)
        ctx = ContextManager(config)
        history = [
            Message(session_id="s1", role="user", content="Hello"),
            Message(session_id="s1", role="assistant", content="Hi there!"),
        ]
        messages = ctx.build_messages(history, "You are helpful.", "How are you?", "gpt-4")
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are helpful."
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "How are you?"
        assert len(messages) == 4  # system + 2 history + user

    def test_build_messages_with_summary(self):
        config = AppSettings(max_context_tokens=128000)
        ctx = ContextManager(config)
        history = [
            Message(session_id="s1", role="user", content="Hello"),
        ]
        messages = ctx.build_messages(
            history, "System.", "New prompt.", "gpt-4", summary="Previous topic was Python."
        )
        # Should have system + summary exchange + history + user
        assert messages[0]["role"] == "system"
        assert "Previous topic was Python." in messages[1]["content"]
        assert messages[-1]["content"] == "New prompt."

    def test_build_messages_respects_token_budget(self):
        config = AppSettings(max_context_tokens=1000)
        ctx = ContextManager(config)
        # Create a long history that exceeds budget
        history = [
            Message(session_id="s1", role="user", content="x " * 500),
            Message(session_id="s1", role="assistant", content="y " * 500),
            Message(session_id="s1", role="user", content="z " * 500),
        ]
        messages = ctx.build_messages(history, "System.", "New.", "gpt-4")
        # Should drop older messages to stay within budget
        assert messages[0]["role"] == "system"
        assert messages[-1]["content"] == "New."

    def test_build_messages_empty_history(self):
        config = AppSettings(max_context_tokens=128000)
        ctx = ContextManager(config)
        messages = ctx.build_messages([], "System.", "Hello.", "gpt-4")
        assert len(messages) == 2  # system + user

    def test_should_summarize(self):
        config = AppSettings(max_context_tokens=100, summary_threshold=0.5)
        ctx = ContextManager(config)
        # Create messages that exceed threshold
        messages = [{"role": "user", "content": "x " * 200}]
        assert ctx.should_summarize(messages, "gpt-4") is True

    def test_should_not_summarize_small_context(self):
        config = AppSettings(max_context_tokens=128000, summary_threshold=0.8)
        ctx = ContextManager(config)
        messages = [{"role": "user", "content": "Hello"}]
        assert ctx.should_summarize(messages, "gpt-4") is False

    def test_get_token_info(self):
        config = AppSettings(max_context_tokens=128000)
        ctx = ContextManager(config)
        messages = [{"role": "user", "content": "Hello, World!"}]
        info = ctx.get_token_info(messages, "gpt-4")
        assert isinstance(info, TokenInfo)
        assert info.used > 0
        assert info.remaining < 128000
        assert info.total == 128000
        assert 0 < info.percent < 1

    def test_count_tokens(self):
        config = AppSettings(max_context_tokens=128000)
        ctx = ContextManager(config)
        tokens = ctx.count_tokens("Hello, World!", "gpt-4")
        assert tokens > 0


class TestHistoryManager:
    def test_get_recent_messages(self):
        messages = [
            Message(session_id="s1", role="user", content=f"Message {i}")
            for i in range(20)
        ]
        recent = HistoryManager.get_recent_messages(messages, count=5)
        assert len(recent) == 5
        assert recent[0].content == "Message 15"
        assert recent[-1].content == "Message 19"

    def test_get_recent_messages_fewer_than_count(self):
        messages = [
            Message(session_id="s1", role="user", content="Hello"),
        ]
        recent = HistoryManager.get_recent_messages(messages, count=10)
        assert len(recent) == 1

    def test_fallback_summary(self):
        messages = [
            Message(session_id="s1", role="user", content="Hello"),
            Message(session_id="s1", role="assistant", content="Hi there!"),
        ]
        summary = HistoryManager._fallback_summary(messages)
        assert "Hello" in summary
        assert "Hi there!" in summary

    def test_fallback_summary_empty(self):
        summary = HistoryManager._fallback_summary([])
        assert summary == "No prior context available."
