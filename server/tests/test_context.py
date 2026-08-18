from server.agents.context import ContextManager, TokenInfo
from server.config.constants import DEFAULT_CONTEXT_WINDOW, HARD_STOP_USAGE_RATIO
from server.config.settings import AppSettings
from server.domain.message import Message, ToolCall


class TestContextManager:
    def test_count_messages_skips_non_dict_entries(self):
        config = AppSettings(max_context_tokens=DEFAULT_CONTEXT_WINDOW, repo_map_enabled=False)
        ctx = ContextManager(config)
        mixed = [
            {"role": "user", "content": "hello world"},
            "stray raw string",
            {"role": "assistant", "content": "hi"},
        ]
        assert ctx.usage_tokens(mixed, "gpt-4") > 0
        count = ctx.token_counter.count_messages(mixed, "gpt-4")
        assert count > 0

    def test_build_messages_basic(self):
        config = AppSettings(max_context_tokens=DEFAULT_CONTEXT_WINDOW, repo_map_enabled=False)
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
        # Phase 2: the previous user *prompt* is never re-sent; only the latest is (T5).
        assert len(messages) == 3
        contents = [m["content"] for m in messages]
        assert "Hello" not in contents
        assert contents[-1] == "How are you?"

    def test_build_messages_drops_older_user_prompts_keeps_latest(self):
        config = AppSettings(max_context_tokens=DEFAULT_CONTEXT_WINDOW, repo_map_enabled=False)
        ctx = ContextManager(config)
        history = [
            Message(session_id="s1", role="user", content="OLD prompt 1"),
            Message(session_id="s1", role="assistant", content="Interim assistant"),
            Message(session_id="s1", role="user", content="OLD prompt 2"),
            Message(session_id="s1", role="assistant", content="worker hand-off"),
        ]
        messages = ctx.build_messages(history, "System.", "LATEST.", "gpt-4")
        assert "LATEST." in [m["content"] for m in messages]
        assert messages[-1]["content"] == "LATEST."
        # No old user prompt may appear in the *history-derived* portion (everything before T5).
        for m in messages[:-1]:
            if m["role"] == "user":
                assert "[Tool:" in m["content"] or m["content"] in (
                    "[Previous conversation summary]",
                )
        # Assistant hand-off / worker content is preserved.
        assert any(m["role"] == "assistant" for m in messages)

    def test_build_messages_keeps_tool_result_that_is_role_user(self):
        config = AppSettings(max_context_tokens=DEFAULT_CONTEXT_WINDOW, repo_map_enabled=False)
        ctx = ContextManager(config)
        history = [
            Message(session_id="s1", role="user", content="OLD prompt"),
            Message(session_id="s1", role="user", content="[Tool: bash | Status: SUCCESS] done"),
        ]
        messages = ctx.build_messages(history, "System.", "Continue.", "gpt-4")
        joined = " ".join(str(m.get("content")) for m in messages)
        assert "[Tool: bash" in joined  # tool result preserved
        assert "OLD prompt" not in joined  # real prompt dropped

    def test_build_messages_with_summary(self):
        config = AppSettings(max_context_tokens=DEFAULT_CONTEXT_WINDOW, repo_map_enabled=False)
        ctx = ContextManager(config)
        history = [Message(session_id="s1", role="user", content="Hello")]
        messages = ctx.build_messages(
            history, "System.", "New prompt.", "gpt-4", summary="Previous topic was Python."
        )
        assert messages[0]["role"] == "system"
        assert "Previous topic was Python." in messages[1]["content"]
        assert messages[-1]["content"] == "New prompt."

    def test_build_messages_respects_token_budget(self):
        config = AppSettings(max_context_tokens=1000, repo_map_enabled=False)
        ctx = ContextManager(config)
        history = [
            Message(session_id="s1", role="user", content="x " * 500),
            Message(session_id="s1", role="assistant", content="y " * 500),
            Message(session_id="s1", role="user", content="z " * 500),
        ]
        messages = ctx.build_messages(history, "System.", "New.", "gpt-4")
        assert messages[0]["role"] == "system"
        assert messages[-1]["content"] == "New."

    def test_build_messages_empty_history(self):
        config = AppSettings(max_context_tokens=DEFAULT_CONTEXT_WINDOW, repo_map_enabled=False)
        ctx = ContextManager(config)
        messages = ctx.build_messages([], "System.", "Hello.", "gpt-4")
        assert len(messages) == 2

    def test_build_messages_keeps_tool_call_with_results(self):
        config = AppSettings(max_context_tokens=DEFAULT_CONTEXT_WINDOW, repo_map_enabled=False)
        ctx = ContextManager(config)
        tc = ToolCall(id="call_1", name="bash", arguments={"command": "ls"})
        history = [
            Message(session_id="s1", role="assistant", content="", tool_calls=[tc]),
            Message(session_id="s1", role="tool", content="file.txt"),
        ]
        messages = ctx.build_messages(history, "System.", "Next.", "gpt-4")
        roles = [m["role"] for m in messages]
        assert "tool" in roles
        idx = roles.index("tool")
        assert roles[idx - 1] == "assistant"
        assert messages[idx]["content"] == "file.txt"

    def test_build_messages_never_orphans_tool_result(self):
        config = AppSettings(max_context_tokens=8000, repo_map_enabled=False)
        ctx = ContextManager(config)
        tc = ToolCall(id="call_2", name="file_read", arguments={"filepath": "a.py"})
        history = [
            Message(session_id="s1", role="assistant", content="x " * 12000, tool_calls=[tc]),
            Message(session_id="s1", role="tool", content="tiny result"),
            Message(session_id="s1", role="user", content="next"),
            Message(session_id="s1", role="assistant", content="done"),
        ]
        messages = ctx.build_messages(history, "System.", "More.", "gpt-4")
        roles = [m["role"] for m in messages]
        assert "tool" not in roles
        for i, role in enumerate(roles):
            if role == "tool":
                assert roles[i - 1] == "assistant"

    def test_should_summarize(self):
        config = AppSettings(max_context_tokens=100, context_compaction_threshold=0.5)
        ctx = ContextManager(config)
        messages = [{"role": "user", "content": "x " * 200}]
        assert ctx.should_summarize(messages, "gpt-4") is True

    def test_should_not_summarize_small_context(self):
        config = AppSettings(max_context_tokens=DEFAULT_CONTEXT_WINDOW)
        ctx = ContextManager(config)
        messages = [{"role": "user", "content": "Hello"}]
        assert ctx.should_summarize(messages, "gpt-4") is False

    def test_get_token_info(self):
        config = AppSettings(max_context_tokens=DEFAULT_CONTEXT_WINDOW)
        ctx = ContextManager(config)
        messages = [{"role": "user", "content": "Hello, World!"}]
        info = ctx.get_token_info(messages, "unknown-model")
        assert isinstance(info, TokenInfo)
        assert info.used > 0
        assert info.remaining < DEFAULT_CONTEXT_WINDOW
        assert info.total == DEFAULT_CONTEXT_WINDOW
        assert 0 < info.percent < 1

    def test_count_tokens(self):
        config = AppSettings(max_context_tokens=DEFAULT_CONTEXT_WINDOW)
        ctx = ContextManager(config)
        tokens = ctx.count_tokens("Hello, World!", "gpt-4")
        assert tokens > 0


class _FakeUsageProvider:
    def __init__(self, total_tokens: int = 0):
        self._cumulative_usage = {"total_tokens": total_tokens}


class TestUsageBasedTriggers:
    def test_usage_tokens_prefers_provider_report(self):
        ctx = ContextManager(AppSettings(max_context_tokens=DEFAULT_CONTEXT_WINDOW))
        provider = _FakeUsageProvider(total_tokens=9999)
        tokens = ctx.usage_tokens([], "gpt-4", provider)
        assert tokens == 9999

    def test_usage_tokens_falls_back_to_estimation(self):
        ctx = ContextManager(AppSettings(max_context_tokens=DEFAULT_CONTEXT_WINDOW))
        tokens = ctx.usage_tokens([{"role": "user", "content": "x " * 100}], "gpt-4", None)
        assert 0 < tokens < 9999

    def test_usage_tokens_ignores_zero_report(self):
        ctx = ContextManager(AppSettings(max_context_tokens=DEFAULT_CONTEXT_WINDOW))
        provider = _FakeUsageProvider(total_tokens=0)
        tokens = ctx.usage_tokens([{"role": "user", "content": "y " * 100}], "gpt-4", provider)
        assert tokens > 0

    def test_should_summarize_when_used_near_limit(self):
        config = AppSettings(max_context_tokens=DEFAULT_CONTEXT_WINDOW)
        ctx = ContextManager(config)
        provider = _FakeUsageProvider(total_tokens=120000)
        assert ctx.should_summarize([], "gpt-4", provider) is True

    def test_should_summarize_false_when_low_usage(self):
        config = AppSettings(max_context_tokens=DEFAULT_CONTEXT_WINDOW)
        ctx = ContextManager(config)
        provider = _FakeUsageProvider(total_tokens=1000)
        assert ctx.should_summarize([], "gpt-4", provider) is False

    def test_get_token_info_uses_reported_usage(self):
        config = AppSettings(max_context_tokens=DEFAULT_CONTEXT_WINDOW)
        ctx = ContextManager(config)
        provider = _FakeUsageProvider(total_tokens=64000)
        info = ctx.get_token_info([], "no-such-model", provider)
        assert info.used == 64000
        assert info.remaining == 64000
        assert abs(info.percent - 0.5) < 0.01


class TestCompactionWatermark:
    def test_should_summarize_follows_config_threshold(self):
        config = AppSettings(
            max_context_tokens=DEFAULT_CONTEXT_WINDOW, context_compaction_threshold=0.5
        )
        ctx = ContextManager(config)
        provider = _FakeUsageProvider(total_tokens=64000)
        assert ctx.should_summarize([], "gpt-4", provider) is True

    def test_should_not_summarize_below_config_threshold(self):
        config = AppSettings(
            max_context_tokens=DEFAULT_CONTEXT_WINDOW, context_compaction_threshold=0.6
        )
        ctx = ContextManager(config)
        provider = _FakeUsageProvider(total_tokens=64000)
        assert ctx.should_summarize([], "gpt-4", provider) is False

    def test_is_context_exhausted_at_hard_stop_ratio(self):
        config = AppSettings(max_context_tokens=DEFAULT_CONTEXT_WINDOW)
        ctx = ContextManager(config)
        boundary = int(DEFAULT_CONTEXT_WINDOW * HARD_STOP_USAGE_RATIO)
        assert (
            ctx.is_context_exhausted([], "gpt-4", _FakeUsageProvider(total_tokens=boundary)) is True
        )
        assert (
            ctx.is_context_exhausted([], "gpt-4", _FakeUsageProvider(total_tokens=boundary - 1))
            is False
        )

    def test_is_context_exhausted_false_without_provider_report(self):
        config = AppSettings(max_context_tokens=DEFAULT_CONTEXT_WINDOW)
        ctx = ContextManager(config)
        assert ctx.is_context_exhausted([{"role": "user", "content": "hi"}], "gpt-4") is False
