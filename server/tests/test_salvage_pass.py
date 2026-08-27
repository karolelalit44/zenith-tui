"""WP3 salvage pass: harness-forced exits must never end in an empty response.

Contract under test:
- Stall cap / repetition-loop cap / iteration-budget exits trigger exactly one
  tools-free completion ("forced final round").
- The salvaged text is emitted as a normal MESSAGE event and recorded as the
  turn's final summary (persistence picks it up).
- A salvage reply that itself contains tool calls is discarded in favor of a
  deterministic digest of tool activity.
- Provider failure/timeout falls back to the same digest — the response is
  never empty and never fabricates.
- Legitimate completions (answer delivered, answer-only hatch) never invoke
  the salvage path.
"""

import pytest

from server.agents.loop import AgentLoop
from server.config.constants import SALVAGE_INSTRUCTION
from server.config.providers import ProviderConfig
from server.config.settings import AppSettings
from server.domain.events import EventKind
from server.providers.base import BaseProvider
from server.toolkit.base import BaseTool, ToolResult
from server.toolkit.registry import ToolRegistry


class EchoTool(BaseTool):
    name = "echo_tool"
    description = "Echoes its text parameter back"

    async def execute(self, params: dict, workspace_root: str) -> ToolResult:
        return ToolResult(success=True, output=str(params.get("text", "")))

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        }


def _registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(EchoTool())
    return reg


_CALL = '```tool\n{"tool": "echo_tool", "params": {"text": "hi"}}\n```'


class ScriptedProvider(BaseProvider):
    """Scripted normal turns via stream(); salvage calls land in complete()."""

    def __init__(self, turn_scripts: list[str], salvage_replies: list[str] | None = None):
        super().__init__("salvage-test", "salvage-test-model")
        self.turn_scripts = list(turn_scripts)
        self.salvage_replies = list(salvage_replies or [])
        self.stream_calls = 0
        self.complete_calls = 0
        self.salvage_prompts: list[str] = []

    def _script(self) -> str:
        script = self.turn_scripts[min(self.stream_calls, len(self.turn_scripts) - 1)]
        self.stream_calls += 1
        return script

    async def complete(self, messages, tools=None):
        self.complete_calls += 1
        last = str(messages[-1].get("content", "")) if messages else ""
        if last == SALVAGE_INSTRUCTION:
            self.salvage_prompts.append(" ".join(str(m.get("content", "")) for m in messages))
            if self.salvage_replies:
                reply = self.salvage_replies.pop(0)
                if isinstance(reply, Exception):
                    raise reply
                return reply
            return "FINAL: best-effort answer from gathered evidence."
        return ""

    async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
        response = await self.complete(messages) if not self.turn_scripts else self._script()
        for char in response:
            yield (char, None)

    async def validate(self):
        return True

    async def list_models(self):
        return ["salvage-test-model"]


@pytest.fixture
def config(temp_dir):
    return AppSettings(
        providers={"test": ProviderConfig(model="test-model", is_active=True)},
        active_provider="test",
        home_dir=str(temp_dir / "test.db"),
        workspace_root=str(temp_dir),
    )


def _events(agent, prompt="Do the thing"):
    async def collect():
        return [ev async for ev in agent.process_prompt(prompt, "s1", [], "build")]

    import asyncio

    return asyncio.run(collect())


def test_stall_exit_triggers_tools_free_salvage(config):
    """Stall finalize -> one salvage completion; answer reaches the UI."""
    provider = ScriptedProvider(
        # iter 1: real call executes; iters 2-3: identical dups -> stall cap.
        [_CALL, _CALL + "\n" + _CALL, _CALL + "\n" + _CALL],
        salvage_replies=["FINAL: found the compaction flow in loop.py."],
    )
    agent = AgentLoop(config, provider, tool_registry=_registry())

    events = _events(agent)

    messages = [
        e.data.get("text", "")
        for e in events
        if e.kind == EventKind.MESSAGE and not e.data.get("partial")
    ]
    assert any("FINAL: found the compaction flow" in t for t in messages), messages
    # Exactly one salvage completion, requested WITHOUT tools.
    assert provider.complete_calls == 1
    assert provider.salvage_prompts, "salvage instruction must reach the provider"
    success = [e for e in events if e.kind == EventKind.SUCCESS]
    assert success and "best-effort summary" in success[0].data.get("message", "")
    assert not any(e.kind == EventKind.ERROR for e in events)


def test_salvage_reply_with_tool_calls_falls_back_to_digest(config):
    """A model that keeps calling tools during salvage gets the digest."""
    tool_call_reply = '```tool\n{"tool": "echo_tool", "params": {"text": "again"}}\n```'
    provider = ScriptedProvider(
        [_CALL, _CALL + "\n" + _CALL, _CALL + "\n" + _CALL], salvage_replies=[tool_call_reply]
    )
    agent = AgentLoop(config, provider, tool_registry=_registry())

    events = _events(agent)

    texts = [
        e.data.get("text", "")
        for e in events
        if e.kind == EventKind.MESSAGE and not e.data.get("partial")
    ]
    assert any("Tool activity this turn" in t for t in texts), texts
    assert any("echo_tool" in t for t in texts), "digest must name the tools that ran"
    assert not any("again" == t for t in texts)


def test_provider_failure_falls_back_to_digest(config):
    """Salvage completion raising still yields a non-empty, truthful reply."""
    provider = ScriptedProvider(
        [_CALL, _CALL + "\n" + _CALL, _CALL + "\n" + _CALL],
        salvage_replies=[RuntimeError("provider down")],
    )
    agent = AgentLoop(config, provider, tool_registry=_registry())

    events = _events(agent)

    texts = [
        e.data.get("text", "")
        for e in events
        if e.kind == EventKind.MESSAGE and not e.data.get("partial")
    ]
    assert texts and all(t.strip() for t in texts), "no empty message may be emitted"
    assert any("Tool activity this turn" in t for t in texts)


def test_answer_only_completion_skips_salvage(config):
    """Substantive answer alongside duplicate calls finalizes without salvage."""
    answer = (
        "Here is the full overview of how compaction works in this codebase, "
        "covering triggers, automatic behavior, and the manual command."
    )
    provider = ScriptedProvider(
        [_CALL, answer + "\n" + _CALL],
        salvage_replies=["SHOULD NOT BE USED"],
    )
    agent = AgentLoop(config, provider, tool_registry=_registry())

    events = _events(agent)

    assert provider.salvage_prompts == [], "legitimate completion must not salvage"
    assert not any(e.data.get("code") == "SALVAGE" for e in events)
    assert events[-1].kind == EventKind.SUCCESS


def test_iteration_budget_exhaustion_salvages(config):
    """Always-new tool calls until the safety net -> salvage, no empty turn."""

    class AlwaysNewProvider(ScriptedProvider):
        def _script(self) -> str:
            self.stream_calls += 1
            n = self.stream_calls
            return f'```tool\n{{"tool": "echo_tool", "params": {{"text": "step-{n}"}}}}\n```'

    provider = AlwaysNewProvider(["x"], salvage_replies=["FINAL: ran out of budget."])
    agent = AgentLoop(config, provider, tool_registry=_registry())

    events = _events(agent)

    assert provider.salvage_prompts, "budget exhaustion must salvage"
    texts = [
        e.data.get("text", "")
        for e in events
        if e.kind == EventKind.MESSAGE and not e.data.get("partial")
    ]
    assert any("FINAL: ran out of budget" in t for t in texts)
    assert not any(
        e.kind == EventKind.ERROR and (e.data.get("message") or "").startswith("Empty")
        for e in events
    )
