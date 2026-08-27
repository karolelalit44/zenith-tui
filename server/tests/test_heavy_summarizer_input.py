"""Heavy-output isolation bounds (F1, revised).

Original incident (AGENT_RELIABILITY_PLAN §10 F1): a 1.4 M-char bash listing
was sent to a summarizer LLM untrimmed → ~208 K prompt tokens, 72 s, and the
bulk of the run's token spend.

Current contract (no LLM in the path at all):
- Heavy tool outputs are isolated deterministically: full output persisted to
  disk, ``result.output`` replaced by marker + head/tail excerpt.
- The isolation path makes ZERO provider calls — no spend, no latency spike,
  no lossy model-written summaries (which dropped paths and caused phantom-
  file hallucinations downstream).
"""

from pathlib import Path

import pytest

from server.agents.loop import AgentLoop
from server.config.constants import HEAVY_TOOL_ISOLATION_PREVIEW_CHARS
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
async def test_heavy_isolation_makes_zero_llm_calls_and_stores_full_output(config, temp_dir):
    big = _big_output()
    provider = _PromptCapturingProvider()
    agent = AgentLoop(config, provider)
    result = ToolResult(success=True, output=big)

    rel = await agent._maybe_summarize_heavy_output("sess-f1", "bash", result)

    assert rel, "heavy path should trigger for multi-MB output"
    stored = Path(config.workspace_root) / rel
    assert stored.exists()
    assert stored.read_text(encoding="utf-8") == big, "full output must be preserved on disk"
    assert result.output.startswith("Output truncated ("), result.output[:80]
    assert "file_read" in result.output
    # Deterministic excerpt budget with slack for the marker line.
    assert len(result.output) <= HEAVY_TOOL_ISOLATION_PREVIEW_CHARS + 4000
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
