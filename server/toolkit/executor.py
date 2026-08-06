from __future__ import annotations

import json
import logging
import time as _time

from server.config.constants import DEFAULT_CONTEXT_WINDOW
from server.agents.validation import (
    check_python_syntax,
    detect_interactive_command,
    detect_placeholders,
    strip_cd_prefix,
)
from server.domain.events import Event
from server.providers import responder as r
from server.toolkit.base import ToolResult
from server.toolkit.registry import ToolRegistry
from server.workspace.git import GitOps

logger = logging.getLogger(__name__)


def validate_tool_calls(
    tool_calls: list[dict], registered_tools: set[str]
) -> tuple[list[dict], list[str]]:
    valid, invalid = ([], [])
    for tc in tool_calls:
        name = tc.get("tool", "")
        (valid if name in registered_tools else invalid).append(tc)
    return (valid, invalid)


def _dynamic_max_output(context_window: int | None = None) -> int:
    if context_window is None:
        return 10000
    if context_window >= 1000000:
        return 50000
    if context_window >= 200000:
        return 25000
    if context_window >= DEFAULT_CONTEXT_WINDOW:
        return 15000
    return 10000


def format_tool_result(tool_name: str, result: ToolResult, max_output: int = 10000) -> str:
    from server.agents.compaction import compact_tool_output

    status = "SUCCESS" if result.success else "FAILED"
    lines = [f"[Tool: {tool_name} | Status: {status}]"]
    if result.output:
        compacted, _stats = compact_tool_output(result.output, max_output=max_output)
        lines.append(compacted)
    if result.error:
        lines.append(f"Error: {result.error}")
    if result.metadata:
        meta_str = json.dumps(result.metadata)
        if len(meta_str) < 200:
            lines.append(f"Metadata: {meta_str}")
    return "\n".join(lines)


def build_tool_metadata(
    tool_name: str, tool_params: dict, result: ToolResult, duration_ms: int
) -> dict:
    if tool_name in ("bash", "terminal"):
        cmd = str(tool_params.get("command") or "")
        out_lines = result.output.split("\n") if result.output else []
        exit_code = result.metadata.get("exit_code", 0) if result.metadata else 0
        return {
            "command": cmd,
            "output_lines": out_lines,
            "duration_ms": duration_ms,
            "exit_code": exit_code,
        }
    elif tool_name == "file_write":
        return {
            "path": tool_params.get("filepath") or tool_params.get("path") or "",
            "content": tool_params.get("content", ""),
            "match": "exact",
        }
    elif tool_name == "file_edit":
        return {
            "path": tool_params.get("filepath") or tool_params.get("path") or "",
            "old_content": tool_params.get("old_content", ""),
            "new_content": tool_params.get("new_content", ""),
            "match": "exact",
        }
    elif tool_name in ("file_delete", "file_read"):
        return {"path": tool_params.get("filepath") or tool_params.get("path") or ""}
    return {}


def apply_bash_prechecks(tool_params: dict, workspace_root: str) -> str | None:
    command = strip_cd_prefix(tool_params.get("command", ""))
    if command != tool_params.get("command", ""):
        tool_params["command"] = command
        logger.info("Stripped cd prefix, command now: %s", command)
    err = check_python_syntax(command, workspace_root)
    if err:
        return err
    return detect_interactive_command(command)


def validate_tool_rejection(
    tool_name: str, tool_params: dict, created_files: set[str], workspace_root: str
) -> str | None:
    msg = check_placeholder_and_edit(tool_name, tool_params)
    if msg:
        return msg
    msg = check_self_delete(tool_name, tool_params, created_files)
    if msg:
        return msg
    if tool_name in ("bash", "terminal"):
        return apply_bash_prechecks(tool_params, workspace_root)
    return None


def check_placeholder_and_edit(tool_name: str, tool_params: dict) -> str | None:
    placeholder = detect_placeholders(tool_params)
    if placeholder:
        return placeholder
    if tool_name == "file_edit" and (not tool_params.get("old_content")):
        return "old_content cannot be empty. Use file_read first to get the current content."
    return None


def check_self_delete(tool_name: str, tool_params: dict, created_files: set[str]) -> str | None:
    if tool_name != "file_delete":
        return None
    target = tool_params.get("filepath") or tool_params.get("path") or ""
    if target in created_files:
        return f"Refusing to delete '{target}' — this file was created in the current session. Only delete files that existed before this session."
    return None


async def execute_tool(
    tool_registry: ToolRegistry,
    tool_name: str,
    tool_params: dict,
    workspace_root: str,
    mode: str,
    allowed_mcp: dict[str, list[str]] | None = None,
) -> tuple[ToolResult, int]:
    logger.info("TOOL EXECUTE: name=%s mode=%s params=%s", tool_name, mode, str(tool_params))
    start = _time.monotonic()
    result = await tool_registry.execute(
        tool_name, tool_params, workspace_root, mode, allowed_mcp=allowed_mcp
    )
    duration_ms = int((_time.monotonic() - start) * 1000)
    logger.info(
        "TOOL RESULT: name=%s success=%s duration=%dms output_len=%d error=%s",
        tool_name,
        result.success,
        duration_ms,
        len(result.output) if result.output else 0,
        result.error if result.error else "None",
    )
    if (
        tool_name == "file_write"
        and (not result.success)
        and ("already exists" in (result.error or ""))
        and (not tool_params.get("overwrite"))
    ):
        tool_params["overwrite"] = True
        logger.info("Auto-retrying file_write with overwrite=True")
        start = _time.monotonic()
        result = await tool_registry.execute(tool_name, tool_params, workspace_root, mode)
        duration_ms = int((_time.monotonic() - start) * 1000)
        logger.info(
            "TOOL RETRY RESULT: name=%s success=%s duration=%dms",
            tool_name,
            result.success,
            duration_ms,
        )
    return (result, duration_ms)


async def post_execution_hooks(
    tool_name: str, tool_params: dict, result: ToolResult, workspace_root: str, session_id: str
) -> list[Event]:
    events: list[Event] = []
    edited_path = tool_params.get("filepath") or tool_params.get("path") or ""
    if tool_name in ("file_edit", "file_write") and result.success and edited_path:
        try:
            from server.toolkit.auto_lint import format_lint_result, run_lint

            lint_result = await run_lint(edited_path, workspace_root)
            if lint_result and (not lint_result.success):
                lint_msg = format_lint_result(lint_result)
                if lint_msg:
                    events.append(r.warning(f"Lint issues detected:\n{lint_msg}", session_id))
        except Exception as e:
            logger.debug("Auto-lint failed: %s", e)
    return events


def auto_commit(workspace_root: str, files: list[str]) -> None:
    if not files:
        return
    try:
        git = GitOps(workspace_root)
        if git.is_git_repo():
            unique = list(dict.fromkeys(files))
            result = git.commit(f"zenith: update {len(unique)} file(s)", files=unique)
            if result.get("success"):
                logger.info("AUTO-COMMIT: %s", result.get("hash", "unknown"))
            else:
                logger.debug("AUTO-COMMIT skipped: %s", result.get("error", "unknown"))
    except Exception as e:
        logger.debug("AUTO-COMMIT failed: %s", e)
