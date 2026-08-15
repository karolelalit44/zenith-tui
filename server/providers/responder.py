from __future__ import annotations

import logging

from server.config.constants import MAX_EVENT_OUTPUT
from server.domain.events import Event, EventKind

logger = logging.getLogger(__name__)


def event(kind: EventKind, data: dict, session_id: str) -> Event:
    return Event(kind=kind, data=data, session_id=session_id)


def thinking(text: str, session_id: str) -> Event:
    return event(EventKind.THINKING, {"text": text}, session_id)


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
    message: str, session_id: str, iterations: int = 0, token_info: dict | None = None
) -> Event:
    data: dict = {"message": message, "iterations": iterations}
    if token_info:
        data["tokenInfo"] = token_info
    return event(EventKind.SUCCESS, data, session_id)


def turn_manifest(payload: dict, session_id: str) -> Event:
    return event(EventKind.TURN_MANIFEST, dict(payload), session_id)


def progress(percent: int, status: str, session_id: str, iteration: int = 0) -> Event:
    return event(
        EventKind.PROGRESS,
        {"percent": percent, "label": status, "steps": [], "iteration": iteration},
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
    session_id: str, reason: str, used: int = 0, total: int = 0
) -> Event:
    return event(
        EventKind.CONTEXT_COMPACTION_STARTED,
        {"reason": reason, "used": used, "total": total},
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
) -> Event:
    data: dict = {
        "reason": reason,
        "used": used,
        "total": total,
        "tokensSaved": tokens_saved,
        "summaryChars": summary_chars,
    }
    if summary:
        data["summary"] = summary
    if preserved:
        data["preserved"] = preserved
    if failed:
        data["failed"] = True
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
) -> Event:
    data: dict = {"phase": phase}
    if label:
        data["label"] = label
    if before_tokens is not None:
        data["beforeTokens"] = before_tokens
    if after_tokens is not None:
        data["afterTokens"] = after_tokens
    return event(
        EventKind.CONTEXT_COMPACTION_PHASE,
        data,
        session_id,
    )
