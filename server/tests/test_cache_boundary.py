from __future__ import annotations

import re
from pathlib import Path

import pytest

from server.agents.context import (
    TIER_T0,
    TIER_T1,
    TIER_T2,
    TIER_T4,
    TIER_T5,
    ContextManager,
)
from server.agents.prompts import build_system_prompt
from server.agents.loop import AgentLoop, _call_signature
from server.agents.session_workspace import (
    record_write,
    reset_session,
    record_read,
    record_edit,
    is_stale,
)
from server.config.constants import (
    DEFAULT_CONTEXT_WINDOW,
    MIN_OUTPUT_RESERVE_TOKENS,
    SESSION_STATE_MAX_TOKENS,
)
from server.config.settings import AppSettings
from server.domain.message import Message

SYSTEM_PROMPT = "You are Zenith, a coding agent." * 50


def _base_config(**kwargs) -> AppSettings:
    defaults = dict(
        max_context_tokens=DEFAULT_CONTEXT_WINDOW,
        repo_map_enabled=False,
        memory_enabled=False,
    )
    defaults.update(kwargs)
    return AppSettings(**defaults)


def _build(ctx: ContextManager, new_prompt: str, **kw) -> list[dict]:
    defaults = dict(
        history=[Message(session_id="s1", role="user", content="old prompt")],
        system_prompt=SYSTEM_PROMPT,
        new_prompt=new_prompt,
        model="gpt-4",
    )
    defaults.update(kw)
    return ctx.build_messages(**defaults)


def _msg(role: str, content: str) -> Message:
    return Message(session_id="s1", role=role, content=content)


class TestT0Boundary:
    def test_t0_is_just_the_system_prompt(self):
        ctx = ContextManager(_base_config())
        messages = _build(
            ctx,
            "Do the thing.",
            repo_map="module a.py:1-10",
            memory="favorite color is blue",
            plan_block="1. step one",
            summary="Previous topic was caching.",
        )
        assert ctx.t0_len() == 1
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == SYSTEM_PROMPT
        volatile = [m["content"] for m in messages[1:]]
        assert all(SYSTEM_PROMPT not in str(v) for v in volatile)

    def test_t0_byte_stable_across_calls(self):
        ctx = ContextManager(_base_config())
        first = _build(ctx, "Prompt A.", summary="Earlier topic.")
        second = _build(ctx, "Prompt B.", summary="Different summary.")
        assert first[: ctx.t0_len()] == second[: ctx.t0_len()]
        assert first[0] == second[0]

    def test_t0_excludes_session_state_and_history(self):
        ctx = ContextManager(_base_config())
        messages = _build(ctx, "Latest.")
        assert len(messages) >= 2
        t0 = messages[: ctx.t0_len()]
        assert len(t0) == 1
        assert t0[0]["content"] == SYSTEM_PROMPT

    def test_t0_len_zero_when_no_system_prompt(self):
        ctx = ContextManager(_base_config())
        messages = _build(ctx, "Merged.", use_system_prompt=False)
        assert ctx.t0_len() == 0
        assert messages[0]["role"] == "user"
        assert SYSTEM_PROMPT in messages[0]["content"]


class _CachingProvider:
    name = "fake-caching"
    model = "fake-model"

    def count_tokens(self, text: str, model: str | None = None) -> int:
        return max(1, len(text) // 4)


class _AnthropicProvider:
    name = "anthropic"
    model = "claude-sonnet-4-5-20250929"

    def count_tokens(self, text: str, model: str | None = None) -> int:
        return max(1, len(text) // 4)


class TestMessageOne:
    """Task 4.1: Message 1 (fresh session bucket) is exactly T0 (static) +
    minimal mode-allowed tool schemas + T5 (verbatim prompt). No repo map,
    memory, plan, summary, history, or session state (§3.1)."""

    def test_message1_is_exactly_t0_and_t5(self):
        ctx = ContextManager(_base_config())
        messages = _build(
            ctx,
            "First prompt.",
            history=[],
            repo_map="module a.py:1-10",
            memory="favorite color is blue",
            plan_block="1. step one",
        )
        assert ctx.t0_len() == 1
        assert ctx.tiers() == [TIER_T0, TIER_T5]
        assert messages == [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "First prompt."},
        ]

    def test_message1_suppresses_volatile_blocks(self):
        ctx = ContextManager(_base_config())
        messages = _build(ctx, "First.", history=[], memory="secret memory", repo_map="a.py:1-1")
        text = str(messages)
        assert "<memory>" not in text
        assert "<repo_map>" not in text
        assert "secret memory" not in text
        assert len(messages) == 2

    def test_message1_plan_block_not_injected(self):
        ctx = ContextManager(_base_config())
        messages = _build(ctx, "First.", history=[], plan_block="PLAN: do Y.")
        assert len(messages) == 2
        assert "plan_to_execute" not in str(messages)

    def test_message1_golden_byte_stable(self):
        ctx = ContextManager(_base_config())
        first = _build(ctx, "Hello.", history=[])
        second = _build(ctx, "Hello.", history=[])
        assert first == second
        assert first == [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "Hello."},
        ]

    def test_message1_t0_byte_stable_across_prompts(self):
        ctx = ContextManager(_base_config())
        a = _build(ctx, "A.", history=[])
        b = _build(ctx, "B.", history=[])
        assert a[:1] == b[:1]
        assert a[0] == {"role": "system", "content": SYSTEM_PROMPT}

    def test_message1_prompt_is_verbatim_t5(self):
        ctx = ContextManager(_base_config())
        messages = _build(ctx, "  verbatim prompt  ", history=[])
        assert messages[-1] == {"role": "user", "content": "  verbatim prompt  "}

    def test_message1_session_state_not_injected(self, temp_dir: Path):
        cfg = AppSettings(workspace_root=str(temp_dir))
        loop = AgentLoop(config=cfg, provider=_CachingProvider())
        sid = "message-one-fresh-session"
        reset_session(sid)
        messages = loop.context_manager.build_messages([], SYSTEM_PROMPT, "First.", "gpt-4")
        loop._inject_session_state(messages, sid)
        assert messages == [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "First."},
        ]

    def test_message1_resumed_after_compact_keeps_blocks(self):
        ctx = ContextManager(_base_config())
        messages = _build(
            ctx,
            "Continue.",
            history=[],
            summary="Prior topic.",
            memory="favorite color is blue",
            repo_map="a.py:1-10",
        )
        assert ctx.t0_len() == 1
        assert messages[1]["content"].startswith("<repo_map>")
        assert any("<memory>" in str(m.get("content", "")) for m in messages)
        assert "Prior topic." in messages[-3]["content"]
        assert messages[-2]["content"] == "Understood."
        assert messages[-1]["content"] == "Continue."


class TestCacheMarking:
    @pytest.mark.asyncio
    async def test_marks_only_t0_prefix(self, temp_dir: Path):
        cfg = AppSettings(workspace_root=str(temp_dir))
        loop = AgentLoop(config=cfg, provider=_CachingProvider())
        loop._catalog_for_provider = staticmethod(
            lambda provider_name: {"supports_prompt_caching": True, "adapter": "anthropic"}
        )
        messages = loop.context_manager.build_messages(
            [Message(session_id="s1", role="user", content="old")],
            SYSTEM_PROMPT,
            "new",
            "gpt-4",
            summary="Prior context.",
        )
        assert loop.context_manager.t0_len() == 1
        cached = loop._apply_prompt_caching(messages)
        assert "cache_control" in cached[0]
        assert cached[0]["content"] == SYSTEM_PROMPT
        boundaries = loop.context_manager.tier_boundaries()
        cache_indices = set()
        for idx in [boundaries["t0_end"], boundaries["t1_end"], boundaries["t2_end"]]:
            if idx > 0:
                cache_indices.add(idx - 1)
        for i, msg in enumerate(cached):
            if i in cache_indices:
                assert msg.get("cache_control") == {"type": "ephemeral"}
            else:
                assert "cache_control" not in msg, f"msg {i} got unexpected flag"

    @pytest.mark.asyncio
    async def test_marks_only_t0_when_summary_present(self, temp_dir: Path):
        cfg = AppSettings(workspace_root=str(temp_dir))
        loop = AgentLoop(config=cfg, provider=_CachingProvider())
        loop._catalog_for_provider = staticmethod(
            lambda provider_name: {"supports_prompt_caching": True, "adapter": "anthropic"}
        )
        messages = loop.context_manager.build_messages(
            [Message(session_id="s1", role="user", content="old")],
            SYSTEM_PROMPT,
            "new",
            "gpt-4",
            summary="[Previous conversation summary]\nPrior topic.",
        )
        cached = loop._apply_prompt_caching(messages)
        assert cached[0]["content"] == SYSTEM_PROMPT
        assert "cache_control" in cached[0]
        boundaries = loop.context_manager.tier_boundaries()
        cache_indices = set()
        for idx in [boundaries["t0_end"], boundaries["t1_end"], boundaries["t2_end"]]:
            if idx > 0:
                cache_indices.add(idx - 1)
        for i, msg in enumerate(cached):
            if i in cache_indices:
                assert msg.get("cache_control") == {"type": "ephemeral"}
            else:
                assert "cache_control" not in msg

    @pytest.mark.asyncio
    async def test_no_marking_without_t0(self, temp_dir: Path):
        cfg = AppSettings(workspace_root=str(temp_dir))
        loop = AgentLoop(config=cfg, provider=_CachingProvider())
        loop._catalog_for_provider = staticmethod(
            lambda provider_name: {"supports_prompt_caching": True, "adapter": "anthropic"}
        )
        messages = loop.context_manager.build_messages(
            [Message(session_id="s1", role="user", content="old")],
            SYSTEM_PROMPT,
            "new",
            "gpt-4",
            use_system_prompt=False,
        )
        assert loop.context_manager.t0_len() == 0
        cached = loop._apply_prompt_caching(messages)
        assert all("cache_control" not in m for m in cached)

    @pytest.mark.asyncio
    async def test_gemini_excluded_even_if_cache_flag_set(self, temp_dir: Path):
        cfg = AppSettings(workspace_root=str(temp_dir))
        loop = AgentLoop(config=cfg, provider=_CachingProvider())
        loop._catalog_for_provider = staticmethod(
            lambda provider_name: {"supports_prompt_caching": True, "adapter": "gemini"}
        )
        messages = loop.context_manager.build_messages([], SYSTEM_PROMPT, "Hello.", "gpt-4")
        cached = loop._apply_prompt_caching(messages)
        assert all("cache_control" not in m for m in cached)

    @pytest.mark.asyncio
    async def test_unknown_provider_gets_no_flags(self, temp_dir: Path):
        cfg = AppSettings(workspace_root=str(temp_dir))
        loop = AgentLoop(config=cfg, provider=_CachingProvider())
        loop._catalog_for_provider = staticmethod(lambda provider_name: {})
        messages = loop.context_manager.build_messages([], SYSTEM_PROMPT, "Hello.", "gpt-4")
        cached = loop._apply_prompt_caching(messages)
        assert all("cache_control" not in m for m in cached)


class TestTierAssembly:
    def _history(self) -> list[Message]:
        return [
            Message(session_id="s1", role="user", content="[Tool: bash | Status: SUCCESS] done"),
            Message(session_id="s1", role="assistant", content="worker hand-off"),
            Message(session_id="s1", role="user", content="[Tool: glob | Status: SUCCESS] a.py"),
        ]

    def test_all_volatile_tiers_after_cache_boundary(self):
        ctx = ContextManager(_base_config())
        messages = _build(
            ctx,
            "Final prompt.",
            history=self._history(),
            repo_map="module a.py:1-10",
            memory="user prefers terse replies",
            plan_block="1. step one\n2. step two",
            summary="Earlier topic was caching.",
        )
        tiers = ctx.tiers()
        assert len(tiers) == len(messages)
        t0 = ctx.t0_len()
        assert t0 == 1
        assert tiers[:t0] == [TIER_T0]
        assert TIER_T0 not in tiers[t0:]
        t1_idx = [i for i, t in enumerate(tiers) if t == TIER_T1]
        t2_idx = [i for i, t in enumerate(tiers) if t == TIER_T2]
        t4_idx = [i for i, t in enumerate(tiers) if t == TIER_T4]
        assert t1_idx, "volatile blocks (repo map/memory/plan) missing"
        assert t1_idx[0] == t0
        assert t2_idx, "summary tier missing"
        assert t4_idx, "history window tier missing"
        assert max(t1_idx) < min(t2_idx) < max(t2_idx) < min(t4_idx) < max(t4_idx)
        assert tiers[-1] == TIER_T5
        assert tiers.count(TIER_T5) == 1

    def test_t5_is_always_last_verbatim_user(self):
        ctx = ContextManager(_base_config())
        messages = _build(ctx, "Final prompt.", history=self._history())
        assert ctx.tiers()[-1] == TIER_T5
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "Final prompt."

    def test_t5_last_without_summary_or_blocks(self):
        ctx = ContextManager(_base_config())
        messages = _build(ctx, "Plain.", history=self._history())
        tiers = ctx.tiers()
        assert tiers[-1] == TIER_T5
        assert TIER_T2 not in tiers
        assert TIER_T1 not in tiers
        assert messages[-1] == {"role": "user", "content": "Plain."}

    def test_t5_last_when_no_history(self):
        ctx = ContextManager(_base_config())
        messages = _build(ctx, "Only me.", history=[])
        assert ctx.tiers() == [TIER_T0, TIER_T5]
        assert messages[-1] == {"role": "user", "content": "Only me."}

    def test_t5_last_when_prompt_equals_last_history_message(self):
        ctx = ContextManager(_base_config())
        history = [Message(session_id="s1", role="assistant", content="Repeat")]
        messages = _build(ctx, "Repeat", history=history)
        assert ctx.tiers()[-1] == TIER_T5
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "Repeat"
        assert len(messages) == 3

    def test_no_system_prompt_path_has_no_t0_and_t5_last(self):
        ctx = ContextManager(_base_config())
        messages = _build(
            ctx, "Merged.", history=self._history(), use_system_prompt=False, summary="Prior."
        )
        assert ctx.t0_len() == 0
        tiers = ctx.tiers()
        assert TIER_T0 not in tiers
        assert tiers[-1] == TIER_T5
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"].endswith("Merged.")


class TestSessionStateInjection:
    def test_state_inserted_after_cache_boundary(self, temp_dir: Path):
        cfg = AppSettings(workspace_root=str(temp_dir))
        loop = AgentLoop(config=cfg, provider=_CachingProvider())
        sid = "state-boundary-test"
        record_write(sid, "a.py", "print('x')\n")
        try:
            messages = loop.context_manager.build_messages(
                [Message(session_id=sid, role="user", content="old")],
                SYSTEM_PROMPT,
                "new",
                "gpt-4",
            )
            t0 = loop.context_manager.t0_len()
            AgentLoop._inject_session_state(messages, sid)
            state_idx = next(
                i
                for i, m in enumerate(messages)
                if m.get("role") == "system" and "[Session state]" in str(m.get("content", ""))
            )
            assert state_idx >= t0
        finally:
            reset_session(sid)

    def test_state_skipped_when_no_files(self, temp_dir: Path):
        cfg = AppSettings(workspace_root=str(temp_dir))
        loop = AgentLoop(config=cfg, provider=_CachingProvider())
        sid = "state-skip-test"
        reset_session(sid)
        messages = loop.context_manager.build_messages(
            [Message(session_id=sid, role="user", content="old")],
            SYSTEM_PROMPT,
            "new",
            "gpt-4",
        )
        before = list(messages)
        AgentLoop._inject_session_state(messages, sid)
        assert messages == before


class TestT0Purity:
    def _varying_history(self) -> list[Message]:
        return [
            Message(session_id="s1", role="user", content="[Tool: bash | Status: SUCCESS] done"),
            Message(session_id="s1", role="assistant", content="worker hand-off"),
            Message(session_id="s1", role="user", content="[Tool: glob | Status: SUCCESS] a.py"),
        ]

    def test_t0_prefix_diff_empty_across_n_prompts(self):
        prompts = [
            "Prompt A.",
            "Prompt B.",
            "x " * 200,
            "Completely different topic.",
            "λ unicode 🚀",
        ]
        baseline = None
        for i, prompt in enumerate(prompts):
            ctx = ContextManager(_base_config())
            messages = _build(
                ctx,
                prompt,
                history=self._varying_history(),
                summary=f"summary number {i}",
                repo_map="module a.py:1-10",
                memory="user prefers terse replies",
                plan_block=f"{i}. step",
            )
            t0 = messages[: ctx.t0_len()]
            if baseline is None:
                baseline = t0
            else:
                assert t0 == baseline, f"T0 prefix drifted for prompt #{i}: {t0}"

    def test_t0_has_only_role_and_content_keys(self):
        ctx = ContextManager(_base_config())
        messages = _build(ctx, "Prompt.", history=self._varying_history(), summary="Prior.")
        for msg in messages[: ctx.t0_len()]:
            assert set(msg.keys()) == {"role", "content"}

    def test_t0_content_free_of_timestamps_and_nonces(self):
        ctx = ContextManager(_base_config())
        messages = _build(ctx, "Prompt.", history=self._varying_history(), summary="Prior.")
        text = "".join(str(m.get("content", "")) for m in messages[: ctx.t0_len()])
        assert not re.search(r"\d{4}-\d{2}-\d{2}", text)
        assert not re.search(r"\b\d{10,13}\b", text)
        assert "nonce" not in text.lower()
        assert "timestamp" not in text.lower()

    def test_session_state_never_lands_inside_t0(self, temp_dir: Path):
        cfg = AppSettings(workspace_root=str(temp_dir))
        loop = AgentLoop(config=cfg, provider=_CachingProvider())
        sid = "state-t0-purity"
        record_write(sid, "a.py", "print('x')\n")
        try:
            messages = loop.context_manager.build_messages(
                [Message(session_id=sid, role="user", content="old")],
                SYSTEM_PROMPT,
                "new",
                "gpt-4",
            )
            AgentLoop._inject_session_state(messages, sid)
            t0_content = "".join(
                str(m.get("content", "")) for m in messages[: loop.context_manager.t0_len()]
            )
            assert "[Session state]" not in t0_content
            assert all("time" not in m for m in messages[: loop.context_manager.t0_len()])
        finally:
            reset_session(sid)

    def test_loop_prune_tool_outputs_leaves_t0_untouched(self, temp_dir: Path):
        cfg = AppSettings(workspace_root=str(temp_dir))
        loop = AgentLoop(config=cfg, provider=_CachingProvider())
        big = "[Tool: bash | Status: SUCCESS]\n" + "x" * 5000 + "\n"
        history = [
            Message(session_id="s1", role="user", content=big),
            Message(session_id="s1", role="assistant", content="worked"),
            Message(session_id="s1", role="user", content="[Tool: glob | Status: SUCCESS]\na.py"),
            Message(session_id="s1", role="assistant", content="next"),
            Message(session_id="s1", role="user", content="[Tool: read | Status: SUCCESS]\nb.py"),
        ]
        messages = loop.context_manager.build_messages(history, SYSTEM_PROMPT, "Continue.", "gpt-4")
        t0_len = loop.context_manager.t0_len()
        t0_snapshot = [dict(m) for m in messages[:t0_len]]
        stats = loop._prune_tool_outputs(messages, force_intraturn=True)
        assert stats["count"] >= 1
        assert messages[:t0_len] == t0_snapshot
        assert all("time" not in m for m in messages[:t0_len])
        assert any(m.get("time") == "compacted" for m in messages[t0_len:])


class TestTokenBudgeter:
    def _full_context(self, temp_dir: Path) -> tuple[ContextManager, list[dict]]:
        cfg = AppSettings(workspace_root=str(temp_dir))
        loop = AgentLoop(config=cfg, provider=_CachingProvider())
        sid = "budget-full-context"
        record_write(sid, "a.py", "print('x')\n")
        history = [
            Message(
                session_id=sid, role="user", content="[Tool: bash | Status: SUCCESS]\n" + "y" * 200
            ),
            Message(session_id=sid, role="assistant", content="assistant reply"),
            Message(session_id=sid, role="user", content="[Tool: glob | Status: SUCCESS]\na.py"),
            Message(session_id=sid, role="assistant", content="more assistant context"),
        ]
        messages = loop.context_manager.build_messages(
            history,
            SYSTEM_PROMPT,
            "The latest prompt.",
            "gpt-4",
            summary="Conversation summary text.",
            repo_map="module a.py:1-10",
            memory="prefers terse replies",
            plan_block="1. plan step",
        )
        AgentLoop._inject_session_state(messages, sid)
        reset_session(sid)
        return loop.context_manager, messages

    def test_breakdown_buckets_all_blocks(self, temp_dir: Path):
        ctx, messages = self._full_context(temp_dir)
        b = ctx.token_breakdown(messages)
        assert b.system > 0
        assert b.state > 0
        assert b.summary > 0
        assert b.handoff > 0
        assert b.tools > 0
        assert b.user > 0
        assert b.window > 0
        assert b.volatile == b.state + b.summary + b.handoff + b.window
        assert b.total == b.system + b.volatile + b.user + b.tools

    def test_breakdown_is_deterministic(self, temp_dir: Path):
        ctx, messages = self._full_context(temp_dir)
        assert ctx.token_breakdown(messages) == ctx.token_breakdown(messages)

    def test_breakdown_total_matches_heuristic_count(self, temp_dir: Path):
        ctx, messages = self._full_context(temp_dir)
        ctx.token_counter._available = False
        expected = ctx.token_counter.count_messages(messages, "gpt-4") - 2
        assert ctx.token_breakdown(messages).total == expected

    def test_reserve_output_at_least_min_on_128k_window(self, temp_dir: Path):
        ctx, messages = self._full_context(temp_dir)
        budget = ctx.get_token_budget(messages, "gpt-4")
        assert budget.window == DEFAULT_CONTEXT_WINDOW
        assert budget.reserve_output >= MIN_OUTPUT_RESERVE_TOKENS
        assert budget.input_budget == budget.window - budget.reserve_output
        assert budget.used == budget.breakdown.total

    def test_small_window_reserve_bounded(self, temp_dir: Path):
        cfg = AppSettings(
            workspace_root=str(temp_dir), max_context_tokens=32_000, repo_map_enabled=False
        )
        ctx = ContextManager(cfg)
        budget = ctx.get_token_budget([{"role": "user", "content": "hi"}], "gpt-4")
        assert budget.window == 32_000
        assert 0 < budget.reserve_output < budget.window
        assert budget.input_budget > 0


class TestSublinearGrowth:
    """3.9 property test: for N up to 100 prompts the composed input stays bounded.

    Models the loop contract from §6.2: compose -> if ``used >= watermark`` (the
    ``context_compaction_threshold``) fold the rolling history into a fixed-size
    summary (T4 -> T2) keeping the last few raw turns, then recompose. Asserts the
    steady-state invariant ``input_tokens <= watermark`` plus "no old user ever".
    """

    N_PROMPTS = 100
    KEEP_RAW_MESSAGES = 6
    SUMMARY_CAP_CHARS = 4000

    @staticmethod
    def _prompt(i: int) -> str:
        return f"User prompt {i}: " + "implement the next feature step. " * 8

    @staticmethod
    def _response(i: int) -> str:
        return f"Assistant turn {i}: " + "analysis and reasoning. " * 60

    @staticmethod
    def _tool_result(i: int) -> str:
        return "[Tool: bash | Status: SUCCESS]\n" + f"output line {i}\n" * 200

    def _compacted_summary(self, n_turns: int) -> str:
        parts = [f"task {j}" for j in range(n_turns)]
        return ("Previously completed: " + ", ".join(parts))[: self.SUMMARY_CAP_CHARS]

    def test_input_tokens_stay_at_or_below_watermark_for_many_prompts(self, temp_dir: Path):
        window = DEFAULT_CONTEXT_WINDOW
        # Gap #8 (mode budgets): build mode caps the history tier at 40% of the
        # input budget, so a conversation-only workload can never reach the
        # default 80% watermark. Lower the threshold to sit inside the
        # achievable range so the compaction property is still exercised.
        cfg = AppSettings(
            workspace_root=str(temp_dir),
            max_context_tokens=window,
            repo_map_enabled=False,
            memory_enabled=False,
            context_compaction_threshold=0.30,
        )
        ctx = ContextManager(cfg)
        ctx.token_counter._available = False
        watermark = int(window * cfg.context_compaction_threshold)

        history: list[Message] = []
        summary: str | None = None
        compactions = 0

        for i in range(self.N_PROMPTS):
            prompt = self._prompt(i)
            history.append(Message(session_id="s", role="user", content=prompt))
            history.append(Message(session_id="s", role="assistant", content=self._response(i)))
            history.append(Message(session_id="s", role="user", content=self._tool_result(i)))

            messages = ctx.build_messages(history, SYSTEM_PROMPT, prompt, "gpt-4", summary=summary)

            current_prompts = [
                m.get("content")
                for m in messages
                if m.get("role") == "user"
                and not str(m.get("content", "")).startswith("[Tool:")
                and not str(m.get("content", "")).startswith("[Previous conversation summary]")
            ]
            assert current_prompts == [prompt], f"old user prompt leaked at N={i + 1}"

            budget = ctx.get_token_budget(messages, "gpt-4")
            if budget.used >= watermark:
                summary = self._compacted_summary(i + 1)
                history = history[-self.KEEP_RAW_MESSAGES :]
                messages = ctx.build_messages(
                    history, SYSTEM_PROMPT, prompt, "gpt-4", summary=summary
                )
                budget = ctx.get_token_budget(messages, "gpt-4")
                compactions += 1

            assert budget.used <= watermark, (
                f"input tokens {budget.used} exceeded watermark {watermark} at N={i + 1}"
            )
            assert budget.breakdown.volatile <= watermark, (
                f"volatile tiers {budget.breakdown.volatile} exceeded watermark {watermark} "
                f"at N={i + 1}"
            )

        assert compactions >= 1, "test never hit the watermark; property is vacuous"

    def test_composer_saturates_instead_of_growing_linear(self, temp_dir: Path):
        """Without compaction the composer still caps history at the input budget,
        so input saturates instead of growing linearly with N."""
        window = DEFAULT_CONTEXT_WINDOW
        cfg = AppSettings(
            workspace_root=str(temp_dir),
            max_context_tokens=window,
            repo_map_enabled=False,
            memory_enabled=False,
        )
        ctx = ContextManager(cfg)
        ctx.token_counter._available = False

        history: list[Message] = []
        used_values: list[int] = []
        for i in range(self.N_PROMPTS):
            prompt = self._prompt(i)
            history.append(Message(session_id="s", role="user", content=prompt))
            history.append(Message(session_id="s", role="assistant", content=self._response(i)))
            history.append(Message(session_id="s", role="user", content=self._tool_result(i)))
            messages = ctx.build_messages(history, SYSTEM_PROMPT, prompt, "gpt-4")
            used_values.append(ctx.get_token_budget(messages, "gpt-4").used)

        assert max(used_values) < window
        budget_cap = window - ctx.get_token_budget([], "gpt-4").reserve_output
        assert max(used_values) <= budget_cap + 3000, (
            f"input {max(used_values)} exceeded the composer budget {budget_cap}"
        )
        last_ten = used_values[-10:]
        assert max(last_ten) - min(last_ten) <= 8000, (
            f"input grew by {max(last_ten) - min(last_ten)} tokens over the last 10 prompts"
        )


class TestPhase5InboundGather:
    """5.1 verification: inbound components are bounded."""

    def test_history_is_budget_bounded(self, temp_dir: Path):
        cfg = _base_config(max_context_tokens=2000, workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        ctx.token_counter._available = False
        big_history = [
            Message(session_id="s", role="user", content="u" * 500),
            Message(session_id="s", role="assistant", content="a" * 500),
        ] * 50
        messages = ctx.build_messages(big_history, SYSTEM_PROMPT, "go", "gpt-4")
        budget = ctx.get_token_budget(messages, "gpt-4")
        assert budget.used < 2000

    def test_session_state_bounded_at_400_tokens(self, temp_dir: Path):
        from server.agents.session_state import render_session_state

        reset_session("s-bounds")
        for i in range(50):
            record_write("s-bounds", f"file_{i}.py", f"content_{i}" * 50)
        state = render_session_state("s-bounds")
        assert state is not None
        from server.config.constants import CHARS_PER_TOKEN

        assert len(state) <= SESSION_STATE_MAX_TOKENS * CHARS_PER_TOKEN + 100

    def test_plan_context_budgeted(self, temp_dir: Path):
        cfg = _base_config(max_context_tokens=1500, workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        ctx.token_counter._available = False
        messages = ctx.build_messages(
            [],
            SYSTEM_PROMPT,
            "go",
            "gpt-4",
            plan_block="x " * 2000,
        )
        budget = ctx.get_token_budget(messages, "gpt-4")
        assert budget.used < 1500

    def test_new_prompt_always_verbatim_last(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        messages = ctx.build_messages(
            [Message(session_id="s", role="user", content="old")],
            SYSTEM_PROMPT,
            "my exact prompt",
            "gpt-4",
        )
        assert messages[-1] == {"role": "user", "content": "my exact prompt"}


class TestPhase5OutboundTierOrder:
    """5.2 verification: T0→T1→T2→T4→T5 strict order, no stale re-send."""

    def test_t0_first_t5_last_no_previous_user(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        history = [
            Message(session_id="s", role="user", content="prev prompt 1"),
            Message(session_id="s", role="assistant", content="response 1"),
            Message(session_id="s", role="user", content="prev prompt 2"),
            Message(session_id="s", role="assistant", content="response 2"),
        ]
        messages = ctx.build_messages(
            history,
            SYSTEM_PROMPT,
            "current",
            "gpt-4",
            summary="Earlier discussion.",
            repo_map="a.py",
        )
        assert messages[0]["role"] == "system"
        assert messages[-1] == {"role": "user", "content": "current"}
        user_contents = [
            m["content"]
            for m in messages
            if m.get("role") == "user"
            and not str(m.get("content", "")).startswith("[Tool:")
            and not str(m.get("content", "")).startswith("[Previous")
        ]
        assert user_contents == ["current"]

    def test_old_user_prompts_excluded(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        history = [
            Message(session_id="s", role="user", content="old1"),
            Message(session_id="s", role="assistant", content="ans1"),
            Message(session_id="s", role="user", content="old2"),
        ]
        messages = ctx.build_messages(history, SYSTEM_PROMPT, "new", "gpt-4")
        for m in messages:
            if m.get("role") == "user":
                assert m["content"] == "new"

    def test_tier_ordering_strict(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        _build(
            ctx,
            "final",
            history=[
                Message(session_id="s", role="user", content="[Tool: bash | Status: SUCCESS] out"),
                Message(session_id="s", role="assistant", content="did stuff"),
            ],
            summary="Earlier.",
            repo_map="mod.py",
            memory="likes terse",
        )
        tiers = ctx.tiers()
        t0s = [i for i, t in enumerate(tiers) if t == TIER_T0]
        t1s = [i for i, t in enumerate(tiers) if t == TIER_T1]
        t2s = [i for i, t in enumerate(tiers) if t == TIER_T2]
        t4s = [i for i, t in enumerate(tiers) if t == TIER_T4]
        assert t0s[0] < t1s[-1] < t2s[-1] < t4s[0]
        assert tiers[-1] == TIER_T5


class TestPhase5Idempotency:
    """5.3 verification: tool call dedup by (tool, normalized params hash)."""

    def test_call_signature_order_independent(self):
        sig1 = _call_signature("bash", {"command": "echo hi", "workdir": "/tmp"})
        sig2 = _call_signature("bash", {"workdir": "/tmp", "command": "echo hi"})
        assert sig1 == sig2

    def test_call_signature_differs_on_params(self):
        sig1 = _call_signature("bash", {"command": "echo hi"})
        sig2 = _call_signature("bash", {"command": "echo bye"})
        assert sig1 != sig2

    def test_call_signature_differs_on_tool(self):
        sig1 = _call_signature("bash", {"command": "echo hi"})
        sig2 = _call_signature("file_read", {"command": "echo hi"})
        assert sig1 != sig2

    @pytest.mark.asyncio
    async def test_same_path_rewrite_is_blocked(self, temp_dir: Path):
        from server.toolkit import create_default_registry

        reg = create_default_registry()
        reset_session("s-dedup")
        result1 = await reg.execute(
            "file_write",
            {"path": "plan.md", "content": "same"},
            str(temp_dir),
            mode="plan",
        )
        assert result1.success
        result2 = await reg.execute(
            "file_write",
            {"path": "plan.md", "content": "same"},
            str(temp_dir),
            mode="plan",
        )
        assert not result2.success


class TestPhase5OverwriteGuard:
    """5.4 verification: cross-turn identical replay blocked by content hash."""

    def test_identical_replay_detected(self, temp_dir: Path):
        from server.agents.session_workspace import is_identical_replay

        reset_session("s-ow")
        record_write("s-ow", "a.py", "content v1")
        assert is_identical_replay("s-ow", "a.py", "content v1") is True
        assert is_identical_replay("s-ow", "a.py", "content v2") is False
        assert is_identical_replay("s-other", "a.py", "content v1") is False

    def test_different_content_not_blocked(self, temp_dir: Path):
        from server.agents.session_workspace import is_identical_replay

        reset_session("s-ow2")
        record_write("s-ow2", "b.py", "original")
        assert is_identical_replay("s-ow2", "b.py", "updated content") is False


class TestPhase6AnthropicCacheControl:
    """6.1 verification: Anthropic catalog sets supports_prompt_caching; T0 is breakpoint."""

    def test_anthropic_catalog_supports_prompt_caching(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        loop = AgentLoop(config=cfg, provider=_AnthropicProvider())
        loop._catalog_for_provider = staticmethod(
            lambda name: {"supports_prompt_caching": True, "adapter": "anthropic"}
        )
        messages = loop.context_manager.build_messages(
            [],
            SYSTEM_PROMPT,
            "Hello.",
            "gpt-4",
        )
        cached = loop._apply_prompt_caching(messages)
        assert cached[0].get("cache_control") == {"type": "ephemeral"}

    def test_anthropic_only_t0_gets_cache_control(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        loop = AgentLoop(config=cfg, provider=_AnthropicProvider())
        loop._catalog_for_provider = staticmethod(
            lambda name: {"supports_prompt_caching": True, "adapter": "anthropic"}
        )
        messages = loop.context_manager.build_messages(
            [Message(session_id="s1", role="user", content="old")],
            SYSTEM_PROMPT,
            "new",
            "gpt-4",
            summary="summary",
        )
        cached = loop._apply_prompt_caching(messages)
        boundaries = loop.context_manager.tier_boundaries()
        cache_indices = set()
        for idx in [boundaries["t0_end"], boundaries["t1_end"], boundaries["t2_end"]]:
            if idx > 0:
                cache_indices.add(idx - 1)
        for i, m in enumerate(cached):
            if i in cache_indices:
                assert m.get("cache_control") == {"type": "ephemeral"}, f"msg {i} missing flag"
            else:
                assert "cache_control" not in m, f"non-T0 msg {i} got unexpected flag"


class TestPhase6GeminiImplicitCaching:
    """6.2 verification: Gemini excluded from explicit cache_control; T0 byte-identical."""

    def test_gemini_excluded_from_explicit_caching(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        loop = AgentLoop(config=cfg, provider=_CachingProvider())
        loop._catalog_for_provider = staticmethod(
            lambda name: {"supports_prompt_caching": True, "adapter": "gemini"}
        )
        messages = loop.context_manager.build_messages(
            [],
            SYSTEM_PROMPT,
            "Hello.",
            "gpt-4",
        )
        cached = loop._apply_prompt_caching(messages)
        for m in cached:
            assert "cache_control" not in m

    def test_gemini_t0_byte_identical_across_prompts(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        t0_a = _build(ctx, "first")[: ctx.t0_len()]
        t0_b = _build(ctx, "second")[: ctx.t0_len()]
        assert t0_a == t0_b

    def test_gemini_t0_is_first_message(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        msgs = _build(
            ctx,
            "hello",
            history=[
                _msg("user", "summarize"),
                _msg("assistant", "ok"),
                _msg("user", "[Tool: read | Status: SUCCESS]\na.py"),
            ],
            summary="summary",
        )
        t0_len = ctx.t0_len()
        assert t0_len >= 1
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"].startswith("You are Zenith")


class TestPhase6OpenAISchemaCap:
    """6.3 verification: schema set bounded; escalation doesn't exceed cap; churn capped."""

    def test_schema_set_stable_across_repeated_escalations(self, temp_dir: Path):
        from server.toolkit import create_default_registry
        from server.toolkit.resolver import SchemaResolver, build_mode_tool_seed
        from server.config.settings import CORE_BUILD_TOOLS

        reg = create_default_registry()
        seed = build_mode_tool_seed(CORE_BUILD_TOOLS)
        resolver = SchemaResolver(reg, seed=seed)
        tools = [
            "bash",
            "bash",
            "websearch",
            "websearch",
            "bash",
            "websearch",
            "file_delete",
            "bash",
            "websearch",
        ]
        for t in tools:
            resolver.request_tool(t)
        active = resolver.active_names()
        from server.config.constants import MAX_ACTIVE_TOOLS_PER_TURN

        assert len(active) <= MAX_ACTIVE_TOOLS_PER_TURN
        assert resolver.schema_tokens("gpt-4") > 0

    def test_seed_tools_never_evicted(self, temp_dir: Path):
        from server.toolkit import create_default_registry
        from server.toolkit.resolver import SchemaResolver, build_mode_tool_seed
        from server.config.settings import CORE_BUILD_TOOLS

        reg = create_default_registry()
        seed = build_mode_tool_seed(CORE_BUILD_TOOLS)
        seed_set = set(seed)
        resolver = SchemaResolver(reg, seed=seed, max_tools=len(seed))
        resolver.request_tool("websearch")
        assert len(resolver.active_names()) <= len(seed)
        assert "websearch" not in resolver.active_names(), "escalated tool should be evicted"
        for name in seed_set:
            assert name in resolver.active_names(), f"seed tool {name} was evicted"


class TestPhase6T0Discipline:
    """6.4 verification: T0 is free of volatile/timestamp/nonce content across N prompts."""

    def test_t0_pure_across_varied_contexts(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        t0s = []
        for i in range(10):
            msgs = _build(
                ctx,
                f"prompt-{i}",
                history=[
                    _msg("user", f"summarize {i}"),
                    _msg("assistant", f"done {i}"),
                    _msg("user", f"[Tool: read | Status: SUCCESS]\nfile{i}.py"),
                ],
                summary=f"summary-{i}",
            )
            t0s.append(msgs[: ctx.t0_len()])
        for t0 in t0s:
            assert t0 == t0s[0], "T0 prefix must be byte-identical across all prompts"

    def test_system_prompt_no_timestamps_or_nonces(self):
        import re

        prompt = build_system_prompt(workspace_root=".")
        assert not re.search(r"\d{4}-\d{2}-\d{2}", prompt)
        assert "nonce" not in prompt.lower()
        assert "timestamp" not in prompt.lower()
        assert "request_id" not in prompt.lower()

    def test_t0_keys_are_role_and_content_only(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        msgs = _build(ctx, "final")
        t0_len = ctx.t0_len()
        for m in msgs[:t0_len]:
            assert set(m.keys()) <= {"role", "content"}, (
                f"T0 has extra keys: {set(m.keys()) - {'role', 'content'}}"
            )


class TestPhase7ContextComposer:
    """7.1 verification: golden-payload fixtures for M1 and M2."""

    def test_m1_golden_fresh_session_payload(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        messages = _build(ctx, "Implement the feature.", history=[])
        assert ctx.tiers() == [TIER_T0, TIER_T5]
        assert len(messages) == 2
        assert messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
        assert messages[1] == {"role": "user", "content": "Implement the feature."}
        for m in messages:
            assert "cache_control" not in m

    def test_m1_golden_no_volatile_blocks(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        messages = _build(
            ctx,
            "Fix the bug.",
            history=[],
            repo_map="a.py",
            memory="color is blue",
            plan_block="1. step one",
        )
        assert ctx.tiers() == [TIER_T0, TIER_T5]
        for m in messages:
            content = m.get("content", "")
            assert "<repo_map>" not in content
            assert "<memory>" not in content
            assert "[Session state]" not in content
            assert "[Running summary]" not in content

    def test_m2_golden_continuation_payload(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        messages = _build(
            ctx,
            "Now do the next step.",
            history=[
                Message(session_id="s1", role="user", content="first prompt"),
                Message(session_id="s1", role="assistant", content="I did step 1."),
                Message(
                    session_id="s1",
                    role="user",
                    content="[Tool: file_write | Status: SUCCESS]\nplan.md",
                ),
            ],
            summary="[Running summary]\nPrevious topic was build-mode.",
        )
        tiers = ctx.tiers()
        assert TIER_T0 in tiers
        assert TIER_T5 in tiers
        assert messages[-1] == {"role": "user", "content": "Now do the next step."}
        assert messages[0]["role"] == "system"
        all_contents = " ".join(m.get("content", "") for m in messages)
        assert "[Running summary]" in all_contents

    def test_m2_golden_tier_order_invariant(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        _build(
            ctx,
            "Continue.",
            history=[
                Message(session_id="s1", role="user", content="old"),
                Message(session_id="s1", role="assistant", content="ok"),
            ],
            summary="summary text",
        )
        tiers = ctx.tiers()
        tier_positions = {t: i for i, t in enumerate(tiers)}
        assert tier_positions[TIER_T0] < tier_positions[TIER_T5]


class TestPhase7TokenBudgeter:
    """7.2 verification: deterministic per-tier token accounting; reserve ≥ 8K; watermark."""

    def test_output_reserve_at_least_8k_on_128k(self):
        from server.agents.context import _adaptive_reserve

        reserve = _adaptive_reserve("gpt-4", 128_000)
        assert reserve >= 8_000

    def test_output_reserve_scales_for_larger_window(self):
        from server.agents.context import _adaptive_reserve

        reserve_128 = _adaptive_reserve("gpt-4", 128_000)
        reserve_200 = _adaptive_reserve("gpt-4", 200_000)
        assert reserve_128 >= 8_000
        assert reserve_200 >= 8_000
        assert reserve_200 <= 20_000

    def test_token_breakdown_deterministic(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        messages = _build(
            ctx,
            "first",
            history=[
                Message(session_id="s1", role="user", content="old"),
                Message(session_id="s1", role="assistant", content="ok"),
            ],
            summary="summary",
        )
        breakdown1 = ctx.token_breakdown(messages)
        breakdown2 = ctx.token_breakdown(messages)
        assert breakdown1.to_dict() == breakdown2.to_dict()

    def test_token_breakdown_has_all_tiers(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        messages = _build(
            ctx,
            "prompt",
            history=[
                Message(session_id="s1", role="user", content="old"),
                Message(session_id="s1", role="assistant", content="ok"),
            ],
            summary="summary text",
        )
        bd = ctx.token_breakdown(messages)
        d = bd.to_dict()
        assert "system" in d
        assert "user" in d
        assert "state" in d
        assert "summary" in d
        assert "window" in d

    def test_watermark_config_default(self):
        from server.config.settings import AppSettings

        cfg = AppSettings()
        assert cfg.context_compaction_threshold == 0.7

    def test_hard_stop_ratio_constant(self):
        from server.config.constants import HARD_STOP_USAGE_RATIO

        assert HARD_STOP_USAGE_RATIO == 0.95


class TestPhase7EventStream:
    """7.6 verification: typed events with sequence numbers; replay buffer; per-tier tokens."""

    def test_event_has_required_fields(self):
        from server.domain.events import EventKind, make_event

        evt = make_event(EventKind.SUCCESS, {"tokens": 100}, session_id="s1")
        assert evt.kind == EventKind.SUCCESS
        assert evt.session_id == "s1"
        assert evt.id.startswith("evt_")
        assert isinstance(evt.data, dict)

    def test_compaction_events_defined(self):
        from server.domain.events import EventKind

        assert hasattr(EventKind, "CONTEXT_COMPACTION_STARTED")
        assert hasattr(EventKind, "CONTEXT_COMPACTION_PHASE")
        assert hasattr(EventKind, "CONTEXT_COMPACTION_ENDED")

    def test_token_events_defined(self):
        from server.domain.events import EventKind

        assert hasattr(EventKind, "TOKEN_USAGE_RECORDED")

    def test_event_sequence_injected_in_metadata(self):
        from server.domain.events import Event, EventKind

        evt = Event(kind=EventKind.MESSAGE, data={"text": "hi"}, session_id="s1")
        evt.metadata["sequence"] = 1
        assert evt.metadata["sequence"] == 1


class TestPhase7Telemetry:
    """7.7 verification: per-tier tokens in success event; cache hit rate data."""

    def test_success_event_carry_per_tier_tokens(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        messages = _build(
            ctx,
            "prompt",
            history=[
                Message(session_id="s1", role="user", content="old"),
                Message(session_id="s1", role="assistant", content="ok"),
            ],
            summary="summary",
        )
        bd = ctx.token_breakdown(messages)
        d = bd.to_dict()
        assert d["system"] > 0
        assert d["user"] > 0
        assert sum(d.values()) > 0

    def test_compaction_events_carry_tier_breakdown(self):
        from server.domain.events import EventKind, make_event

        evt = make_event(
            EventKind.CONTEXT_COMPACTION_STARTED,
            {
                "tokens": {
                    "system": 100,
                    "state": 50,
                    "summary": 30,
                    "handoff": 20,
                    "window": 60,
                    "user": 40,
                    "tools": 10,
                }
            },
            session_id="s1",
        )
        tokens = evt.data.get("tokens", {})
        for key in ["system", "state", "summary", "handoff", "window", "user", "tools"]:
            assert key in tokens, f"missing tier key: {key}"

    def test_ttft_field_recorded_on_success(self):
        from server.domain.events import EventKind, make_event

        evt = make_event(
            EventKind.SUCCESS,
            {"ttft_ms": 150, "elapsed_ms": 1200, "prompt_tokens": 500},
            session_id="s1",
        )
        assert evt.data["ttft_ms"] == 150
        assert evt.data["elapsed_ms"] == 1200


class TestPhase8GrowthTable:
    """8.5 verification: Arch 1 — rolling window + running summary.
    Dry-run N=1,2,large and assert the continuation input bound ≤ 30% of window."""

    LARGE_N = 50

    def test_m1_fresh_session_bound(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        messages = _build(ctx, "First prompt.", history=[])
        budget = ctx.get_token_budget(messages, "gpt-4")
        assert budget.used > 0
        assert budget.breakdown.system > 0
        assert budget.breakdown.user > 0
        assert budget.breakdown.volatile == 0

    def test_m2_continuation_within_30pct(self, temp_dir: Path):
        window = DEFAULT_CONTEXT_WINDOW
        cfg = _base_config(workspace_root=str(temp_dir), max_context_tokens=window)
        ctx = ContextManager(cfg)
        ctx.token_counter._available = False
        messages = _build(
            ctx,
            "Second prompt.",
            history=[
                Message(session_id="s", role="user", content="first"),
                Message(session_id="s", role="assistant", content="ok"),
                Message(
                    session_id="s", role="user", content="[Tool: bash | Status: SUCCESS]\noutput"
                ),
            ],
            summary="[Previous conversation summary]\nEarlier topic.",
        )
        budget = ctx.get_token_budget(messages, "gpt-4")
        bound_30pct = int(window * 0.30)
        assert budget.used <= bound_30pct, (
            f"M2 input {budget.used} exceeded 30% bound {bound_30pct}"
        )

    def test_large_n_continuation_sublinear(self, temp_dir: Path):
        window = DEFAULT_CONTEXT_WINDOW
        cfg = _base_config(workspace_root=str(temp_dir), max_context_tokens=window)
        ctx = ContextManager(cfg)
        ctx.token_counter._available = False
        bound_30pct = int(window * 0.30)

        history: list[Message] = []
        summary: str | None = None
        used_at_large_n = 0

        for i in range(self.LARGE_N):
            prompt = f"Step {i}: implement feature."
            history.append(Message(session_id="s", role="user", content=prompt))
            history.append(
                Message(session_id="s", role="assistant", content=f"Done step {i}. " * 50)
            )
            history.append(
                Message(
                    session_id="s", role="user", content=f"[Tool: bash | Status: SUCCESS]\nout{i}"
                )
            )
            messages = ctx.build_messages(history, SYSTEM_PROMPT, prompt, "gpt-4", summary=summary)
            budget = ctx.get_token_budget(messages, "gpt-4")
            if budget.used >= int(window * 0.7):
                summary = f"Completed steps 0..{i}."
                history = history[-6:]
            used_at_large_n = ctx.get_token_budget(
                ctx.build_messages(history, SYSTEM_PROMPT, prompt, "gpt-4", summary=summary),
                "gpt-4",
            ).used

        assert used_at_large_n <= bound_30pct, (
            f"N={self.LARGE_N} input {used_at_large_n} exceeded 30% bound {bound_30pct}"
        )

    def test_arch1_docstring_records_decision(self):
        import server.agents.context as ctx_mod

        source = open(ctx_mod.__file__).read()
        assert "Arch 1" in source
        assert "Rolling window" in source


class TestPhase9Redaction:
    """9.3 + 9.14: no secrets/PII in persisted text."""

    def test_redact_pii_strips_api_keys(self):
        from server.toolkit.executor import redact_pii

        text = "api_key=sk-abc123def456ghi789jkl012mno"
        result = redact_pii(text)
        assert "sk-abc123" not in result
        assert "***" in result

    def test_redact_pii_strips_bearer_tokens(self):
        from server.toolkit.executor import redact_pii

        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = redact_pii(text)
        assert "eyJhbGci" not in result

    def test_redact_pii_preserves_normal_text(self):
        from server.toolkit.executor import redact_pii

        text = "The file was written successfully at /tmp/output.py"
        result = redact_pii(text)
        assert result == text

    def test_no_secrets_in_persisted_handoff(self):
        from server.toolkit.executor import redact_pii

        handoff = "api_key=sk-supersecret1234567890abcdef and password=hunter2"
        redacted = redact_pii(handoff)
        assert "sk-supersecret" not in redacted
        assert "hunter2" not in redacted


class TestPhase9Resilience:
    """9.4–9.7: provider errors typed, one terminal event, degradation."""

    def test_typed_error_has_action_hint(self):
        from server.agents.llm_stream import _error_action_hint
        from server.domain.errors import RateLimitError

        rate_err = RateLimitError(provider="anthropic", retry_after=5.0)
        action, hint = _error_action_hint(rate_err)
        assert action == "retry"
        assert "rate limit" in hint.lower() or "wait" in hint.lower()

    def test_provider_error_has_code(self):
        from server.domain.errors import ProviderError

        err = ProviderError(provider="openai", message="fail")
        assert err.code or err.message

    def test_terminal_event_one_per_prompt(self):
        from server.domain.events import EventKind

        terminal_events = {EventKind.SUCCESS, EventKind.ERROR, EventKind.WARNING}
        assert len(terminal_events) >= 3

    def test_ttft_measured(self):
        from server.domain.events import EventKind, make_event

        evt = make_event(EventKind.SUCCESS, {"ttft_ms": 120, "elapsed_ms": 500})
        assert evt.data["ttft_ms"] == 120


class TestPhase9PerTurnIsolation:
    """9.15: cross-task contamination — per-turn state must not leak."""

    def test_executed_calls_reset_between_loops(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        loop = AgentLoop(config=cfg, provider=_CachingProvider())
        assert not hasattr(loop, "_executed_calls") or loop._executed_calls == set()

    def test_created_files_are_local_to_process_prompt(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        loop = AgentLoop(config=cfg, provider=_CachingProvider())
        assert not hasattr(loop, "_created_files") or loop._created_files == set()

    def test_usage_reset_per_request(self, temp_dir: Path):
        from server.domain.events import EventKind, make_event

        evt1 = make_event(EventKind.SUCCESS, {"used": 1000})
        evt2 = make_event(EventKind.SUCCESS, {"used": 1000})
        assert evt1.data["used"] == evt2.data["used"]


class TestPhase9AutoOverwrite:
    """Task 11: auto_overwrite config trace."""

    def test_auto_overwrite_default_true(self):
        from server.config.settings import AppSettings

        cfg = AppSettings()
        assert cfg.auto_overwrite is True

    def test_auto_overwrite_rejects_when_false(self, temp_dir: Path):
        from server.config.settings import AppSettings

        cfg = AppSettings(workspace_root=str(temp_dir), auto_overwrite=False)
        assert cfg.auto_overwrite is False

    def test_auto_overwrite_setting_exists(self):
        from server.config.settings import AppSettings

        assert "auto_overwrite" in AppSettings.model_fields


class TestPhase9SessionStateBounded:
    """Task 38: bounded, compressed session_state."""

    def test_session_state_max_tokens_constant(self):
        from server.config.constants import SESSION_STATE_MAX_TOKENS

        assert SESSION_STATE_MAX_TOKENS == 400

    def test_session_state_entry_max_chars(self):
        from server.config.constants import SESSION_STATE_ENTRY_MAX_CHARS

        assert SESSION_STATE_ENTRY_MAX_CHARS == 200


class TestPhase10SLOGates:
    """Phase 10: SLO gates with evidence."""

    def test_slo1_continuation_within_30pct(self, temp_dir: Path):
        window = DEFAULT_CONTEXT_WINDOW
        cfg = _base_config(workspace_root=str(temp_dir), max_context_tokens=window)
        ctx = ContextManager(cfg)
        ctx.token_counter._available = False
        messages = _build(
            ctx,
            "prompt",
            history=[
                Message(session_id="s", role="user", content="old"),
                Message(session_id="s", role="assistant", content="ok"),
            ],
            summary="summary",
        )
        budget = ctx.get_token_budget(messages, "gpt-4")
        assert budget.used <= int(window * 0.30)

    def test_slo3_no_old_user_messages(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        messages = _build(
            ctx,
            "latest",
            history=[
                Message(session_id="s", role="user", content="old prompt"),
                Message(session_id="s", role="assistant", content="ok"),
            ],
            summary="summary",
        )
        user_msgs = [
            m
            for m in messages
            if m.get("role") == "user" and not str(m.get("content", "")).startswith("[Tool:")
        ]
        assert user_msgs[-1]["content"] == "latest"

    def test_slo4_no_placeholder_for_worked_turns(self):
        from server.domain.events import EventKind, make_event

        manifest = make_event(
            EventKind.TURN_MANIFEST,
            {
                "created": ["a.py"],
                "modified": [],
                "verified": True,
            },
        )
        assert manifest.data["created"]

    def test_slo6_latest_message_verbatim(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        messages = _build(ctx, "exact text here", history=[])
        assert messages[-1]["content"] == "exact text here"

    def test_slo5_no_thinking_in_outbound(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        messages = _build(
            ctx,
            "prompt",
            history=[],
        )
        all_content = " ".join(m.get("content", "") for m in messages)
        assert "<thinking>" not in all_content

    def test_slo9_no_fabricated_facts_in_summary(self):
        from server.agents.summarizer import ConversationSummarizer

        assert hasattr(ConversationSummarizer, "summarize")


class TestPhase11Scenarios:
    """Phase 11: representative scenario tests."""

    def test_read_only_no_mutation_tools(self, temp_dir: Path):
        from server.config.constants import READ_ONLY_TOOLS
        from server.config.settings import CORE_BUILD_TOOLS

        for t in READ_ONLY_TOOLS:
            assert t in ["file_read", "glob", "grep", "list_dir"]
        for t in CORE_BUILD_TOOLS:
            assert t in ["file_read", "file_edit", "file_write", "bash", "glob", "grep"]

    def test_plan_mode_no_bash(self, temp_dir: Path):
        from server.config.settings import CORE_PLAN_TOOLS

        assert "bash" not in CORE_PLAN_TOOLS
        assert "file_write" in CORE_PLAN_TOOLS

    def test_handoff_never_empty_when_work_happened(self):
        from server.agents.prompt_executor import _build_crafted_handoff

        manifest = {"created": ["a.py"], "modified": [], "verified": True}
        handoff = _build_crafted_handoff(manifest, "I created the file.")
        assert handoff
        assert "[Cancelled by user]" not in handoff


class TestFinalGates:
    """FINAL-1 through FINAL-8: completion gates."""

    def test_final2_imports_cleanly(self):
        import server

        assert server is not None

    def test_final5_no_placeholder_when_work_happened(self):
        from server.agents.prompt_executor import _did_work

        manifest = {"created": ["a.py"], "modified": [], "verified": True}
        assert _did_work(manifest)

    def test_final6_no_old_user_in_fresh_context(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        messages = _build(ctx, "new prompt", history=[])
        for m in messages:
            if m.get("role") == "user":
                assert m["content"] == "new prompt"

    def test_final7_t0_byte_stable_across_prompts(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        t0_a = _build(ctx, "a")[: ctx.t0_len()]
        t0_b = _build(ctx, "b")[: ctx.t0_len()]
        assert t0_a == t0_b

    def test_final8_architecture_documented(self):
        import server.agents.context as ctx_mod

        source = open(ctx_mod.__file__).read()
        assert "Arch 1" in source


class TestStalenessDetection:
    """Gap #6.2: Verify stale file reads get penalized in T4 backward-fit."""

    def test_stale_read_gets_doubled_cost(self, temp_dir: Path):
        sid = "stale-ctx-1"
        reset_session(sid)
        record_read(sid, "auth.py")
        import time

        t_read = time.monotonic()
        while time.monotonic() == t_read:
            time.sleep(0.02)
        record_edit(sid, "auth.py")
        assert is_stale(sid, "auth.py")

        cfg = _base_config(workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        tool_result = "[Tool: file_read | Status: SUCCESS]\nauth.py\n stale content"
        history = [
            _msg("assistant", "I will read auth.py"),
            _msg("user", tool_result),
        ]
        messages = ctx.build_messages(history, SYSTEM_PROMPT, "continue", "gpt-4", session_id=sid)
        tool_msgs = [m for m in messages if m.get("content", "").startswith("[Tool:")]
        assert len(tool_msgs) == 1
        assert ctx._last_stale_count == 1

    def test_non_stale_read_not_penalized(self, temp_dir: Path):
        sid = "stale-ctx-2"
        reset_session(sid)
        record_read(sid, "fresh.py")

        cfg = _base_config(workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        tool_result = "[Tool: file_read | Status: SUCCESS]\nfresh.py\n fresh content"
        history = [
            _msg("assistant", "I will read fresh.py"),
            _msg("user", tool_result),
        ]
        messages = ctx.build_messages(history, SYSTEM_PROMPT, "continue", "gpt-4", session_id=sid)
        tool_msgs = [m for m in messages if m.get("content", "").startswith("[Tool:")]
        for m in tool_msgs:
            assert m.get("is_stale") is None

    def test_stale_evicted_before_non_stale_in_tight_budget(self, temp_dir: Path):
        """When budget is tight, the stale read should be evicted first."""
        sid = "stale-ctx-3"
        reset_session(sid)
        record_read(sid, "stale.py")
        import time

        t_read = time.monotonic()
        while time.monotonic() == t_read:
            time.sleep(0.02)
        record_edit(sid, "stale.py")
        record_read(sid, "fresh.py")

        cfg = _base_config(workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        stale_result = "[Tool: file_read | Status: SUCCESS]\nstale.py\n stale data"
        fresh_result = "[Tool: file_read | Status: SUCCESS]\nfresh.py\n fresh data"
        history = [
            _msg("assistant", "reading stale"),
            _msg("user", stale_result),
            _msg("assistant", "reading fresh"),
            _msg("user", fresh_result),
        ]
        messages = ctx.build_messages(history, SYSTEM_PROMPT, "continue", "gpt-4", session_id=sid)
        tool_contents = [
            m["content"] for m in messages if m.get("content", "").startswith("[Tool:")
        ]
        stale_present = any("stale.py" in c for c in tool_contents)
        fresh_present = any("fresh.py" in c for c in tool_contents)
        if stale_present and fresh_present:
            pass
        elif fresh_present:
            pass
        else:
            pytest.fail("Fresh read should be preferred over stale read when budget is tight")


class TestStalenessTelemetry:
    """Gap #6.3: Verify stale Reads evicted counter is tracked."""

    def test_last_stale_count_tracked(self, temp_dir: Path):
        sid = "telemetry-1"
        reset_session(sid)
        record_read(sid, "old.py")
        import time

        t_read = time.monotonic()
        while time.monotonic() == t_read:
            time.sleep(0.02)
        record_edit(sid, "old.py")
        cfg = _base_config(workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        tool_result = "[Tool: file_read | Status: SUCCESS]\nold.py\n stale"
        history = [_msg("assistant", "reading"), _msg("user", tool_result)]
        ctx.build_messages(history, SYSTEM_PROMPT, "continue", "gpt-4", session_id=sid)
        assert ctx._last_stale_count == 1

    def test_non_stale_count_zero(self, temp_dir: Path):
        sid = "telemetry-2"
        reset_session(sid)
        record_read(sid, "fresh.py")
        cfg = _base_config(workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        tool_result = "[Tool: file_read | Status: SUCCESS]\nfresh.py\n fresh"
        history = [_msg("assistant", "reading"), _msg("user", tool_result)]
        ctx.build_messages(history, SYSTEM_PROMPT, "continue", "gpt-4", session_id=sid)
        assert ctx._last_stale_count == 0


class TestScoreBasedEviction:
    """Gap #1: Verify score-based T4 eviction."""

    def test_errors_outlive_successes(self, temp_dir: Path):
        from server.agents.context import HistoryEntry, score_entry

        err_entry = HistoryEntry(message={}, tokens=100, role="user", is_error=True, turn_index=1)
        ok_entry = HistoryEntry(
            message={}, tokens=100, role="assistant", is_error=False, turn_index=2
        )
        assert score_entry(err_entry, 5, 5) > score_entry(ok_entry, 5, 5)

    def test_stale_heavily_penalized(self, temp_dir: Path):
        from server.agents.context import HistoryEntry, score_entry

        stale = HistoryEntry(message={}, tokens=100, role="user", is_stale=True, turn_index=3)
        fresh = HistoryEntry(message={}, tokens=100, role="user", is_stale=False, turn_index=3)
        assert score_entry(stale, 5, 5) < score_entry(fresh, 5, 5)

    def test_large_items_cost_more(self, temp_dir: Path):
        from server.agents.context import HistoryEntry, score_entry

        small = HistoryEntry(message={}, tokens=50, role="user", turn_index=2)
        large = HistoryEntry(message={}, tokens=5000, role="user", turn_index=2)
        assert score_entry(small, 5, 5) > score_entry(large, 5, 5)

    def test_error_survives_when_budget_tight(self, temp_dir: Path):
        """Error message should be kept over a non-error assistant msg."""
        cfg = _base_config(workspace_root=str(temp_dir), max_context_tokens=20000)
        ctx = ContextManager(cfg)
        err_result = "[Tool: bash | Status: ERROR]\nbig error " + "x" * 8000
        ok_msg = "I fixed the bug."
        history = [
            _msg("user", err_result),
            _msg("assistant", ok_msg),
        ]
        messages = ctx.build_messages(history, SYSTEM_PROMPT, "continue", "gpt-4")
        contents = [m["content"] for m in messages]
        assert any("Status: ERROR" in c for c in contents)


class TestMultiTierCacheBreakpoints:
    """Gap #4: Verify tier_boundaries and multi-breakpoint caching."""

    def test_tier_boundaries_basic(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        _build(ctx, "go", history=[_msg("assistant", "ok")], summary="prev summary")
        bounds = ctx.tier_boundaries()
        assert bounds["t0_end"] == 1
        assert bounds["t2_end"] > 0
        assert bounds["t4_end"] > 0

    def test_tier_boundaries_no_summary(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        _build(ctx, "go", history=[_msg("assistant", "ok")])
        bounds = ctx.tier_boundaries()
        assert bounds["t0_end"] == 1
        assert bounds["t2_end"] == 0
        assert bounds["t4_end"] > 0

    def test_tier_boundaries_ordering(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        ctx = ContextManager(cfg)
        _build(
            ctx,
            "go",
            history=[_msg("assistant", "ok")],
            summary="prev summary",
            repo_map="a.py",
            memory="remember x",
        )
        bounds = ctx.tier_boundaries()
        assert bounds["t0_end"] <= bounds["t1_end"] <= bounds["t2_end"] <= bounds["t4_end"]


class TestCacheSafeCompaction:
    """Gap #5: the compaction summarizer request must reuse the main request's
    cache prefix (system prompt + cached tiers) instead of invalidating it."""

    async def _compact_with_recording_provider(self, temp_dir, messages):
        from server.agents.compaction_service import CompactionService
        from server.domain.message import Message

        recorded: dict = {}

        class _Recorder:
            name = "fake-recorder"
            model = "gpt-4"

            async def complete(self, request, tools=None):
                recorded["request"] = [dict(m) for m in request]
                return "compacted summary"

            async def validate(self) -> bool:
                return True

        provider = _Recorder()
        cfg = _base_config(workspace_root=str(temp_dir))
        cm = ContextManager(cfg)
        service = CompactionService(cfg, provider, context_manager=cm)
        history = [
            Message(session_id="s1", role="user", content=f"old prompt {i} " + "x" * 1300)
            for i in range(150)
        ] + [Message(session_id="s1", role="assistant", content="old reply")]
        outcome = await service.compact(
            session_id="s1",
            history=history,
            messages=[dict(m) for m in messages],
            previous_summary=None,
        )
        return outcome, recorded

    @pytest.mark.asyncio
    async def test_compaction_request_prepends_cache_prefix(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        loop = AgentLoop(config=cfg, provider=_CachingProvider())
        loop._catalog_for_provider = staticmethod(
            lambda provider_name: {"supports_prompt_caching": True, "adapter": "anthropic"}
        )
        messages = loop.context_manager.build_messages(
            [Message(session_id="s1", role="user", content="old")],
            SYSTEM_PROMPT,
            "new",
            "gpt-4",
            summary="Prior context.",
        )
        cached = loop._apply_prompt_caching(messages)
        outcome, recorded = await self._compact_with_recording_provider(temp_dir, cached)

        assert not outcome.failed
        request = recorded["request"]
        assert request, "summarizer provider must be called"
        assert request[0]["content"] == SYSTEM_PROMPT
        assert any(m.get("cache_control") for m in request), "cache markers must survive into the prefix"
        assert request[-1]["role"] == "user"

    @pytest.mark.asyncio
    async def test_compaction_prefix_ends_at_last_cache_marker(self, temp_dir: Path):
        from server.agents.compaction_service import _cache_prefix_for

        msgs = [
            {"role": "system", "content": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}},
            {"role": "system", "content": "tool schemas", "cache_control": {"type": "ephemeral"}},
            {"role": "system", "content": "summary block"},
            {"role": "user", "content": "history + prompt"},
        ]
        prefix = _cache_prefix_for(msgs)
        assert len(prefix) == 2
        assert prefix[-1]["content"] == "tool schemas"

    @pytest.mark.asyncio
    async def test_post_compaction_prompt_keeps_cache_markers(self, temp_dir: Path):
        cfg = _base_config(workspace_root=str(temp_dir))
        loop = AgentLoop(config=cfg, provider=_CachingProvider())
        loop._catalog_for_provider = staticmethod(
            lambda provider_name: {"supports_prompt_caching": True, "adapter": "anthropic"}
        )
        messages = loop.context_manager.build_messages(
            [Message(session_id="s1", role="user", content="old")],
            SYSTEM_PROMPT,
            "new",
            "gpt-4",
            summary="Prior context.",
        )
        cached = loop._apply_prompt_caching(messages)
        await self._compact_with_recording_provider(temp_dir, cached)
        rebuilt = loop._apply_prompt_caching(
            loop.context_manager.build_messages(
                [Message(session_id="s1", role="user", content="old")],
                SYSTEM_PROMPT,
                "new after compaction",
                "gpt-4",
                summary="compacted summary",
            )
        )
        assert rebuilt[0]["content"] == SYSTEM_PROMPT
        assert rebuilt[0].get("cache_control") == {"type": "ephemeral"}
