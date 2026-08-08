"""Regression tests for agent-loop fixes.

Covers:
- P0-1: hard-stop the loop when a turn re-issues already-executed calls.
- P0-2: never emit the same final answer text more than once.
- P0-3: usage accounting is reset per request (no cross-prompt leakage).
"""

import pytest

from server.agents.loop import AgentLoop
from server.config.settings import AppSettings
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
