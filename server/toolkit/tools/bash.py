from __future__ import annotations

import asyncio
import logging
import platform
import re
from typing import Any

from server.config.constants import (
    BASH_TOOL_COMMAND_PARAM_UNIX,
    BASH_TOOL_COMMAND_PARAM_WINDOWS,
    BASH_TOOL_DESCRIPTION_UNIX,
    BASH_TOOL_DESCRIPTION_WINDOWS,
    BASH_WORKDIR_PARAM,
    BUILD_MODE,
    CONCURRENCY_GROUP_SHELL,
    COST_CLASS_HIGH,
    DEFAULT_BASH_TIMEOUT_MS,
    LATENCY_CLASS_HIGH,
    PERMISSION_COMMAND,
    RISK_MEDIUM,
    TOOL_DOMAIN_EXECUTION,
)
from server.shell_runner import run_shell_command

from ..base import BaseTool, ToolResult
from ..command_result import detect_false_success
from .background import get_background_manager

logger = logging.getLogger(__name__)


def _is_windows() -> bool:
    return platform.system() == "Windows"


# ---- Whole-tree enumeration guard (WP1c) -----------------------------------
#
# Unbounded recursive listings (`Get-ChildItem -Recurse`, `tree`, `ls -R`,
# `find .` at the root) can walk millions of files and flood the context with
# megabytes of output. They are refused BEFORE execution with scoped,
# bounded alternatives. Explicitly bounded commands (piped to -First/head or
# capped by -maxdepth) pass through.

_PS_LISTING = re.compile(r"(?:^|[;|&]|\b)(?:Get-ChildItem|gci|dir|ls)\b", re.IGNORECASE)
_PS_RECURSE = re.compile(r"-(?:Recurs|r)e?(?![a-z])", re.IGNORECASE)
_PS_LIMIT = re.compile(
    r"-First\s+\d+|-TotalCount\s+\d+|-Head\s+\d+|Select-Object\s+-First\s+\d+", re.IGNORECASE
)
_TREE_CMD = re.compile(r"(?:^|[;|&])\s*tree\b")

_UNIX_RECURSIVE_LS = re.compile(r"(?:^|[;|&])\s*(?:ls|ll)\s+(?=[^;|&]*-[^;|&]*R\b)[^;|&]*")
_UNIX_HEAD_PIPE = re.compile(r"\|\s*head\b|\|\s*Select-Object\s+-First\s+\d+", re.IGNORECASE)
_FIND_AT_ROOT = re.compile(
    r"(?:^|[;|&])\s*find\s+(?:\.|\"\.\"|'.'|\./)?\s*(?:$|[;|&]|-)", re.IGNORECASE
)
_FIND_MAXDEPTH = re.compile(r"-maxdepth\s+\d+", re.IGNORECASE)

_RECURSE_REFUSAL = (
    "Refused: unbounded recursive listing would enumerate the ENTIRE workspace. "
    "Scope it instead, e.g.: 'Get-ChildItem <subdir> -Recurse -File | Select-Object "
    "-First 50 FullName' or 'find <subdir> -maxdepth 2' - or use the glob/list_dir "
    "tools, which respect ignore rules."
)


def _assess_enumeration(command: str, workspace_root: str) -> str | None:
    """Return a refusal message when the command would enumerate whole trees."""
    stripped = command.strip()
    if not stripped:
        return None

    limited = bool(_PS_LIMIT.search(stripped)) or bool(_UNIX_HEAD_PIPE.search(stripped))

    # `tree` walks the entire subtree and cannot be pruned.
    if _TREE_CMD.search(stripped) and not _UNIX_HEAD_PIPE.search(stripped):
        return (
            "Refused: 'tree' enumerates the ENTIRE workspace subtree. "
            "This workspace is far too large to list wholesale. Use 'list_dir' "
            "for a single directory, or a scoped listing like: "
            "Get-ChildItem <subdir> | Select-Object Name"
        )

    if (
        (_PS_LISTING.search(stripped) or _UNIX_RECURSIVE_LS.search(stripped))
        and (_PS_RECURSE.search(stripped) or _UNIX_RECURSIVE_LS.search(stripped))
        and not limited
    ):
        return _RECURSE_REFUSAL

    if _FIND_AT_ROOT.search(stripped) and not _FIND_MAXDEPTH.search(stripped) and not limited:
        return (
            "Refused: unscoped 'find .' walks the ENTIRE workspace. Add -maxdepth, "
            "scope to a subdirectory, or pipe through 'head'."
        )

    return None


class BashTool(BaseTool):
    name = "bash"

    @property
    def description(self) -> str:  # type: ignore[override]
        return BASH_TOOL_DESCRIPTION_WINDOWS if _is_windows() else BASH_TOOL_DESCRIPTION_UNIX

    capability_id = "command_execution"
    requires_mode = BUILD_MODE
    read_only = False
    timeout_ms = DEFAULT_BASH_TIMEOUT_MS
    concurrency_group = CONCURRENCY_GROUP_SHELL
    permission_scope = PERMISSION_COMMAND
    domains = (TOOL_DOMAIN_EXECUTION,)
    search_terms = (
        "shell",
        "bash",
        "command",
        "run",
        "execute",
        "terminal",
    )
    risk_level = RISK_MEDIUM
    cost_class = COST_CLASS_HIGH
    latency_class = LATENCY_CLASS_HIGH

    def __init__(self, timeout: int = 30, auto_background_after: int = 60) -> None:
        self.timeout = timeout
        self.auto_background_after = auto_background_after

    def get_schema(self) -> dict:
        command_desc = (
            BASH_TOOL_COMMAND_PARAM_WINDOWS if _is_windows() else BASH_TOOL_COMMAND_PARAM_UNIX
        )
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": command_desc},
                "timeout": {"type": "integer", "description": "Timeout seconds", "default": 30},
                "run_in_background": {
                    "type": "boolean",
                    "description": "Run in background",
                    "default": False,
                },
                "auto_background_after": {
                    "type": "integer",
                    "description": "Background delay seconds",
                    "default": 60,
                },
            },
            "required": ["command"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        command = params.get("command", "")
        workdir = params.get(BASH_WORKDIR_PARAM) or workspace_root
        timeout = params.get("timeout", self.timeout)
        run_in_background = params.get("run_in_background", False)
        auto_background_after = params.get("auto_background_after", self.auto_background_after)
        if not command.strip():
            return ToolResult(success=False, error="No command provided")
        refusal = _assess_enumeration(command, workspace_root)
        if refusal:
            from server.workspace.index import get_workspace_stats

            try:
                stats = get_workspace_stats(workspace_root)
                detail = (
                    f" Workspace has ~{stats.total_files} files ({stats.describe_top_level()})."
                )
            except Exception:
                detail = ""
            return ToolResult(success=False, error=f"{refusal}{detail}")
        if run_in_background:
            return await self._start_background(command, workdir, params.get("description", ""))
        return await self._execute_sync(command, workdir, timeout, auto_background_after)

    async def _start_background(self, command: str, workdir: str, description: str) -> ToolResult:
        manager = get_background_manager()
        job = await manager.start(command, workdir, description)
        try:
            await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            pass
        output = manager.get_output(job.id)
        if output is None:
            return ToolResult(success=False, error="Failed to start background job")
        if job.done:
            manager.remove(job.id)
            false_sig = detect_false_success(job.stdout, job.stderr)
            if job.exit_code == 0 and false_sig:
                return ToolResult(
                    success=False,
                    output=job.stdout,
                    error=(
                        f"Background job reported success (exit 0) but its output indicates "
                        f"failure: '{false_sig}'. The command was likely not actually executed."
                    ),
                    metadata={"exit_code": job.exit_code, "background": False, "job_id": job.id},
                )
            return ToolResult(
                success=job.exit_code == 0,
                output=output,
                error="" if job.exit_code == 0 else output,
                metadata={"exit_code": job.exit_code, "background": False, "job_id": job.id},
            )
        return ToolResult(
            success=True,
            output=f"Background job started with ID: {job.id}\nCommand: {command}\n\nUse job_output tool to view output or job_kill to terminate.",
            metadata={"background": True, "job_id": job.id},
        )

    async def _execute_sync(
        self, command: str, workdir: str, timeout: int, auto_background_after: int
    ) -> ToolResult:
        process = None
        try:
            # exec (not shell): the FULL command string must reach
            # PowerShell as a single argument. Routing through
            # create_subprocess_shell made cmd.exe parse the string first,
            # so any `|`/`&` in the command was treated as a CMD pipe and
            # PowerShell segments after it failed with "'X' is not
            # recognized as an internal or external command" (F2).
            try:
                process = await run_shell_command(command, cwd=workdir)
            except RuntimeError as e:
                return ToolResult(success=False, error=str(e))
            stdout_chunks: list[bytes] = []
            stderr_chunks: list[bytes] = []

            async def _read_stream(reader: asyncio.StreamReader, chunks: list[bytes]) -> None:
                while True:
                    chunk = await reader.read(4096)
                    if not chunk:
                        break
                    chunks.append(chunk)

            stdout_task = (
                asyncio.create_task(_read_stream(process.stdout, stdout_chunks))
                if process.stdout
                else None
            )
            stderr_task = (
                asyncio.create_task(_read_stream(process.stderr, stderr_chunks))
                if process.stderr
                else None
            )
            try:
                auto_bg_timeout = min(auto_background_after, timeout)
                await asyncio.wait_for(process.wait(), timeout=auto_bg_timeout)
            except TimeoutError:
                if process.returncode is None:
                    for t in (stdout_task, stderr_task):
                        if t and (not t.done()):
                            t.cancel()
                    await asyncio.gather(
                        *(t for t in (stdout_task, stderr_task) if t is not None),
                        return_exceptions=True,
                    )
                    manager = get_background_manager()
                    job = manager.register(command, workdir, "", process)
                    return ToolResult(
                        success=True,
                        output=f"Command is taking longer than expected and has been moved to background.\nBackground job ID: {job.id}\nCommand: {command}\n\nUse job_output tool to view output or job_kill to terminate.",
                        metadata={"background": True, "job_id": job.id},
                    )
                else:
                    return ToolResult(success=False, error=f"Command timed out after {timeout}s")
            except asyncio.CancelledError:
                if process.returncode is None:
                    process.kill()
                    try:
                        await process.wait()
                    except Exception:
                        pass
                raise
            for t in (stdout_task, stderr_task):
                if t:
                    try:
                        await t
                    except asyncio.CancelledError:
                        pass
            output = b"".join(stdout_chunks).decode("utf-8", errors="replace")
            error = b"".join(stderr_chunks).decode("utf-8", errors="replace")
            exit_code = process.returncode
            if exit_code == 0:
                false_sig = detect_false_success(output, error)
                if false_sig:
                    return ToolResult(
                        success=False,
                        output=output,
                        error=(
                            f"Command reported success (exit 0) but its output indicates "
                            f"failure: '{false_sig}'. This usually means the command was not "
                            "actually executed (e.g. the Windows Store 'python' alias). Run it "
                            "again with an explicit interpreter or fix the environment."
                        ),
                        metadata={"exit_code": exit_code, "false_success": false_sig},
                    )
                # Surface stderr on success too: tools like `python -m unittest`
                # write their entire report to stderr, so dropping it on exit 0
                # leaves the model with a SUCCESS and zero evidence bytes.
                combined = output
                if error:
                    combined = output + ("\n" if output else "") + error
                return ToolResult(
                    success=True,
                    output=combined,
                    metadata={"exit_code": exit_code, "stderr_len": len(error)},
                )
            else:
                return ToolResult(
                    success=False, output=output, error=error, metadata={"exit_code": exit_code}
                )
        except asyncio.CancelledError:
            if process and process.returncode is None:
                process.kill()
                try:
                    await process.wait()
                except Exception:
                    pass
            raise
        except Exception as e:
            if process and process.returncode is None:
                process.kill()
                try:
                    await process.wait()
                except Exception:
                    pass
            return ToolResult(success=False, error=str(e))
