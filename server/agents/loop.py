"""Turn loop compatibility module.

The legacy 1800-line AgentLoop has been retired in Phase 3.
All turn execution is powered by SimpleLoop (emergent stopping, doom-loop guard,
compaction). This module provides backwards-compatible aliases for remaining tests and callers.
"""

from __future__ import annotations

from server.toolkit.executor import format_tool_result as _format_tool_result

from .simple_loop import SimpleLoop
from .simple_loop import SimpleLoop as AgentLoop


def _params_label(params: dict | str = "", tool_name: str = "") -> str:
    if isinstance(params, str):
        params, tool_name = (tool_name if isinstance(tool_name, dict) else {}), params
    if not isinstance(params, dict) or not params:
        return ""
    if "tool_name" in params and len(params) == 1:
        return str(params["tool_name"])
    for key in ("command", "path", "filepath", "pattern", "query", "url"):
        val = params.get(key)
        if val is not None and str(val).strip():
            s = str(val).strip()
            if len(s) > 48:
                s = s[:48]
            return f"{key}={s}"
    return ""


_DEGENERATE_TOKENS = {
    "[tool calls]",
    "[thinking]",
    "[no output]",
}


def _is_degenerate_message(text: str | None) -> bool:
    if not text or not str(text).strip():
        return True
    return str(text).strip().lower() in _DEGENERATE_TOKENS


def _strip_write_payload_from_assistant_messages(
    messages: list[dict], target_path: str = ""
) -> list[dict]:
    import re

    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            c = msg.get("content", "")
            if (
                isinstance(c, str)
                and "file_write" in c
                and (not target_path or target_path in c)
            ):
                msg["content"] = re.sub(
                    r'("content":\s*")[^"]*(")',
                    r"\1[content omitted; file written]\2",
                    c,
                )
    return messages


__all__ = [
    "AgentLoop",
    "SimpleLoop",
    "_format_tool_result",
    "_is_degenerate_message",
    "_params_label",
    "_strip_write_payload_from_assistant_messages",
]
