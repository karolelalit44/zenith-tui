from __future__ import annotations

import logging
from typing import AsyncIterator

from .adapters import Chunk
from .parser import clean_tool_text, parse_tool_calls
from zenith.core.events import Event, EventKind

logger = logging.getLogger(__name__)


def event(kind: EventKind, data: dict, session_id: str) -> Event:
    return Event(kind=kind, data=data, session_id=session_id)


def thinking(text: str, session_id: str) -> Event:
    return event(EventKind.THINKING, {"text": text}, session_id)


def summary(action: str, text: str, session_id: str) -> Event:
    return event(EventKind.SUMMARY, {"action": action, "text": text}, session_id)


def warning(message: str, session_id: str) -> Event:
    return event(EventKind.WARNING, {"message": message}, session_id)


def error(message: str, session_id: str, code: str = "", recoverable: bool = False) -> Event:
    return event(EventKind.ERROR, {
        "message": message, "code": code, "recoverable": recoverable,
    }, session_id)


def progress(percent: int, status: str, session_id: str, iteration: int = 0) -> Event:
    return event(EventKind.PROGRESS, {
        "percent": percent, "label": status, "steps": [], "iteration": iteration,
    }, session_id)


def analysis(tool_name: str, session_id: str, params: dict | None = None) -> Event:
    return event(EventKind.ANALYSIS, {
        "tool": tool_name, "params": params or {},
        "text": f"Executing {tool_name}...",
    }, session_id)


def tool_result(tool_name: str, success: bool, session_id: str, output: str = "", error: str = "") -> Event:
    return event(
        EventKind.SUCCESS if success else EventKind.ERROR,
        {"tool": tool_name, "result": {
            "success": success, "output": output[:500] if output else "", "error": error,
        }},
        session_id,
    )


def file_event(kind: EventKind, path: str, content: str, session_id: str) -> Event:
    return event(kind, {"path": path, "filepath": path, "content": content}, session_id)


def terminal_event(command: str, output: list[str], duration: int, session_id: str) -> Event:
    return event(EventKind.TERMINAL, {
        "command": command,
        "output": output,
        "duration": duration,
    }, session_id)


def success(message: str, session_id: str, iterations: int = 0, token_info: dict | None = None) -> Event:
    data: dict = {
        "message": message, "filesCreated": [], "commandsExecuted": [],
        "iterations": iterations,
    }
    if token_info:
        data["tokenInfo"] = token_info
    return event(EventKind.SUCCESS, data, session_id)


def message_event(text: str, session_id: str, partial: bool = False) -> Event:
    return event(EventKind.MESSAGE, {"text": text, "partial": partial}, session_id)


async def stream_tokens(
    token_stream: AsyncIterator[tuple[str, str | None]],
    session_id: str,
) -> AsyncIterator[Event]:
    reasoning_buffer = ""
    has_yielded_content = False
    async for content, reasoning in token_stream:
        if reasoning:
            reasoning_buffer += reasoning
        if content:
            if reasoning_buffer and not has_yielded_content:
                yield thinking(reasoning_buffer, session_id)
                reasoning_buffer = ""
            has_yielded_content = True
            yield message_event(content, session_id, partial=True)
    if reasoning_buffer:
        yield thinking(reasoning_buffer, session_id)
