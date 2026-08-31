"""Tests for the transport event-adapter (module 10).

Covers the Parts -> EventKind mapping used to keep the TUI working against the
clean part-based content stream (G5), and the fan-out behaviour of
``iter_client_events``.
"""

from __future__ import annotations

import asyncio

from server.api.event_adapter import adapt_part, adapt_parts, iter_client_events
from server.domain.events import Event, EventKind
from server.providers.responder import (
    ContentPart,
    PartKind,
    error_part,
    reasoning_part,
    text_part,
    tool_call_part,
    tool_result_part,
)
from server.toolkit.base import MAX_TOOL_OUTPUT_BASELINE


def _ev(kind: EventKind, data: dict, session_id: str = "s1") -> Event:
    return Event(kind=kind, data=data, session_id=session_id)


def test_adapt_text_part_to_message():
    ev = adapt_part(text_part("hello"), "s1")
    assert ev.kind is EventKind.MESSAGE
    assert ev.session_id == "s1"
    assert ev.data["text"] == "hello"
    assert ev.data["partial"] is False


def test_adapt_reasoning_part_to_thinking():
    ev = adapt_part(reasoning_part("thinking...", partial=True, duration_ms=12), "s1")
    assert ev.kind is EventKind.THINKING
    assert ev.data["text"] == "thinking..."
    assert ev.data["partial"] is True
    assert ev.data["duration"] == 12


def test_adapt_tool_call_part():
    ev = adapt_part(tool_call_part("bash", {"command": "ls"}), "s1")
    assert ev.kind is EventKind.TOOL_CALL
    assert ev.data["tool"] == "bash"
    assert ev.data["params"] == {"command": "ls"}


def test_adapt_tool_result_part_success():
    ev = adapt_part(tool_result_part("bash", output="done", success=True), "s1")
    assert ev.kind is EventKind.TOOL_RESULT
    assert ev.data["tool"] == "bash"
    assert ev.data["success"] is True
    assert ev.data["output"] == "done"
    assert ev.data["error"] == ""
    assert ev.data["truncated"] is False


def test_adapt_tool_result_part_error():
    ev = adapt_part(tool_result_part("bash", error="boom", success=False), "s1")
    assert ev.kind is EventKind.TOOL_RESULT
    assert ev.data["success"] is False
    assert ev.data["error"] == "boom"


def test_adapt_tool_result_does_not_apply_5k_preview_cap():
    # A large budgeted part must be delivered in full (truncated-output, no
    # 5K preview) — the adapter honours the part's budget, not MAX_EVENT_OUTPUT.
    part = ContentPart(
        type=PartKind.TOOL_RESULT, tool="bash", output="x" * (MAX_TOOL_OUTPUT_BASELINE + 500)
    )
    ev = adapt_part(part, "s1")
    assert ev.data["truncated"] is True
    assert "output truncated" in ev.data["output"]
    # Never capped down to the legacy 5000-char preview.
    assert len(ev.data["output"]) > 5000


def test_adapt_error_part():
    ev = adapt_part(error_part("bad thing"), "s1")
    assert ev.kind is EventKind.ERROR
    assert ev.data["message"] == "bad thing"


def test_adapt_part_unknown_type_raises():
    # Pydantic validates ``type`` at construction, so use a duck-typed object
    # to exercise the adapter's guard clause. None of the known-kind branches
    # match, so the adapter must raise before touching any other attribute.
    class _BadPart:
        type = "not_a_kind"

    try:
        adapt_part(_BadPart(), "s1")
    except ValueError:
        return
    raise AssertionError("expected ValueError for unknown part type")


def test_adapt_parts_returns_one_event_per_part():
    parts = [text_part("a"), reasoning_part("b"), tool_call_part("bash", {})]
    events = adapt_parts(parts, "s1")
    assert [e.kind for e in events] == [
        EventKind.MESSAGE,
        EventKind.THINKING,
        EventKind.TOOL_CALL,
    ]


async def _collect(stream) -> list[Event]:
    return [ev async for ev in stream]


def test_iter_client_events_fans_out_parts_message():
    upstream = [
        _ev(
            EventKind.MESSAGE,
            {
                "parts": [
                    text_part("hi").model_dump(exclude_none=True, exclude_defaults=False),
                    tool_call_part("bash", {"command": "ls"}).model_dump(
                        exclude_none=True, exclude_defaults=False
                    ),
                ],
                "text": "fallback",
            },
        )
    ]
    out = asyncio.run(_collect(iter_client_events(_as_async(upstream))))
    assert [e.kind for e in out] == [EventKind.MESSAGE, EventKind.TOOL_CALL]
    assert out[0].data["text"] == "hi"
    assert out[1].data["tool"] == "bash"


def test_iter_client_events_forwards_non_part_events_unchanged():
    upstream = [
        _ev(EventKind.WARNING, {"message": "w"}),
        _ev(EventKind.ERROR, {"message": "e"}),
    ]
    out = asyncio.run(_collect(iter_client_events(_as_async(upstream))))
    assert len(out) == 2
    assert out[0].kind is EventKind.WARNING
    assert out[1].kind is EventKind.ERROR
    assert out[0] is upstream[0]  # same object, not recreated


def test_iter_client_events_empty_parts_forwarded():
    upstream = [_ev(EventKind.MESSAGE, {"parts": [], "text": "t"})]
    out = asyncio.run(_collect(iter_client_events(_as_async(upstream))))
    assert len(out) == 1
    assert out[0].kind is EventKind.MESSAGE


async def _as_async(items):
    for item in items:
        yield item
