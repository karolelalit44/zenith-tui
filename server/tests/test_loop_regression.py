"""Regression tests for agent-loop fixes.

Covers:
- P0-1: hard-stop the loop when a turn re-issues already-executed calls.
- P0-2: never emit the same final answer text more than once.
- P0-3: usage accounting is reset per request (no cross-prompt leakage).
"""

import pytest

from server.agents.loop import AgentLoop, _params_label
from server.config.settings import AppSettings
from server.domain.errors import RateLimitError
from server.domain.events import EventKind
from server.providers.base import BaseProvider
from server.toolkit import create_default_registry
from server.config.providers import ProviderConfig


class _StallProvider(BaseProvider):
    """Always emits the same final answer plus the same, already-done tool call."""

    def __init__(self):
        super().__init__("stall", "stall-model")
        self.call_count = 0

    async def complete(self, messages, tools=None):
        self.call_count += 1
        return (
            "Done. The file has been created successfully.\n"
            '```tool\n{"tool": "file_read", "params": {"path": "test.txt"}}\n```'
        )

    async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
        response = await self.complete(messages)
        for char in response:
            yield (char, None)

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["stall-model"]


async def _stream_from_complete(self, messages, tools=None, tool_choice=None, response_format=None):
    """Reusable stream() that drives complete() per char (same as _StallProvider)."""
    response = await self.complete(messages, tools)
    for char in response:
        yield (char, None)


class _ScatteredFailureProvider(BaseProvider):
    """Fails often, but always recovers with a success between failures.

    The failure streak never exceeds 1, so REFLECTION_LIMIT (which counts
    CONSECUTIVE failures) must NOT fire and the task must complete normally.
    """

    def __init__(self):
        super().__init__("scattered", "scattered-model")
        self.call_count = 0

    async def complete(self, messages, tools=None):
        self.call_count += 1
        n = self.call_count
        if n > 12:
            return "The task is complete after recovering from scattered errors."
        if n % 2 == 1:
            i = (n + 1) // 2
            return f'```tool\n{{"tool": "file_read", "params": {{"path": "missing_{i}.txt"}}}}\n```'
        i = n // 2
        return f'```tool\n{{"tool": "file_write", "params": {{"path": "created_{i}.txt", "content": "x"}}}}\n```'

    stream = _stream_from_complete

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["scattered-model"]


class _ConsecutiveFailureProvider(BaseProvider):
    """Emits a fresh failing call every iteration, never the same signature twice."""

    def __init__(self):
        super().__init__("consec", "consec-model")
        self.call_count = 0

    async def complete(self, messages, tools=None):
        self.call_count += 1
        i = self.call_count
        return f'```tool\n{{"tool": "file_read", "params": {{"path": "missing_{i}.txt"}}}}\n```'

    stream = _stream_from_complete

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["consec-model"]


class _RateLimitProvider(BaseProvider):
    """Raises a non-recoverable rate limit on the first stream call."""

    def __init__(self):
        super().__init__("ratelimit", "ratelimit-model")

    async def complete(self, messages, tools=None):
        raise RateLimitError(
            "free-models-per-day quota", provider="ratelimit", retry_after=3600, recoverable=False
        )

    async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
        # An async generator that raises on first iteration (matches LLMProvider).
        if False:
            yield None
        raise RateLimitError(
            "free-models-per-day quota", provider="ratelimit", retry_after=3600, recoverable=False
        )

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["ratelimit-model"]


@pytest.fixture
def test_config(temp_dir):
    return AppSettings(
        providers={"test": ProviderConfig(model="test-model", is_active=True)},
        active_provider="test",
        db_path=str(temp_dir / "test.db"),
        workspace_root=str(temp_dir),
    )


@pytest.mark.asyncio
async def test_loop_hard_stops_on_repeated_identical_calls(test_config):
    """P0-1: the loop must terminate instead of re-invoking the LLM forever."""
    provider = _StallProvider()
    agent = AgentLoop(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for event in agent.process_prompt("Do the work", "s1", [], "build"):
        events.append(event)

    # Bound: first call executes the tool, second is a repeat (continue), third
    # breaks at the top-of-loop task_completed check. Definitely not a runaway.
    assert provider.call_count <= 3, f"loop re-invoked the LLM {provider.call_count} times"
    assert events[-1].kind == EventKind.SUCCESS


@pytest.mark.asyncio
async def test_final_answer_is_emitted_exactly_once(test_config):
    """P0-2: the same closing text must not be rendered multiple times."""
    provider = _StallProvider()
    agent = AgentLoop(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for event in agent.process_prompt("Do the work", "s1", [], "build"):
        events.append(event)

    final_texts = [
        e.data.get("text")
        for e in events
        if e.kind == EventKind.MESSAGE and (e.data.get("text") or "").startswith("Done.")
    ]
    assert len(final_texts) == 1, f"final answer emitted {len(final_texts)} times: {final_texts}"


@pytest.mark.asyncio
async def test_scattered_failures_do_not_trigger_reflection_limit(test_config):
    """B2: failures interleaved with successes (max streak 1) must not abort.

    Six failures would trip the old total-count limit (4); with consecutive-
    failure counting the task must recover and finish normally.
    """
    provider = _ScatteredFailureProvider()
    agent = AgentLoop(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for event in agent.process_prompt("Do the work", "s1", [], "build"):
        events.append(event)

    limit_errors = [
        e
        for e in events
        if e.kind == EventKind.ERROR and (e.data.get("code") or "") == "REFLECTION_LIMIT"
    ]
    assert not limit_errors, f"REFLECTION_LIMIT fired despite scattered failures: {limit_errors}"

    writes = [
        e
        for e in events
        if e.kind == EventKind.TOOL_RESULT
        and e.data.get("tool") == "file_write"
        and e.data.get("success")
    ]
    assert len(writes) == 6, f"expected 6 successful writes, got {len(writes)}"
    assert any((e.data.get("text") or "").startswith("The task is complete") for e in events), (
        "final answer never emitted"
    )


@pytest.mark.asyncio
async def test_consecutive_failures_trigger_reflection_limit(test_config):
    """B2: an uninterrupted streak of failures still aborts the task."""
    provider = _ConsecutiveFailureProvider()
    agent = AgentLoop(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for event in agent.process_prompt("Do the work", "s1", [], "build"):
        events.append(event)

    limit_errors = [
        e
        for e in events
        if e.kind == EventKind.ERROR and (e.data.get("code") or "") == "REFLECTION_LIMIT"
    ]
    assert limit_errors, "REFLECTION_LIMIT should fire on a streak of consecutive failures"
    assert limit_errors[0].data.get("recoverable") is True


@pytest.mark.asyncio
async def test_rate_limit_error_does_not_emit_empty_response(test_config):
    """T3: a provider error must not also trigger a spurious EMPTY_RESPONSE."""
    provider = _RateLimitProvider()
    agent = AgentLoop(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for event in agent.process_prompt("Do the work", "s1", [], "build"):
        events.append(event)

    codes = [e.data.get("code") for e in events if e.kind == EventKind.ERROR]
    assert "RATE_LIMIT" in codes, f"expected the rate-limit error, got: {codes}"
    assert "EMPTY_RESPONSE" not in codes, f"spurious empty-response error emitted: {codes}"


class _UsageResetProvider(BaseProvider):
    def __init__(self):
        super().__init__("usage", "usage-model")
        self._cumulative_usage = {"total_tokens": 50000, "cached_tokens": 1000}
        self.reset_calls = 0

    def _reset_cumulative_usage(self) -> None:
        self.reset_calls += 1
        self._cumulative_usage = {}

    async def complete(self, messages, tools=None):
        return "ok"

    async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
        for char in "ok":
            yield (char, None)

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["usage-model"]


@pytest.mark.asyncio
async def test_usage_accounting_is_reset_per_request(test_config):
    """P0-3: provider usage must not leak from one prompt to the next."""
    provider = _UsageResetProvider()
    agent = AgentLoop(test_config, provider, tool_registry=create_default_registry())

    async for _event in agent.process_prompt("First prompt", "s1", [], "build"):
        pass

    assert provider.reset_calls >= 1, "process_prompt did not reset cumulative usage"
    assert provider._cumulative_usage == {}, "cumulative usage carried over across requests"


class _ToolsProbeProvider(BaseProvider):
    """Records the tools offered on iteration 1."""

    def __init__(self):
        super().__init__("probe", "probe-model")
        self.first_turn_tools: list[dict] | None = None

    async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
        if self.first_turn_tools is None:
            self.first_turn_tools = list(tools or [])
        yield ("I looked around. Nothing to do here.", None)

    async def complete(self, messages, tools=None):
        return ""

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["probe-model"]


def test_params_label_is_readable_for_multi_arg_calls():
    """'Skipped calls' warnings must distinguish calls; file_write(path=...)
    instead of an ambiguous file_write()."""
    assert _params_label({}) == ""
    assert _params_label({"path": "app/main.py", "content": "x"}) == "path=app/main.py"
    assert _params_label({"pattern": "**/*"}) == "pattern=**/*"
    assert _params_label({"tool_name": "todo"}) == "todo"
    long_cmd = "Get-ChildItem -Recurse | Format-Table -AutoSize"
    label = _params_label({"command": long_cmd})
    assert label.startswith("command=")
    assert len(label) <= 48 + len("command="), "long values must be truncated"


@pytest.mark.asyncio
async def test_non_code_prompt_still_gets_tools_on_iteration_one(test_config):
    """The removed code-relevance gate used to strip ALL tools from iteration 1
    for prompts that didn't 'look like code' (e.g. 'research this product'). The
    loop must always offer tools and let the model decide via tool_choice."""
    provider = _ToolsProbeProvider()
    agent = AgentLoop(test_config, provider, tool_registry=create_default_registry())

    async for _event in agent.process_prompt(
        "What does this product do? research it online", "s1", [], "build"
    ):
        pass

    assert provider.first_turn_tools is not None, "model was not offered any tools"
    assert provider.first_turn_tools, "iteration-1 tool list must not be empty"
    offered = {t["function"]["name"] for t in provider.first_turn_tools}
    assert "file_read" in offered
    # T1 (token strategy): the lean seed no longer ships the large web schemas on
    # every turn. Research tools stay reachable - a direct call to an unseeded
    # tool auto-escalates it, and discover_capabilities lists what exists
    # (see test_build_seed_is_lean_and_web_tools_still_escalate).
    assert "websearch" not in offered, "web schemas should not be in the lean default seed"
    assert "discover_capabilities" in offered, "discovery tools must remain offered"


class _ManifestProvider(BaseProvider):
    """Emits one file_write then succeeds, so the loop finishes with a manifest."""

    def __init__(self):
        super().__init__("manifest", "manifest-model")
        self.call_count = 0

    async def complete(self, messages, tools=None):
        self.call_count += 1
        if self.call_count == 1:
            return '```tool\n{"tool": "file_write", "params": {"path": "test_manifest.txt", "content": "ok"}}\n```'
        return "Done. The file has been created successfully."

    stream = _stream_from_complete

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["manifest-model"]


@pytest.mark.asyncio
async def test_success_path_emits_turn_manifest(test_config):
    """P0-5: a successful turn must emit turn_manifest before the terminal success."""
    from server.domain.events import EventKind

    provider = _ManifestProvider()
    agent = AgentLoop(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for event in agent.process_prompt("Create a file", "s1", [], "build"):
        events.append(event)

    kinds = [e.kind for e in events]
    assert EventKind.TURN_MANIFEST in kinds, "turn_manifest event missing on success"
    manifest_events = [e for e in events if e.kind == EventKind.TURN_MANIFEST]
    manifest = manifest_events[-1].data
    assert "test_manifest.txt" in manifest.get("created", [])
    success_events = [e for e in events if e.kind == EventKind.SUCCESS]
    assert len(success_events) == 1
    assert "manifest" in success_events[0].data, "success event missing manifest payload"


class _StalledProvider(BaseProvider):
    """Repeatedly emits the same file_write, forcing stall-finalize."""

    def __init__(self):
        super().__init__("stalled", "stalled-model")
        self.call_count = 0

    async def complete(self, messages, tools=None):
        self.call_count += 1
        return (
            "I will keep working.\n"
            '```tool\n{"tool": "file_write", "params": {"path": "stalled.txt", "content": "x"}}\n```'
        )

    stream = _stream_from_complete

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["stalled-model"]


@pytest.mark.asyncio
async def test_stall_finalize_emits_turn_manifest(test_config):
    """P0-5: a stalled turn must emit turn_manifest with remaining steps."""
    from server.domain.events import EventKind

    provider = _StalledProvider()
    agent = AgentLoop(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for event in agent.process_prompt("Stall me", "s1", [], "build"):
        events.append(event)

    kinds = [e.kind for e in events]
    assert EventKind.TURN_MANIFEST in kinds, "turn_manifest event missing on stall"
    manifest_events = [e for e in events if e.kind == EventKind.TURN_MANIFEST]
    manifest = manifest_events[-1].data
    assert manifest.get("stalled") is True
    success_events = [e for e in events if e.kind == EventKind.SUCCESS]
    assert len(success_events) == 1
    assert "manifest" in success_events[0].data, "stall success missing manifest payload"
