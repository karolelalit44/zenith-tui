"""Tool execution — validation, safety checks, execution, and post-hooks."""

from __future__ import annotations

import json
import logging
import time as _time
from typing import Awaitable, Callable

from core.events import Event
from tools.base import ToolResult
from tools.command_safety import assess_command
from tools.param_normalizer import normalize_file_params
from tools.registry import ToolRegistry
from providers import responder as r
from workspace.git import GitOps
from .validation import (
    REFLECTION_ERROR_LIMIT,
    detect_placeholders,
    check_python_syntax,
    detect_interactive_command,
    strip_cd_prefix,
)

logger = logging.getLogger(__name__)


def validate_tool_calls(tool_calls: list[dict], registered_tools: set[str]) -> tuple[list[dict], list[str]]:
    """Filter hallucinated tool names. Returns (valid_calls, invalid_names)."""
    valid, invalid = [], []
    for tc in tool_calls:
        name = tc.get("tool", "")
        (valid if name in registered_tools else invalid).append(tc)
    return valid, invalid


def format_tool_result(tool_name: str, result: ToolResult, max_output: int = 10000) -> str:
    """Format a tool result for LLM consumption."""
    status = "SUCCESS" if result.success else "FAILED"
    lines = [f"[Tool: {tool_name} | Status: {status}]"]
    if result.output:
        output = result.output
        if len(output) > max_output:
            output = output[:max_output] + f"\n... (truncated, {len(result.output)} total chars)"
        lines.append(output)
    if result.error:
        lines.append(f"Error: {result.error}")
    if result.metadata:
        meta_str = json.dumps(result.metadata)
        if len(meta_str) < 200:
            lines.append(f"Metadata: {meta_str}")
    return "\n".join(lines)


def build_tool_metadata(tool_name: str, tool_params: dict, result: ToolResult, duration_ms: int) -> dict:
    """Build tool-specific metadata for tool_result events."""
    if tool_name in ("bash", "terminal"):
        cmd = str(tool_params.get("command") or "")
        out_lines = result.output.split("\n") if result.output else []
        exit_code = result.metadata.get("exit_code", 0) if result.metadata else 0
        return {"command": cmd, "output_lines": out_lines, "duration_ms": duration_ms, "exit_code": exit_code}
    elif tool_name == "file_write":
        return {"path": tool_params.get("filepath") or tool_params.get("path") or "", "content": tool_params.get("content", ""), "match": "exact"}
    elif tool_name == "file_edit":
        return {"path": tool_params.get("filepath") or tool_params.get("path") or "", "old_content": tool_params.get("old_content", ""), "new_content": tool_params.get("new_content", ""), "match": "exact"}
    elif tool_name in ("file_delete", "file_read"):
        return {"path": tool_params.get("filepath") or tool_params.get("path") or ""}
    return {}


def apply_bash_prechecks(
    tool_params: dict,
    workspace_root: str,
) -> str | None:
    """Run bash-specific pre-execution checks. Returns error/warning message or None."""
    command = strip_cd_prefix(tool_params.get("command", ""))
    if command != tool_params.get("command", ""):
        tool_params["command"] = command
        logger.info("Stripped cd prefix, command now: %s", command)
    err = check_python_syntax(command, workspace_root)
    if err:
        return err
    return detect_interactive_command(command)


def validate_tool_rejection(tool_name: str, tool_params: dict, created_files: set[str], workspace_root: str) -> str | None:
    """Run all pre-execution validation checks. Returns rejection message or None."""
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
    """Check for placeholder content or invalid file_edit. Returns rejection message or None."""
    placeholder = detect_placeholders(tool_params)
    if placeholder:
        return placeholder
    if tool_name == "file_edit" and not tool_params.get("old_content"):
        return "old_content cannot be empty. Use file_read first to get the current content."
    return None


def check_self_delete(tool_name: str, tool_params: dict, created_files: set[str]) -> str | None:
    """Check if model tries to delete a file it just created. Returns rejection message or None."""
    if tool_name != "file_delete":
        return None
    target = tool_params.get("filepath") or tool_params.get("path") or ""
    if target in created_files:
        return (
            f"Refusing to delete '{target}' — this file was created in the current session. "
            f"Only delete files that existed before this session."
        )
    return None


async def confirm_risky_command(
    tool_params: dict,
    confirm_callback: Callable[[str, str, str], Awaitable[bool]],
) -> bool:
    """Ask user to confirm risky bash commands. Returns True if approved."""
    command = tool_params.get("command", "")
    assessment = assess_command(command)
    if not assessment.is_risky:
        return True
    logger.info("RISKY COMMAND: '%s' reason=%s level=%s", command, assessment.reason, assessment.risk_level)
    try:
        return await confirm_callback("bash", assessment.reason, assessment.risk_level)
    except Exception:
        return False


async def execute_tool(
    tool_registry: ToolRegistry,
    tool_name: str,
    tool_params: dict,
    workspace_root: str,
    mode: str,
) -> tuple[ToolResult, int]:
    """Execute a tool and return (result, duration_ms). Handles auto-retry for file_write."""
    start = _time.monotonic()
    result = await tool_registry.execute(tool_name, tool_params, workspace_root, mode)
    duration_ms = int((_time.monotonic() - start) * 1000)

    if (tool_name == "file_write" and not result.success
            and "already exists" in (result.error or "")
            and not tool_params.get("overwrite")):
        tool_params["overwrite"] = True
        logger.info("Auto-retrying file_write with overwrite=True")
        start = _time.monotonic()
        result = await tool_registry.execute(tool_name, tool_params, workspace_root, mode)
        duration_ms = int((_time.monotonic() - start) * 1000)

    return result, duration_ms


async def post_execution_hooks(
    tool_name: str,
    tool_params: dict,
    result: ToolResult,
    workspace_root: str,
    session_id: str,
) -> list[Event]:
    """Run post-execution hooks (auto-lint, tracking). Returns events to yield."""
    events: list[Event] = []
    edited_path = tool_params.get("filepath") or tool_params.get("path") or ""

    if tool_name in ("file_edit", "file_write") and result.success and edited_path:
        try:
            from tools.auto_lint import run_lint, format_lint_result
            lint_result = await run_lint(edited_path, workspace_root)
            if lint_result and not lint_result.success:
                lint_msg = format_lint_result(lint_result)
                if lint_msg:
                    events.append(r.warning(f"Lint issues detected:\n{lint_msg}", session_id))
        except Exception as e:
            logger.debug("Auto-lint failed: %s", e)

    return events


def auto_commit(workspace_root: str, files: list[str]) -> None:
    """Attempt auto-commit of edited files. Best-effort, no events."""
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


async def reject_tool(tool_name: str, reason: str, session_id: str) -> tuple[Event, str]:
    """Build rejection warning and context feedback for the LLM."""
    warning = r.warning(f"Tool '{tool_name}' rejected: {reason}", session_id)
    feedback = f"[Tool rejected] {reason} Please provide the actual content, not a placeholder."
    return warning, feedback
