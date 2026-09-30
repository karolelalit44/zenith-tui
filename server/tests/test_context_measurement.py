"""How context occupancy is measured.

Occupancy drives every context decision â€” when to prune, when to fold, when to
refuse the turn â€” so the number has to describe what the window actually holds.
Three ways it used to understate that, each asserted here:

* tool-call arguments were never counted, which for a mutating tool is the whole
  payload;
* the tool-schema block belongs to no message at all and was not counted;
* the provider's own figure, the most accurate one available, was never used.

The anchor tests additionally pin the property that makes anchoring safe: a
rebuilt list shares no prefix with the one the provider last billed, so an
anchor from before a rebuild must not be reused across it.
"""

from __future__ import annotations

import pytest

from server.agents.context import ContextManager
from server.agents.context_diagnostics import ContextDiagnostics
from server.config.constants import DEFAULT_CONTEXT_WINDOW
from server.config.constants.context import default_max_tokens_for_context
from server.config.settings import AppSettings
from server.storage.usage_store import REINVOCATION_ALERT_RATE, session_context_view

MODEL = "gpt-4"


def _manager(**overrides) -> ContextManager:
    return ContextManager(
        AppSettings(max_context_tokens=DEFAULT_CONTEXT_WINDOW, repo_map_enabled=False, **overrides)
    )


def _write_call(payload_chars: int = 4000) -> dict:
    return {
        "role": "assistant",
        "content": "writing",
        "tool_calls": [
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "file_write", "arguments": {"content": "x" * payload_chars}},
            }
        ],
    }


class TestMessageTokenCounting:
    def test_tool_call_arguments_are_counted(self):
        """A mutating tool's arguments are the payload, and they are billed."""
        ctx = _manager()
        plain = ctx.usage_tokens([{"role": "assistant", "content": "ok"}], MODEL)
        with_call = ctx.usage_tokens([_write_call()], MODEL)
        assert with_call > plain + 500

    def test_tool_call_count_scales_with_payload(self):
        ctx = _manager()
        small = ctx.usage_tokens([_write_call(100)], MODEL)
        large = ctx.usage_tokens([_write_call(8000)], MODEL)
        assert large > small * 2

    def test_harness_metadata_is_not_counted(self):
        """Private loop keys never reach the provider, so they cost nothing."""
        ctx = _manager()
        base = {"role": "user", "content": "[Tool: grep | Status: SUCCESS]\n3 matches"}
        annotated = dict(
            base,
            tool_name="grep",
            digest="grep: 3 matches",
            salvage_digest="grep: ok",
            time="compacted",
            is_digested=True,
        )
        assert ctx.usage_tokens([base], MODEL) == ctx.usage_tokens([annotated], MODEL)

    def test_list_content_is_measured_as_text_not_scaffolding(self):
        """Typed content parts are billed as prose, not as their JSON envelope."""
        ctx = _manager()
        plain = ctx.usage_tokens([{"role": "user", "content": "alpha beta gamma"}], MODEL)
        parts = ctx.usage_tokens(
            [{"role": "user", "content": [{"type": "text", "text": "alpha beta gamma"}]}], MODEL
        )
        assert abs(plain - parts) <= 8

    def test_non_dict_entries_are_skipped_not_fatal(self):
        ctx = _manager()
        assert ctx.usage_tokens([{"role": "user", "content": "x"}, "not-a-dict"], MODEL) > 0


class TestAuxToolSchemaBudget:
    def test_aux_is_included_without_an_anchor(self):
        ctx = _manager()
        msg = [{"role": "user", "content": "hi"}]
        before = ctx.usage_tokens(msg, MODEL)
        ctx.set_aux_tokens(4000)
        assert ctx.usage_tokens(msg, MODEL) == before + 4000

    def test_aux_is_never_negative(self):
        ctx = _manager()
        ctx.set_aux_tokens(-500)
        assert ctx.aux_tokens == 0


class TestProviderAnchoring:
    def test_anchor_supplies_the_prefix_and_the_tail_is_estimated(self):
        ctx = _manager()
        ctx.record_usage_anchor(1, 50_000)
        usage = ctx.measure(
            [{"role": "user", "content": "a"}, {"role": "user", "content": "b"}], MODEL
        )
        assert usage.source == "provider"
        assert usage.anchor_index == 1
        # The provider's figure, plus only the one message added after it.
        assert 50_000 < usage.tokens < 50_100

    def test_schema_block_inside_the_anchor_is_not_charged_twice(self):
        ctx = _manager()
        ctx.set_aux_tokens(4000)
        ctx.record_usage_anchor(1, 50_000)
        usage = ctx.measure([{"role": "user", "content": "a"}], MODEL)
        assert usage.tokens < 50_100

    def test_schema_growth_after_the_anchor_is_charged(self):
        ctx = _manager()
        ctx.set_aux_tokens(4000)
        ctx.record_usage_anchor(1, 50_000)
        ctx.set_aux_tokens(6500)
        usage = ctx.measure([{"role": "user", "content": "a"}], MODEL)
        assert 50_000 + 2500 <= usage.tokens < 50_000 + 2600

    def test_rebuild_invalidates_the_anchor(self):
        """A rebuilt list shares no prefix with the last billed request."""
        ctx = _manager()
        prefix = [{"role": "user", "content": str(i)} for i in range(4)]
        ctx.record_usage_anchor(4, 50_000)
        assert ctx.measure(prefix, MODEL).source == "provider"
        ctx.build_messages([], "system", "hello", MODEL)
        assert ctx.measure(prefix, MODEL).source == "estimated"

    def test_zero_usage_does_not_anchor(self):
        ctx = _manager()
        ctx.record_usage_anchor(4, 0)
        assert ctx.measure([{"role": "user", "content": "a"}], MODEL).source == "estimated"

    def test_anchor_beyond_the_list_is_ignored(self):
        ctx = _manager()
        ctx.record_usage_anchor(99, 50_000)
        assert ctx.measure([{"role": "user", "content": "a"}], MODEL).source == "estimated"

    def test_anchoring_never_makes_occupancy_exceed_a_local_estimate(self):
        """An anchor must be a correction, not an inflation of the real figure."""
        ctx = _manager()
        messages = [{"role": "user", "content": "hello world"}]
        local = ctx.measure(messages, MODEL).tokens
        ctx.record_usage_anchor(len(messages), local)
        assert ctx.measure(messages, MODEL).tokens == local


class TestGenerationCeiling:
    @pytest.mark.parametrize(
        "window,ceiling",
        [
            (4000, 2000),
            (8192, 4096),
            (128_000, 32_768),
            (10_000_000, 32_768),
        ],
    )
    def test_ceiling_is_a_share_of_the_window(self, window, ceiling):
        assert default_max_tokens_for_context(window) == ceiling

    def test_ceiling_never_exceeds_the_window(self):
        """A ceiling larger than the window leaves no room for the prompt."""
        for window in (512, 1024, 2000, 4000, 8192):
            assert default_max_tokens_for_context(window) <= window

    def test_unknown_window_falls_back_to_the_configured_default(self):
        from server.config.constants import DEFAULT_LLM_MAX_TOKENS

        assert default_max_tokens_for_context(0) == DEFAULT_LLM_MAX_TOKENS


class TestDiagnostics:
    def test_first_call_is_not_a_reinvocation(self):
        d = ContextDiagnostics()
        assert d.record_tool_call("grep", '{"q":"x"}') is False
        assert d.reinvocation_rate == 0.0

    def test_repeated_signature_counts_once_per_repeat(self):
        d = ContextDiagnostics()
        for _ in range(3):
            d.record_tool_call("grep", '{"q":"x"}')
        assert d.tool_calls == 3
        assert d.reinvocations == 2
        # Rounded: the rate is reported to a UI, and a long float tail has no
        # meaning at that resolution.
        assert d.reinvocation_rate == 0.6667

    def test_same_args_under_a_different_tool_are_distinct(self):
        d = ContextDiagnostics()
        d.record_tool_call("grep", '{"p":"x"}')
        assert d.record_tool_call("glob", '{"p":"x"}') is False

    def test_rate_is_zero_without_calls(self):
        assert ContextDiagnostics().reinvocation_rate == 0.0

    def test_cache_rate_is_a_ratio_of_billed_prompt_tokens(self):
        d = ContextDiagnostics()
        d.record_cache_usage({"prompt_tokens": 20_000, "cached_tokens": 15_000})
        assert d.cache_hit_rate == pytest.approx(0.75)

    def test_cache_rate_is_zero_without_a_prompt_measurement(self):
        assert ContextDiagnostics().cache_hit_rate == 0.0
        d = ContextDiagnostics()
        d.record_cache_usage(None)
        assert d.cache_hit_rate == 0.0

    def test_savings_accumulate_and_reject_negatives(self):
        d = ContextDiagnostics()
        d.record_ladder_savings(100)
        d.record_ladder_savings(-50)
        d.record_dedup_savings(30)
        payload = d.as_dict()
        assert payload["ladder_saved_tokens"] == 100
        assert payload["dedup_saved_tokens"] == 30


class TestSessionDiagnostics:
    def test_session_aggregates_turn_deltas(self):
        rows = [
            {
                "prompt_tokens": 10_000,
                "cache_read_tokens": 8_000,
                "diagnostics": {"tool_calls": 10, "reinvocations": 1, "ladder_saved_tokens": 500},
            },
            {
                "prompt_tokens": 30_000,
                "cache_read_tokens": 3_000,
                "diagnostics": {"tool_calls": 30, "reinvocations": 3, "ladder_saved_tokens": 100},
            },
        ]
        view = session_context_view(rows)
        assert view["tool_calls"] == 40
        assert view["reinvocations"] == 4
        assert view["reinvocation_rate"] == pytest.approx(0.1)
        assert view["ladder_saved_tokens"] == 600

    def test_cache_rate_is_ratio_of_sums_not_mean_of_ratios(self):
        """A 100-token turn must not weigh as much as a 100 000-token one."""
        rows = [
            {"prompt_tokens": 100, "cache_read_tokens": 0, "diagnostics": {}},
            {"prompt_tokens": 99_900, "cache_read_tokens": 89_900, "diagnostics": {}},
        ]
        assert session_context_view(rows)["cache_hit_rate"] == pytest.approx(0.899)

    def test_rows_without_diagnostics_are_skipped(self):
        assert session_context_view([{"prompt_tokens": 5}])["tool_calls"] == 0

    def test_alert_flag_follows_the_rate(self):
        def row(rate_hits: int, calls: int) -> dict:
            return {"diagnostics": {"tool_calls": calls, "reinvocations": rate_hits}}

        assert session_context_view([row(1, 100)])["reinvocation_alert"] is False
        assert session_context_view([row(20, 100)])["reinvocation_alert"] is True

    def test_alert_threshold_is_a_documented_constant(self):
        """The alert boundary is one number, not a per-call-site guess."""
        below = {"tool_calls": 1000, "reinvocations": round(1000 * REINVOCATION_ALERT_RATE)}
        above = {"tool_calls": 1000, "reinvocations": round(1000 * REINVOCATION_ALERT_RATE) + 1}
        assert session_context_view([{"diagnostics": below}])["reinvocation_alert"] is False
        assert session_context_view([{"diagnostics": above}])["reinvocation_alert"] is True
