"""Compaction passes bound tool results identically.

``prune_inflight_messages``, ``prune_tool_outputs`` and ``compact_live_tail`` all
route through ``bound_tool_message``. These tests pin that shared rule plus each
pass's own contract: in-place mutation, reported savings, and idempotence.
"""

from server.agents.compaction import bound_tool_message, prune_inflight_messages
from server.agents.compaction_service import (
    TAIL_TRIM_MAX_CHARS,
    TOOL_PREVIEW_MAX_CHARS,
    compact_live_tail,
    prune_tool_outputs,
)
from server.config.constants import CHARS_PER_TOKEN

HEAD = "[Tool: glob | Status: SUCCESS]"


def tool_msg(body: str, *, digest: str | None = None, tool_name: str = "glob") -> dict:
    msg = {
        "role": "user",
        "content": f"{HEAD}\n{body}",
        "tool_name": tool_name,
    }
    if digest is not None:
        msg["digest"] = digest
    return msg


class TestBoundToolMessage:
    def test_prefers_digest_over_trimming(self):
        msg = tool_msg("x" * 5000, digest=f"{HEAD} Found 5000 files")
        removed = bound_tool_message(msg, TOOL_PREVIEW_MAX_CHARS)
        assert msg["content"] == f"{HEAD} Found 5000 files"
        assert msg["time"] == "compacted"
        assert removed > 0

    def test_trims_when_no_digest(self):
        msg = tool_msg("x" * 5000)
        removed = bound_tool_message(msg, TOOL_PREVIEW_MAX_CHARS)
        assert msg["content"].startswith(HEAD)
        assert "truncated" in msg["content"]
        assert msg["time"] == "compacted"
        assert removed > 0

    def test_preserved_tools_are_never_digested(self):
        """file_read/todo carry the task's real content; a digest would destroy it."""
        for tool in ("file_read", "todo"):
            msg = tool_msg("important payload", digest="hollow digest", tool_name=tool)
            bound_tool_message(msg, TOOL_PREVIEW_MAX_CHARS)
            assert msg["content"] == f"{HEAD}\nimportant payload"

    def test_within_budget_message_is_untouched(self):
        msg = tool_msg("short body")
        assert bound_tool_message(msg, TOOL_PREVIEW_MAX_CHARS) == 0
        assert "time" not in msg

    def test_head_line_is_never_truncated(self):
        long_head = f"[Tool: {'g' * 3000} | Status: SUCCESS]"
        msg = {"role": "user", "content": f"{long_head}\n{'x' * 5000}"}
        bound_tool_message(msg, TOOL_PREVIEW_MAX_CHARS)
        assert msg["content"].startswith(long_head)

    def test_non_str_content_is_ignored(self):
        msg = {"role": "user", "content": None, "digest": "d"}
        assert bound_tool_message(msg, TOOL_PREVIEW_MAX_CHARS) == 0


class TestPruneToolOutputs:
    def test_compacts_in_place_and_reports_saving(self):
        """The boundary counts back over recent user turns; an old tool result
        sitting behind them is what gets compacted."""
        old = tool_msg("y" * 5000, digest="short digest")
        fresh = tool_msg("keep me intact")
        messages = [
            old,
            {"role": "user", "content": "turn 2"},
            {"role": "user", "content": "turn 3"},
            {"role": "user", "content": "turn 4"},
            fresh,
        ]
        stats = prune_tool_outputs(messages, keep_turns=2)

        assert old["content"] == "short digest"
        assert stats["count"] == 1
        assert stats["chars_removed"] > 0
        assert stats["tokens_saved"] == stats["chars_removed"] // CHARS_PER_TOKEN
        assert fresh["content"] == f"{HEAD}\nkeep me intact"

    def test_is_idempotent(self):
        messages = [
            tool_msg("z" * 5000, digest="short digest"),
            {"role": "user", "content": "another turn"},
            {"role": "user", "content": "a third turn"},
        ]
        first = prune_tool_outputs(messages, keep_turns=1)
        second = prune_tool_outputs(messages, keep_turns=1)
        assert first["count"] == 1
        assert second["count"] == 0

    def test_empty_list_returns_zeroed_stats(self):
        assert prune_tool_outputs([]) == {"count": 0, "chars_removed": 0, "tokens_saved": 0}


class TestCompactLiveTail:
    def test_compacts_the_whole_tail_in_place(self):
        digested = tool_msg("q" * 5000, digest="live digest")
        trimmed = tool_msg("w" * (TAIL_TRIM_MAX_CHARS * 3))
        messages = [digested, trimmed]
        compact_live_tail(messages)
        assert digested["content"] == "live digest"
        assert "truncated" in trimmed["content"]

    def test_ignores_non_tool_messages(self):
        messages = [{"role": "user", "content": "[assistant prose]\n" + "x" * 5000}]
        compact_live_tail(messages)
        assert "time" not in messages[0]


class TestSharedAcrossCallSites:
    def test_every_pass_bounds_a_message_the_same_way(self):
        """The three passes must not drift: one rule, one result, one saving."""
        def fresh() -> list[dict]:
            return [
                tool_msg("p" * 4000, digest="canonical digest"),
                tool_msg("n" * 4000),
            ]

        via_bound = [dict(m) for m in fresh()]
        expected = [bound_tool_message(m, TOOL_PREVIEW_MAX_CHARS) for m in via_bound]

        inflight, inflight_stats = prune_inflight_messages(
            fresh(), keep_latest_tools=0, max_output=TOOL_PREVIEW_MAX_CHARS
        )
        assert [m["content"] for m in inflight] == [m["content"] for m in via_bound]
        assert inflight_stats.chars_removed == sum(expected)

        historical = fresh()
        hist_stats = prune_tool_outputs(historical, keep_turns=0)
        assert [m["content"] for m in historical] == [m["content"] for m in via_bound]
        assert hist_stats["chars_removed"] == sum(expected)

        live = fresh()
        compact_live_tail(live)
        # compact_live_tail bounds the tail to a tighter budget than the
        # historical pass, so only the digest-collapsed message must match
        # exactly; the trimmed one is bounded harder by design.
        assert live[0]["content"] == via_bound[0]["content"]

    def test_keep_latest_tools_zero_prunes_everything(self):
        """``tool_indices[:-0]`` is empty; 0 must mean prune all, not prune none."""
        messages = [tool_msg("r" * 3000, digest=f"d{i}") for i in range(3)]
        pruned, stats = prune_inflight_messages(messages, keep_latest_tools=0)
        assert stats.trimmed is True
        assert [m["content"] for m in pruned] == ["d0", "d1", "d2"]

    def test_keep_latest_tools_protects_the_tail(self):
        messages = [tool_msg("s" * 3000, digest=f"e{i}") for i in range(4)]
        protected = [messages[2]["content"], messages[3]["content"]]
        pruned, _ = prune_inflight_messages(messages, keep_latest_tools=2)
        assert [m["content"] for m in pruned] == ["e0", "e1", *protected]