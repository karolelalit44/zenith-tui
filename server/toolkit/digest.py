from __future__ import annotations

from typing import Any

from server.config.constants import TOOL_DIGEST_MAX_CHARS
from server.toolkit.base import ToolResult


def format_tool_digest(tool_name: str, tool_params: dict[str, Any], result: ToolResult) -> str:
    """Generate a compact 1-line structured digest for an executed tool result.

    Preserves critical facts (paths, counts, line ranges, exit codes, errors)
    while discarding multi-kilobyte raw outputs.
    """
    if not result.success:
        err = (result.error or "Operation failed").strip().replace("\n", " ")
        if len(err) > 180:
            err = err[:180] + "..."
        digest = f"[Tool: {tool_name} | Status: FAILED] Error: {err}"
        return digest[:TOOL_DIGEST_MAX_CHARS]

    meta = result.metadata or {}
    output_str = result.output or ""

    if tool_name == "glob":
        pattern = tool_params.get("pattern", "*")
        path = tool_params.get("path") or "."
        count = meta.get("count", len(output_str.splitlines()) if output_str else 0)
        digest = (
            f"[Tool: glob | Status: SUCCESS] Found {count} files matching '{pattern}' in '{path}'"
        )

    elif tool_name == "grep":
        pattern = tool_params.get("pattern", "")
        count = meta.get("count", len(output_str.splitlines()) if output_str else 0)
        files = meta.get("files_searched", 1)
        digest = f"[Tool: grep | Status: SUCCESS] Found {count} matches for '{pattern}' across {files} file(s)"

    elif tool_name == "file_read":
        path = tool_params.get("path") or tool_params.get("filepath") or ""
        size_kb = f"{len(output_str) / 1024:.1f} KB" if output_str else "0 KB"
        lines = len(output_str.splitlines())
        digest = f"[Tool: file_read | Status: SUCCESS] Read {lines} lines from '{path}' ({size_kb})"

    elif tool_name == "file_write":
        path = tool_params.get("path") or tool_params.get("filepath") or ""
        content = tool_params.get("content", "")
        size_kb = f"{len(content) / 1024:.1f} KB" if content else f"{len(output_str) / 1024:.1f} KB"
        lines = len(content.splitlines()) if content else len(output_str.splitlines())
        digest = f"[Tool: file_write | Status: SUCCESS] Wrote {size_kb} to '{path}' ({lines} lines)"

    elif tool_name == "file_edit":
        path = tool_params.get("path") or tool_params.get("filepath") or ""
        digest = f"[Tool: file_edit | Status: SUCCESS] Applied edit to '{path}'"

    elif tool_name == "file_delete":
        path = tool_params.get("path") or ""
        digest = f"[Tool: file_delete | Status: SUCCESS] Deleted '{path}'"

    elif tool_name in ("bash", "terminal"):
        cmd = tool_params.get("command", "")
        if len(cmd) > 50:
            cmd = cmd[:47] + "..."
        exit_code = meta.get("exit_code", 0)
        output_len = len(output_str)
        digest = f"[Tool: bash | Status: SUCCESS] Executed '{cmd}' -> exit {exit_code} ({output_len} chars output)"

    elif tool_name == "websearch":
        query = tool_params.get("query", "")
        digest = f"[Tool: websearch | Status: SUCCESS] Search for '{query}' completed ({len(output_str)} chars)"

    elif tool_name == "webfetch":
        url = tool_params.get("url", "")
        digest = f"[Tool: webfetch | Status: SUCCESS] Fetched '{url}' ({len(output_str)} chars)"

    else:
        chars = len(output_str)
        digest = f"[Tool: {tool_name} | Status: SUCCESS] Completed ({chars} chars output)"

    return digest[:TOOL_DIGEST_MAX_CHARS]
