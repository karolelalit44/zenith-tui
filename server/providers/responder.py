from __future__ import annotations

import logging
from enum import StrEnum

from pydantic import BaseModel, Field

from server.config.constants import MAX_EVENT_OUTPUT
from server.domain.events import Event, EventKind
from server.toolkit.base import truncate_output

logger = logging.getLogger(__name__)


def event(kind: EventKind, data: dict, session_id: str) -> Event:
    return Event(kind=kind, data=data, session_id=session_id)


def thinking(
    text: str,
    session_id: str,
    partial: bool = False,
    duration_ms: int | None = None,
) -> Event:
    data: dict = {"text": text}
    if partial:
        data["partial"] = True
    if duration_ms is not None:
        data["duration"] = duration_ms
    return event(EventKind.THINKING, data, session_id)


def message_event(text: str, session_id: str, partial: bool = False, iteration: int = 0) -> Event:
    return event(
        EventKind.MESSAGE, {"text": text, "partial": partial, "iteration": iteration}, session_id
    )


def tool_call(tool_name: str, params: dict, session_id: str) -> Event:
    return event(
        EventKind.TOOL_CALL,
        {"tool": tool_name, "params": params, "text": f"Executing {tool_name}..."},
        session_id,
    )


def tool_result(
    tool_name: str,
    success: bool,
    session_id: str,
    output: str = "",
    error: str = "",
    metadata: dict | None = None,
) -> Event:
    max_event_output = MAX_EVENT_OUTPUT
    return event(
        EventKind.TOOL_RESULT,
        {
            "tool": tool_name,
            "success": success,
            "output": output[:max_event_output] if output else "",
            "error": error,
            "truncated": len(output) > max_event_output if output else False,
            "metadata": metadata or {},
        },
        session_id,
    )


def error(
    message: str,
    session_id: str,
    code: str = "",
    recoverable: bool = False,
    provider: str = "",
    action: str = "",
    hint: str = "",
) -> Event:
    data: dict = {"message": message, "code": code, "recoverable": recoverable}
    if provider:
        data["provider"] = provider
    if action:
        data["action"] = action
    if hint:
        data["hint"] = hint
    return event(EventKind.ERROR, data, session_id)


def warning(message: str, session_id: str, code: str = "", extra: dict | None = None) -> Event:
    data: dict = {"message": message, "code": code}
    if extra:
        data.update(extra)
    return event(EventKind.WARNING, data, session_id)


def success(
    message: str,
    session_id: str,
    iterations: int = 0,
    token_info: dict | None = None,
    elapsed_ms: int | None = None,
) -> Event:
    data: dict = {"message": message, "iterations": iterations}
    if token_info:
        data["tokenInfo"] = token_info
    if elapsed_ms is not None:
        data["elapsedMs"] = elapsed_ms
        data["duration"] = elapsed_ms
    return event(EventKind.SUCCESS, data, session_id)


def turn_manifest(payload: dict, session_id: str) -> Event:
    return event(EventKind.TURN_MANIFEST, dict(payload), session_id)


def progress(
    percent: int,
    status: str,
    session_id: str,
    iteration: int = 0,
    steps: list[dict] | None = None,
) -> Event:
    return event(
        EventKind.PROGRESS,
        {
            "percent": percent,
            "label": status,
            "steps": steps or [],
            "iteration": iteration,
        },
        session_id,
    )


def context_compacted(
    tool: str,
    chars_removed: int,
    tokens_saved: int,
    reason: str,
    session_id: str,
    original_chars: int = 0,
    compacted_chars: int = 0,
) -> Event:
    return event(
        EventKind.CONTEXT_COMPACTED,
        {
            "tool": tool,
            "charsRemoved": chars_removed,
            "tokensSaved": tokens_saved,
            "reason": reason,
            "originalChars": original_chars,
            "compactedChars": compacted_chars,
        },
        session_id,
    )


def context_compaction_started(
    session_id: str,
    reason: str,
    used: int = 0,
    total: int = 0,
    tokens: dict | None = None,
    trigger: str = "automatic",
) -> Event:
    data: dict = {
        "reason": reason,
        "used": used,
        "total": total,
        "trigger": trigger,
        "status": "started",
    }
    if tokens:
        data["tokens"] = tokens
    return event(
        EventKind.CONTEXT_COMPACTION_STARTED,
        data,
        session_id,
    )


def context_compaction_ended(
    session_id: str,
    reason: str,
    used: int = 0,
    total: int = 0,
    tokens_saved: int = 0,
    summary_chars: int = 0,
    preserved: dict | None = None,
    failed: bool = False,
    summary: str = "",
    tokens_before: dict | None = None,
    tokens_after: dict | None = None,
    trigger: str = "automatic",
    status: str = "completed",
    error: str = "",
) -> Event:
    data: dict = {
        "reason": reason,
        "used": used,
        "total": total,
        "tokensSaved": tokens_saved,
        "summaryChars": summary_chars,
        "trigger": trigger,
        "status": status,
    }
    if summary:
        data["summary"] = summary
    if preserved:
        data["preserved"] = preserved
    if failed:
        data["failed"] = True
    if error:
        data["error"] = error
    if tokens_before:
        data["tokensBefore"] = tokens_before
    if tokens_after:
        data["tokensAfter"] = tokens_after
    return event(
        EventKind.CONTEXT_COMPACTION_ENDED,
        data,
        session_id,
    )


def context_compaction_phase(
    session_id: str,
    phase: str,
    label: str = "",
    before_tokens: int | None = None,
    after_tokens: int | None = None,
    tokens_before: dict | None = None,
    tokens_after: dict | None = None,
    trigger: str = "automatic",
) -> Event:
    data: dict = {"phase": phase, "trigger": trigger}
    if label:
        data["label"] = label
    if before_tokens is not None:
        data["beforeTokens"] = before_tokens
    if after_tokens is not None:
        data["afterTokens"] = after_tokens
    if tokens_before:
        data["tokensBefore"] = tokens_before
    if tokens_after:
        data["tokensAfter"] = tokens_after
    return event(
        EventKind.CONTEXT_COMPACTION_PHASE,
        data,
        session_id,
    )


# ---------------------------------------------------------------------------
# Phase 1 additive — clean Part content delivery (module 09 markdown_render).
# Mirrors opencode AnyPart (TextPart / ReasoningPart / ToolCallPart /
# ToolResultPart) and codex EventMsg content deltas. Purely additive and
# transport-safe (G5): parts ride inside the existing MESSAGE event under
# ``data.parts`` while ``data.text`` stays the rendered markdown, so the legacy
# TUI keeps working. Full (truncated) tool output is delivered via
# ``truncate_output`` instead of the MAX_EVENT_OUTPUT preview hack (Phase 3).
# NOTE: this module-09 transport-facing reasoning part is distinct from module
# 08's ReasoningPart (llm_stream.py) to avoid a circular import (llm_stream
# imports responder).
# ---------------------------------------------------------------------------


class PartKind(StrEnum):
    TEXT = "text"
    REASONING = "reasoning"
    TOOL_CALL = "tool-call"
    TOOL_RESULT = "tool-result"
    ERROR = "error"


class ContentPart(BaseModel):
    """A single, clean, renderable content part (opencode AnyPart).

    Each part carries a ``type`` discriminator plus the relevant fields. Tool
    output is delivered truncated-but-complete, never a tiny preview.
    """

    type: PartKind
    text: str = ""
    partial: bool = False
    duration_ms: int | None = None
    tool: str = ""
    input: dict = Field(default_factory=dict)
    success: bool = True
    output: str = ""
    error: str = ""


def text_part(text: str, partial: bool = False) -> ContentPart:
    return ContentPart(type=PartKind.TEXT, text=text, partial=partial)


def reasoning_part(text: str, partial: bool = False, duration_ms: int | None = None) -> ContentPart:
    return ContentPart(
        type=PartKind.REASONING,
        text=text,
        partial=partial,
        duration_ms=duration_ms,
    )


def tool_call_part(tool: str, input_params: dict) -> ContentPart:
    return ContentPart(type=PartKind.TOOL_CALL, tool=tool, input=dict(input_params))


def tool_result_part(
    tool: str, output: str = "", success: bool = True, error: str = ""
) -> ContentPart:
    kept, _truncated = truncate_output(output or "")
    return ContentPart(
        type=PartKind.TOOL_RESULT, tool=tool, output=kept, success=success, error=error
    )


def error_part(message: str) -> ContentPart:
    return ContentPart(type=PartKind.ERROR, text=message)


def render_parts_text(parts: list[ContentPart]) -> str:
    """Render parts to a markdown/plain fallback string for the TUI.

    Text and reasoning render inline; tool calls render as a block header;
    tool results render their (truncated) output; errors render their message.
    """
    out: list[str] = []
    for p in parts:
        if p.type is PartKind.TEXT or p.type is PartKind.REASONING:
            if p.text:
                out.append(p.text)
        elif p.type is PartKind.TOOL_CALL:
            out.append(f"Executing {p.tool}...")
        elif p.type is PartKind.TOOL_RESULT:
            if p.output:
                out.append(p.output)
            if p.error:
                out.append(p.error)
        elif p.type is PartKind.ERROR:
            out.append(p.text)
    return "\n\n".join(out)


def parts_message(
    parts: list[ContentPart],
    session_id: str,
    partial: bool = False,
    iteration: int = 0,
) -> Event:
    """Emit a clean, part-based assistant message on the existing MESSAGE kind.

    ``data.parts`` carries the serialized Part list; ``data.text`` is the rendered
    markdown fallback so existing consumers/TUI are unaffected (G5).
    """
    return event(
        EventKind.MESSAGE,
        {
            "parts": [p.model_dump(exclude_none=True, exclude_defaults=False) for p in parts],
            "text": render_parts_text(parts),
            "partial": partial,
            "iteration": iteration,
        },
        session_id,
    )
