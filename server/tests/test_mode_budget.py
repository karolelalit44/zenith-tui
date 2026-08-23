"""Mode-aware context budgeting (Gap #8): per-mode tier profiles split the
input budget differently, so investigation modes retain more conversation
history and read-only mode trims the tool-schema spend."""

from server.agents.context import ContextManager
from server.agents.loop import AgentLoop, _adaptive_reserve
from server.config.constants import (
    BUILD_MODE,
    DEFAULT_CONTEXT_WINDOW,
    MODE_BUDGET_PROFILES,
    PLAN_MODE,
    READ_ONLY_MODE,
)
from server.config.settings import AppSettings
from server.domain.message import Message

SYSTEM_PROMPT = "You are Zenith, a coding agent." * 50

HISTORY_COUNT = 340
HISTORY_BODY = "data " * 260  # ~1300 chars, ~168 tokens per message


class _FakeProvider:
    async def complete(self, messages, tools=None):
        return "Done."

    async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
        for char in "Done.":
            yield (char, None)

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["test-model-xyz"]


def _base_config(**kwargs) -> AppSettings:
    defaults = dict(
        max_context_tokens=DEFAULT_CONTEXT_WINDOW,
        repo_map_enabled=False,
        memory_enabled=False,
    )
    defaults.update(kwargs)
    return AppSettings(**defaults)


def _big_history() -> list[Message]:
    return [
        Message(
            session_id="s1",
            role="assistant",
            content=f"HISTORY-MARKER-{i:04d} {HISTORY_BODY}",
        )
        for i in range(HISTORY_COUNT)
    ]


def _included_history_count(messages: list[dict]) -> int:
    joined = " ".join(str(m.get("content") or "") for m in messages)
    return sum(f"HISTORY-MARKER-{i:04d}" in joined for i in range(HISTORY_COUNT))


class TestModeHistoryBudgets:
    def test_read_only_retains_more_history_than_build(self):
        ctx = ContextManager(_base_config())
        history = _big_history()
        build = ctx.build_messages(history, SYSTEM_PROMPT, "go", "gpt-4", mode=BUILD_MODE)
        ro = ctx.build_messages(history, SYSTEM_PROMPT, "go", "gpt-4", mode=READ_ONLY_MODE)
        assert _included_history_count(build) < HISTORY_COUNT
        assert _included_history_count(ro) > _included_history_count(build)

    def test_plan_retains_more_history_than_build(self):
        ctx = ContextManager(_base_config())
        history = _big_history()
        build = ctx.build_messages(history, SYSTEM_PROMPT, "go", "gpt-4", mode=BUILD_MODE)
        plan = ctx.build_messages(history, SYSTEM_PROMPT, "go", "gpt-4", mode=PLAN_MODE)
        assert _included_history_count(plan) > _included_history_count(build)

    def test_default_mode_is_build(self):
        ctx = ContextManager(_base_config())
        history = _big_history()
        default = ctx.build_messages(history, SYSTEM_PROMPT, "go", "gpt-4")
        build = ctx.build_messages(history, SYSTEM_PROMPT, "go", "gpt-4", mode=BUILD_MODE)
        assert [m.get("content") for m in default] == [m.get("content") for m in build]

    def test_small_history_unaffected_by_mode(self):
        ctx = ContextManager(_base_config())
        history = [Message(session_id="s1", role="assistant", content="small prompt")]
        for mode in (BUILD_MODE, PLAN_MODE, READ_ONLY_MODE):
            messages = ctx.build_messages(history, SYSTEM_PROMPT, "go", "gpt-4", mode=mode)
            contents = [str(m.get("content") or "") for m in messages]
            assert any("small prompt" in c for c in contents), mode


class TestModeToolsBudgets:
    def test_profile_shares_are_ordered_and_bounded(self):
        p = MODE_BUDGET_PROFILES
        assert p[BUILD_MODE]["tools_pct"] > p[PLAN_MODE]["tools_pct"]
        assert p[PLAN_MODE]["tools_pct"] > p[READ_ONLY_MODE]["tools_pct"]
        assert p[READ_ONLY_MODE]["history_pct"] > p[PLAN_MODE]["history_pct"]
        assert p[PLAN_MODE]["history_pct"] > p[BUILD_MODE]["history_pct"]
        for mode in (BUILD_MODE, PLAN_MODE, READ_ONLY_MODE):
            shares = p[mode]["tools_pct"] + p[mode]["history_pct"] + p[mode]["summary_pct"]
            assert shares <= 1.0, mode

    def test_mode_tools_budget_ordering_on_loop(self, tmp_path):
        loop = AgentLoop(
            AppSettings(home_dir=str(tmp_path / "test.db"), workspace_root=str(tmp_path)),
            _FakeProvider(),
        )
        window = DEFAULT_CONTEXT_WINDOW
        reserve = _adaptive_reserve("test-model-xyz", window)
        input_budget = window - reserve
        p = MODE_BUDGET_PROFILES
        assert loop._mode_tools_budget("test-model-xyz", BUILD_MODE) == int(
            input_budget * p[BUILD_MODE]["tools_pct"]
        )
        assert (
            loop._mode_tools_budget("test-model-xyz", BUILD_MODE)
            > loop._mode_tools_budget("test-model-xyz", PLAN_MODE)
            > loop._mode_tools_budget("test-model-xyz", READ_ONLY_MODE)
        )

    def test_unknown_mode_falls_back_to_build(self, tmp_path):
        loop = AgentLoop(
            AppSettings(home_dir=str(tmp_path / "test.db"), workspace_root=str(tmp_path)),
            _FakeProvider(),
        )
        assert loop._mode_tools_budget("test-model-xyz", "mystery") == loop._mode_tools_budget(
            "test-model-xyz", BUILD_MODE
        )