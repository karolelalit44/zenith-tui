from __future__ import annotations

import logging

from server.domain.events import Event, EventKind

logger = logging.getLogger(__name__)


def event(kind: EventKind, data: dict, session_id: str) -> Event:
    return Event(kind=kind, data=data, session_id=session_id)


def thinking(text: str, session_id: str) -> Event:
    return event(EventKind.THINKING, {"text": text}, session_id)


def message_event(text: str, session_id: str, partial: bool = False, iteration: int = 0) -> Event:
    return event(EventKind.MESSAGE, {"text": text, "partial": partial, "iteration": iteration}, session_id)


def tool_call(tool_name: str, params: dict, session_id: str) -> Event:
    return event(EventKind.TOOL_CALL, {
        "tool": tool_name, "params": params,
        "text": f"Executing {tool_name}...",
    }, session_id)


def tool_result(
    tool_name: str,
    success: bool,
    session_id: str,
    output: str = "",
    error: str = "",
    metadata: dict | None = None,
) -> Event:
    max_event_output = 5000
    return event(EventKind.TOOL_RESULT, {
        "tool": tool_name,
        "success": success,
        "output": output[:max_event_output] if output else "",
        "error": error,
        "truncated": len(output) > max_event_output if output else False,
        "metadata": metadata or {},
    }, session_id)


def error(message: str, session_id: str, code: str = "", recoverable: bool = False) -> Event:
    return event(EventKind.ERROR, {
        "message": message, "code": code, "recoverable": recoverable,
    }, session_id)


def warning(message: str, session_id: str, code: str = "", extra: dict | None = None) -> Event:
    data: dict = {"message": message, "code": code}
    if extra:
        data.update(extra)
    return event(EventKind.WARNING, data, session_id)


def success(message: str, session_id: str, iterations: int = 0, token_info: dict | None = None) -> Event:
    data: dict = {
        "message": message, "iterations": iterations,
    }
    if token_info:
        data["tokenInfo"] = token_info
    return event(EventKind.SUCCESS, data, session_id)


def progress(percent: int, status: str, session_id: str, iteration: int = 0) -> Event:
    return event(EventKind.PROGRESS, {
        "percent": percent, "label": status, "steps": [], "iteration": iteration,
    }, session_id)


def context_compacted(
    tool: str,
    chars_removed: int,
    tokens_saved: int,
    reason: str,
    session_id: str,
    original_chars: int = 0,
    compacted_chars: int = 0,
) -> Event:
    """Emit a CONTEXT_COMPACTED event with exact compaction counts (HP-4)."""
    return event(EventKind.CONTEXT_COMPACTED, {
        "tool": tool,
        "charsRemoved": chars_removed,
        "tokensSaved": tokens_saved,
        "reason": reason,
        "originalChars": original_chars,
        "compactedChars": compacted_chars,
    }, session_id)


def context_compaction_started(session_id: str, reason: str, used: int = 0, total: int = 0) -> Event:
    """Emit a CONTEXT_COMPACTION_STARTED event with the trigger reason and usage."""
    return event(EventKind.CONTEXT_COMPACTION_STARTED, {
        "reason": reason,
        "used": used,
        "total": total,
    }, session_id)


def context_compaction_ended(
    session_id: str,
    reason: str,
    used: int = 0,
    total: int = 0,
    tokens_saved: int = 0,
    summary_chars: int = 0,
) -> Event:
    """Emit a CONTEXT_COMPACTION_ENDED event with outcome counts."""
    return event(EventKind.CONTEXT_COMPACTION_ENDED, {
        "reason": reason,
        "used": used,
        "total": total,
        "tokensSaved": tokens_saved,
        "summaryChars": summary_chars,
    }, session_id)


def confirmation_request(
    confirmation_id: str,
    tool: str,
    reason: str,
    risk_level: str,
    message: str,
    session_id: str,
) -> Event:
    return event(EventKind.CONFIRMATION_REQUEST, {
        "confirmationId": confirmation_id,
        "tool": tool,
        "reason": reason,
        "riskLevel": risk_level,
        "message": message,
    }, session_id)
