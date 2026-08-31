"""Transport event-adapter (module 10).

Maps the clean, minimal content ``Part`` stream (module 09 ``ContentPart``:
text / reasoning / tool_call / tool_result / error) onto the TUI's existing,
long-standing ``EventKind`` set so the WebSocket JSON-RPC transport and the
TUI are preserved without rewriting the frontend (G5).

Why this exists
    The redesign's core loop emits one *part-based* message (``data.parts``)
    instead of many bespoke event kinds. The TUI, however, consumes the
    historical kinds (``thinking`` / ``message`` / ``tool_call`` /
    ``tool_result`` / ``error``). This adapter is the thin compatibility
    boundary that fans a part-bearing event out into the individual kinds the
    TUI already renders, and passes every other event through untouched.

Contract
    - :func:`adapt_part`  -> a single ``ContentPart`` -> one TUI ``Event``.
    - :func:`adapt_parts` -> a list of parts -> a list of TUI events.
    - :func:`iter_client_events` -> wraps an upstream ``AsyncIterator[Event]``
      so every ``MESSAGE`` carrying ``data.parts`` is re-expressed as the
      per-kind events the TUI understands; all other events are forwarded
      unchanged (the transport and any downstream consumer see the same
      sequence otherwise).

Additive only: no existing ``EventKind`` is removed, reordered, or retyped,
and no behaviour of the legacy transport is changed. Invented-kind *removal*
is deliberately out of scope here (see ``transport_event_contract/feature.md``
REMOVE section; it must wait for the Phase-2/3 loop swap).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from server.domain.events import Event, EventKind
from server.providers.responder import ContentPart, PartKind
from server.toolkit.base import truncate_output

logger = logging.getLogger(__name__)

# Part kinds that never carry a ``data.parts`` payload and must be forwarded
# by :func:`iter_client_events` rather than treated as a fan-out source.
_PASSTHROUGH_MESSAGE_KINDS = (EventKind.THINKING,)


def adapt_part(part: ContentPart, session_id: str) -> Event:
    """Map a single clean ``ContentPart`` to the TUI's ``EventKind``.

    Each mapping mirrors the field shape the TUI already consumes for that
    kind (see ``server/providers/responder.py``), so rendering needs no changes:
    reasoning → ``thinking``, text → ``message``, call → ``tool_call``,
    result → ``tool_result`` (full, truncated output), error → ``error``.

    Raises ``ValueError`` for an unrecognized part ``type`` so a bad upstream
    part is surfaced rather than silently dropped.
    """
    if part.type is PartKind.TEXT:
        return _event(
            EventKind.MESSAGE,
            {"text": part.text, "partial": part.partial or False, "iteration": 0},
            session_id,
        )
    if part.type is PartKind.REASONING:
        data: dict = {"text": part.text, "partial": part.partial or False}
        if part.duration_ms is not None:
            data["duration"] = part.duration_ms
        return _event(EventKind.THINKING, data, session_id)
    if part.type is PartKind.TOOL_CALL:
        return _event(
            EventKind.TOOL_CALL,
            {
                "tool": part.tool,
                "params": dict(part.input),
                "text": f"Executing {part.tool}...",
            },
            session_id,
        )
    if part.type is PartKind.TOOL_RESULT:
        kept, truncated = truncate_output(part.output)
        return _event(
            EventKind.TOOL_RESULT,
            {
                "tool": part.tool,
                "success": part.success,
                "output": kept,
                "error": part.error,
                "truncated": truncated,
                "metadata": {},
            },
            session_id,
        )
    if part.type is PartKind.ERROR:
        return _event(
            EventKind.ERROR,
            {"message": part.text or "Tool error", "code": "TOOL_ERROR", "recoverable": False},
            session_id,
        )
    raise ValueError(f"Unsupported content part type: {part.type!r}")


def adapt_parts(parts: list[ContentPart], session_id: str) -> list[Event]:
    """Map a list of parts to the corresponding TUI events, in order."""
    return [adapt_part(p, session_id) for p in parts]


async def iter_client_events(stream: AsyncIterator[Event]) -> AsyncIterator[Event]:
    """Wrap an upstream event stream so part-bearing messages fan out to kinds.

    A ``MESSAGE`` carrying ``data.parts`` is re-expressed as one event per
    part (each mapped to its TUI ``EventKind``). Events that do not carry a
    ``data.parts`` list, and the ``THINKING`` passthrough, are forwarded
    unmodified so the transport and any existing consumer see no behavioural
    change.
    """
    async for event in stream:
        if event.kind in _PASSTHROUGH_MESSAGE_KINDS:
            yield event
            continue
        raw_parts = event.data.get("parts") if isinstance(event.data, dict) else None
        if isinstance(raw_parts, list) and raw_parts:
            for part_dict in raw_parts:
                try:
                    part = ContentPart.model_validate(part_dict)
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning(
                        "Skipping unparseable part on %s (session=%s): %s",
                        event.kind,
                        event.session_id,
                        exc,
                    )
                    continue
                yield adapt_part(part, event.session_id or "")
            continue
        yield event


def _event(kind: EventKind, data: dict, session_id: str) -> Event:
    return Event(kind=kind, data=data, session_id=session_id)
