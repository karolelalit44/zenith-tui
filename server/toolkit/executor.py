from __future__ import annotations

import json
import logging
import time as _time
from pathlib import Path

from server.config.constants import (
    AUTO_LINT_FIX_ENABLED,
    BASH_TOOL,
    BASH_WORKDIR_PARAM,
    FILE_DELETE_TOOL,
    FILE_EDIT_TOOL,
    FILE_READ_TOOL,
    FILE_WRITE_TOOL,
    MAX_TOOL_METADATA_PREVIEW_CHARS,
    MAX_TOOL_OUTPUT_BASELINE,
    MAX_TOOL_OUTPUT_TIERS,
    TERMINAL_TOOL,
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
        return MAX_TOOL_OUTPUT_BASELINE
    for tier_window, tier_limit in MAX_TOOL_OUTPUT_TIERS:
        if context_window >= tier_window:
            return tier_limit
    return MAX_TOOL_OUTPUT_BASELINE


def format_tool_result(
    tool_name: str, result: ToolResult, max_output: int = MAX_TOOL_OUTPUT_BASELINE
) -> str:
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
        if len(meta_str) < MAX_TOOL_METADATA_PREVIEW_CHARS:
            lines.append(f"Metadata: {meta_str}")
    return "\n".join(lines)


def build_tool_metadata(
    tool_name: str, tool_params: dict, result: ToolResult, duration_ms: int
) -> dict:
    if tool_name in (BASH_TOOL, TERMINAL_TOOL):
        cmd = str(tool_params.get("command") or "")
        out_lines = result.output.split("\n") if result.output else []
        exit_code = result.metadata.get("exit_code", 0) if result.metadata else 0
        return {
            "command": cmd,
            "output_lines": out_lines,
            "duration_ms": duration_ms,
            "exit_code": exit_code,
        }
    elif tool_name == FILE_WRITE_TOOL:
        return {
            "path": tool_params.get("filepath") or tool_params.get("path") or "",
            "content": tool_params.get("content", ""),
            "match": "exact",
        }
    elif tool_name == FILE_EDIT_TOOL:
        return {
            "path": tool_params.get("filepath") or tool_params.get("path") or "",
            "old_content": tool_params.get("old_content", ""),
            "new_content": tool_params.get("new_content", ""),
            "match": "exact",
        }
    elif tool_name in (FILE_DELETE_TOOL, FILE_READ_TOOL):
        return {"path": tool_params.get("filepath") or tool_params.get("path") or ""}
    return {}


def _resolve_workdir(workspace_root: str, target: str) -> Path | None:
    """Resolve ``target`` against the workspace, or ``None`` if it escapes it."""
    workspace = Path(workspace_root).resolve()
    try:
        resolved = (workspace / target).resolve()
    except (OSError, ValueError):
        return None
    try:
        resolved.relative_to(workspace)
        return resolved
    except ValueError:
        return None


def apply_bash_prechecks(tool_params: dict, workspace_root: str) -> str | None:
    from server.agents.validation import (
        check_python_syntax,
        detect_interactive_command,
        parse_cd_prefix,
    )

    command = tool_params.get("command", "")
    target, remainder = parse_cd_prefix(command)
    if target is not None and remainder != command:
        resolved = _resolve_workdir(workspace_root, target)
        if resolved is None:
            return (
                f"Command changes directory to '{target}' but that path is outside the "
                "workspace; refusing. Run the command from the workspace root instead."
            )
        if not resolved.is_dir():
            return (
                f"Command changes directory to '{target}' but it is not an existing "
                "directory. Create it first (e.g. `New-Item -ItemType Directory "
                f"'{target}'`), then run your command."
            )
        tool_params["command"] = remainder
        tool_params[BASH_WORKDIR_PARAM] = str(resolved)
        logger.info("Resolved cd prefix: workdir=%s command=%s", resolved, remainder)
    err = check_python_syntax(tool_params.get("command", ""), workspace_root)
    if err:
        return err
    return detect_interactive_command(tool_params.get("command", ""))


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
    from server.agents.validation import detect_placeholders

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
    return (result, duration_ms)


async def post_execution_hooks(
    tool_name: str, tool_params: dict, result: ToolResult, workspace_root: str, session_id: str
) -> list[Event]:
    events: list[Event] = []
    edited_path = tool_params.get("filepath") or tool_params.get("path") or ""
    if tool_name in ("file_edit", "file_write") and result.success and edited_path:
        try:
            from server.toolkit.auto_lint import format_lint_result, run_lint

            lint_result = await run_lint(
                edited_path, workspace_root, fix=AUTO_LINT_FIX_ENABLED
            )
            if lint_result and (not lint_result.success):
                lint_msg = format_lint_result(lint_result)
                if lint_msg:
                    events.append(
                        r.warning(f"Lint issues detected:\n{lint_msg}", session_id, code="LINT")
                    )
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
