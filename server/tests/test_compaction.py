import pytest

from server.agents.compaction import (
    CompactionStats,
    _find_compaction_cut,
    _find_compaction_cut_budgeted,
    compact_tool_output,
    head_tail_trim,
    strip_ansi,
)
from server.agents.loop import (
    AgentLoop,
    _format_tool_result,
)
from server.config.constants import (
    COMPACTION_KEEP_TAIL,
    MAX_TOOL_OUTPUT_BASELINE,
)
from server.config.providers import ProviderConfig
from server.config.settings import AppSettings
from server.domain.events import EventKind
from server.domain.message import Message, ToolCall
from server.providers import responder as r
from server.providers.base import BaseProvider
from server.toolkit import create_default_registry
from server.toolkit.base import ToolResult


def _big_output(lines: int = 50000, line_len: int = 10) -> str:
    return "\n".join(f"line {i:05d} {'x' * (line_len - 10)}" for i in range(lines))


class TestStripAnsi:
    def test_strips_csi_codes(self):
        text = "\x1b[31mred\x1b[0m plain \x1b[1m\x1b[32mbold green\x1b[0m"
        cleaned, n = strip_ansi(text)
        assert n == 5
        assert "\x1b" not in cleaned
        assert cleaned == "red plain bold green"

    def test_strips_osc_hyperlink(self):
        text = "\x1b]8;;https://example.com\x07link\x1b]8;;\x07"
        cleaned, n = strip_ansi(text)
        assert n == 2
        assert cleaned == "link"

    def test_no_ansi_noop(self):
        cleaned, n = strip_ansi("plain text\nmore")
        assert n == 0
        assert cleaned == "plain text\nmore"


class TestHeadTailTrim:
    def test_under_limit_unchanged(self):
        text, omitted = head_tail_trim("short", 100)
        assert text == "short"
        assert omitted == 0

    def test_keeps_head_and_tail(self):
        text = "A" * 300 + "MID" + "B" * 300
        trimmed, omitted = head_tail_trim(text, 300)
        assert omitted > 0
        assert trimmed.startswith("A" * 199)
        assert trimmed.endswith("B" * 100)
        assert "truncated" in trimmed
        assert "MID" not in trimmed


class TestCompactToolOutput:
    def test_50k_lines_token_drop(self):
        output = _big_output(50000)
        compacted, stats = compact_tool_output(output, max_output=MAX_TOOL_OUTPUT_BASELINE)
        assert stats.original_chars == len(output)
        assert stats.trimmed is True
        assert stats.chars_removed > 0
        assert stats.tokens_saved > 0
        assert len(compacted) < len(output) // 20
        assert compacted.startswith("line 00000")
        assert compacted.rstrip().endswith("line 49999")
        assert "compacted" in stats.reason

    def test_ansi_stripped_and_counted(self):
        output = "\x1b[32m" + "OK\n" * 1000 + "\x1b[0m"
        compacted, stats = compact_tool_output(output, max_output=100000)
        assert stats.ansi_sequences_removed == 2
        assert "\x1b" not in compacted
        assert stats.chars_removed > 0
        assert stats.tokens_saved > 0

    def test_small_output_untouched(self):
        compacted, stats = compact_tool_output("hello world", max_output=MAX_TOOL_OUTPUT_BASELINE)
        assert compacted == "hello world"
        assert stats.trimmed is False
        assert stats.chars_removed == 0
        assert stats.tokens_saved == 0

    def test_stats_dataclass(self):
        assert CompactionStats().tokens_saved == 0


class TestCompactionCutPoint:
    def _history(self, n: int) -> list[Message]:
        return [
            Message(session_id="s", role="user" if i % 2 == 0 else "assistant", content=f"m{i}")
            for i in range(n)
        ]

    def test_short_history_summarizes_everything(self):
        assert _find_compaction_cut(self._history(5), keep_tail=COMPACTION_KEEP_TAIL) == 0

    def test_cut_never_splits_tool_result_exchange(self):
        msgs = self._history(30)
        cut = _find_compaction_cut(msgs, keep_tail=COMPACTION_KEEP_TAIL)
        assert cut > 0
        assert msgs[cut - 1].role != "assistant"
        assert len(msgs) - cut <= COMPACTION_KEEP_TAIL + 1

    def test_cut_prefers_user_boundary(self):
        msgs = self._history(28)
        cut = _find_compaction_cut(msgs, keep_tail=COMPACTION_KEEP_TAIL)
        assert msgs[cut - 1].role == "user"


class TestCompactionCutTokenBudgeted:
    def _history(self, n: int) -> list[Message]:
        return [
            Message(session_id="s", role="user" if i % 2 == 0 else "assistant", content=f"m{i}")
            for i in range(n)
        ]

    def test_keeps_recent_exchanges_within_budget(self):
        msgs = self._history(30)
        cut = _find_compaction_cut_budgeted(msgs, keep_tokens=15, count_fn=lambda m: len(m) + 1)
        assert cut > 0
        tail = msgs[cut:]
        assert sum(len(m.content) + 1 for m in tail) <= 15

    def test_whole_history_fits_returns_zero(self):
        msgs = self._history(4)
        cut = _find_compaction_cut_budgeted(msgs, keep_tokens=100000, count_fn=lambda m: len(m) + 1)
        assert cut == 0

    def test_never_splits_tool_result_group(self):
        msgs = [
            Message(session_id="s", role="user", content="u1"),
            Message(
                session_id="s",
                role="assistant",
                content="call1",
                tool_calls=[ToolCall(id="c1", name="bash", arguments={})],
            ),
            Message(session_id="s", role="tool", content="r1"),
            Message(session_id="s", role="assistant", content="resp1"),
        ]
        cut = _find_compaction_cut_budgeted(msgs, keep_tokens=50, count_fn=lambda m: len(m) + 1)
        kept = msgs[cut:]
        assert not kept or kept[0].role != "tool"

    def test_live_exchange_always_kept_whole(self):
        msgs = [
            Message(session_id="s", role="user", content="old"),
            Message(
                session_id="s",
                role="assistant",
                content="huge " * 200,
                tool_calls=[ToolCall(id="c2", name="bash", arguments={})],
            ),
            Message(session_id="s", role="tool", content="result"),
        ]
        cut = _find_compaction_cut_budgeted(msgs, keep_tokens=10, count_fn=lambda m: len(m) + 1)
        kept = msgs[cut:]
        assert kept[0].role == "assistant"
        assert kept[1].role == "tool"
        assert "old" not in [m.content for m in kept]


class TestFormatToolResultCompaction:
    def test_huge_output_truncated_with_tail(self):
        output = _big_output(50000)
        result = ToolResult(success=True, output=output)
        formatted = _format_tool_result("bash", result)
        assert "SUCCESS" in formatted
        assert "truncated" in formatted
        assert len(formatted) < 20000
        assert formatted.rstrip().endswith("line 49999")

    def test_failure_keeps_error_and_tail(self):
        output = "stdout line\n" * 5000 + "final detail here"
        result = ToolResult(success=False, output=output, error="boom")
        formatted = _format_tool_result("bash", result)
        assert "FAILED" in formatted
        assert "boom" in formatted
        assert "final detail here" in formatted


class TestContextCompactedEvent:
    def test_event_emitted_with_counts(self):
        output = _big_output(50000)
        _, stats = compact_tool_output(output, max_output=MAX_TOOL_OUTPUT_BASELINE)
        ev = r.context_compacted(
            "bash",
            stats.chars_removed,
            stats.tokens_saved,
            stats.reason,
            "sess-1",
            original_chars=stats.original_chars,
            compacted_chars=stats.compacted_chars,
        )
        assert ev.kind.value == "context_compacted"
        assert ev.data["tool"] == "bash"
        assert ev.data["charsRemoved"] > 0
        assert ev.data["tokensSaved"] > 0
        assert ev.data["originalChars"] == stats.original_chars
        assert ev.data["compactedChars"] == stats.compacted_chars

    def test_no_event_for_small_output(self):
        _, stats = compact_tool_output("small", max_output=MAX_TOOL_OUTPUT_BASELINE)
        assert stats.chars_removed == 0


class _BigReadProvider(BaseProvider):
    def __init__(self):
        super().__init__("test", "test-model")
        self.call_count = 0

    async def complete(self, messages: list[dict], tools=None) -> str:
        self.call_count += 1
        if self.call_count == 1:
            return '```tool\n{"tool": "file_read", "params": {"path": "big.txt", "limit": 100000}}\n```'
        return "Done."

    async def stream(
        self, messages: list[dict], tools=None, tool_choice=None, response_format=None
    ):
        response = await self.complete(messages)
        for char in response:
            yield (char, None)

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["test-model"]


class TestLoopTrimsWithFootnote:
    """Per-tool trims are surfaced as a footnote on the tool row - the old
    full-screen CONTEXT_COMPACTED ceremony for every trim was noise."""

    @pytest.mark.asyncio
    async def test_live_turn_trims_and_footnotes(self, temp_dir):
        (temp_dir / "big.txt").write_text(
            "\n".join(f"data line {i:05d}" for i in range(50000)), encoding="utf-8"
        )
        config = AppSettings(
            providers={"test": ProviderConfig(model="test-model", is_active=True)},
            active_provider="test",
            home_dir=str(temp_dir / "test.db"),
            workspace_root=str(temp_dir),
        )
        provider = _BigReadProvider()
        agent = AgentLoop(config, provider, tool_registry=create_default_registry())
        events = []
        async for event in agent.process_prompt("Read big.txt", "s1", [], "build"):
            events.append(event)
        kinds = [e.kind for e in events]
        assert EventKind.TOOL_RESULT in kinds
        # No ceremony for per-tool trims anymore.
        assert not [e for e in events if e.kind == EventKind.CONTEXT_COMPACTED]
        # The trim is disclosed on the tool result row itself.
        results = [e for e in events if e.kind == EventKind.TOOL_RESULT]
        assert results, "tool_result must be present"
        trim = (results[0].data.get("metadata") or {}).get("trim")
        assert trim and trim["charsRemoved"] > 0
        assert events[-1].kind == EventKind.SUCCESS
