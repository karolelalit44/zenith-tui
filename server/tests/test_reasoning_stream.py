"""QA-1: Reasoning must never be folded into assistant content.

Regression guard for the reasoning-fold bug in ``llm_stream.stream_completion``:
when a reasoning-capable model produced little/no real content but long
chain-of-thought, the old code assigned ``reasoning_text`` to ``response_text``,
leaking private chain-of-thought into the user-visible assistant transcript.

New contract:
- reasoning is only ever surfaced as a ``thinking`` event (kept collapsed/private
  in the UI), never as ``message`` content;
- a reasoning-only turn has empty assistant content, so the loop reports it as
  an empty response rather than fabricating a message from chain-of-thought.
"""

import asyncio

from server.agents.llm_stream import stream_completion
from server.domain.events import EventKind
from server.providers.base import BaseProvider


class _ReasoningOnlyProvider(BaseProvider):
    """Emits no real content but a long reasoning stream (reasoning-capable model)."""

    def __init__(self, content: str = "", reasoning: str = "x" * 300):
        super().__init__("reasoning", "reasoning-model")
        self._content = content
        self._reasoning = reasoning

    async def complete(self, messages, tools=None):
        return self._content or self._reasoning[:30]

    async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
        # Reasoning first, then a tiny/empty content payload — the shape that
        # used to trigger the fold.
        yield (None, self._reasoning)
        if self._content:
            yield (self._content, None)

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["reasoning-model"]


def _collect_events(provider, messages=None):
    events = []

    async def consume():
        async for ev in stream_completion(provider, messages or [], [], "s1", 1):
            events.append(ev)

    asyncio.run(consume())
    return events


def test_reasoning_only_turn_does_not_leak_as_assistant_content():
    provider = _ReasoningOnlyProvider()
    events = _collect_events(provider)

    # Reasoning is surfaced as private `thinking` events, never as `message`.
    # Streaming contract: throttled partial events, then ONE final non-partial
    # event carrying the complete text and the measured duration.
    kinds = {ev.kind for ev in events}
    assert kinds == {EventKind.THINKING}, kinds
    thinking_events = [ev for ev in events if ev.kind is EventKind.THINKING]
    partials = [ev for ev in thinking_events if ev.data.get("partial") is True]
    finals = [ev for ev in thinking_events if ev.data.get("partial") is not True]
    assert len(finals) == 1
    final_event = finals[0]
    assert final_event.data["text"] == "x" * 300
    assert isinstance(final_event.data.get("duration"), int)
    for pev in partials:
        assert final_event.data["text"].startswith(pev.data["text"])

    # No assistant content is fabricated from chain-of-thought.
    message_events = [ev for ev in events if ev.kind is EventKind.MESSAGE]
    assert message_events == []


def test_tiny_content_plus_long_reasoning_stays_content_only():
    """Even with a tiny real-content payload, reasoning must not be folded in."""
    provider = _ReasoningOnlyProvider(content="ok")
    events = _collect_events(provider)

    messages = [ev for ev in events if ev.kind is EventKind.MESSAGE]
    thinking = [ev for ev in events if ev.kind is EventKind.THINKING]

    # The assistant message is exactly the real content, nothing else.
    assert len(messages) == 1
    assert messages[0].data["text"] == "ok"
    # Reasoning ends with exactly one final thinking event, not merged into prose.
    finals = [ev for ev in thinking if ev.data.get("partial") is not True]
    assert len(finals) == 1
    assert finals[0].data["text"] == "x" * 300
