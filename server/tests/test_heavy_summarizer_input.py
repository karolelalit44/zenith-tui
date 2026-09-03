"""Heavy-output helper is now a no-op compatibility stub."""

import pytest

from server.agents.loop import AgentLoop
from server.config.providers import ProviderConfig
from server.config.settings import AppSettings
from server.providers.base import BaseProvider
from server.toolkit.base import ToolResult


class _PromptCapturingProvider(BaseProvider):
    """Records every complete() prompt; replies with a fixed digest."""

    def __init__(self):
        super().__init__("cap", "cap-model")
        self.prompts: list[str] = []

    async def complete(self, messages, tools=None):
        content = " ".join(str(m.get("content", "")) for m in messages or [])
        self.prompts.append(content)
        return "DIGEST: directory listing of project"

    async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
        response = await self.complete(messages)
        for char in response:
            yield (char, None)

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["cap-model"]


@pytest.fixture
def config(temp_dir):
    return AppSettings(
        providers={"test": ProviderConfig(model="test-model", is_active=True)},
        active_provider="test",
        home_dir=str(temp_dir / "test.db"),
        workspace_root=str(temp_dir),
    )


def _big_output(lines: int = 120_000) -> str:
    return "\n".join(
        f"line {i}: D:\\vdo\\code\\zenith-frontend-tui\\some\\path_{i}.txt" for i in range(lines)
    )


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)


@pytest.mark.asyncio
async def test_heavy_output_no_longer_isolates(config, temp_dir):
    big = _big_output()
    provider = _PromptCapturingProvider()
    agent = AgentLoop(config, provider)
    result = ToolResult(success=True, output=big)

    rel = await agent._maybe_summarize_heavy_output("sess-f1", "bash", result)

    assert rel is None
    assert result.output == big
    # Zero LLM calls: isolation is purely mechanical now.
    assert provider.prompts == []


def test_light_outputs_skip_isolation(config, temp_dir):
    provider = _PromptCapturingProvider()
    agent = AgentLoop(config, provider)
    result = ToolResult(success=True, output="tiny")
    rel = asyncio_run(agent._maybe_summarize_heavy_output("s", "bash", result))
    assert rel is None
    assert result.output == "tiny"
    assert provider.prompts == []


def test_event_kinds_importable():
    """Guard import surface used by other suites (sanity)."""
    from server.domain.events import EventKind as _EK

    assert _EK.SUCCESS is not None
