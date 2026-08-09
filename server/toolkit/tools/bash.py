from __future__ import annotations

import asyncio
import logging
import platform
import shutil
from typing import Any

from server.config.constants import (
    BASH_TOOL_COMMAND_PARAM_UNIX,
    BASH_TOOL_COMMAND_PARAM_WINDOWS,
    BASH_TOOL_DESCRIPTION_UNIX,
    BASH_TOOL_DESCRIPTION_WINDOWS,
    BUILD_MODE,
    CONCURRENCY_GROUP_SHELL,
    COST_CLASS_HIGH,
    DEFAULT_BASH_TIMEOUT_MS,
    LATENCY_CLASS_HIGH,
    PERMISSION_COMMAND,
    RISK_MEDIUM,
    TOOL_DOMAIN_EXECUTION,
)

from ..base import BaseTool, ToolResult
from .background import get_background_manager

logger = logging.getLogger(__name__)
_OS_NAME = platform.system()
_IS_WINDOWS = _OS_NAME == "Windows"


def _resolve_shell() -> str | None:
    if _IS_WINDOWS:
        return shutil.which("pwsh") or shutil.which("powershell")
    return shutil.which("bash")


def _is_windows() -> bool:
    return platform.system() == "Windows"


class BashTool(BaseTool):
    name = "bash"

    @property
    def description(self) -> str:
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
        timeout = params.get("timeout", self.timeout)
        run_in_background = params.get("run_in_background", False)
        auto_background_after = params.get("auto_background_after", self.auto_background_after)
        if not command.strip():
            return ToolResult(success=False, error="No command provided")
        if run_in_background:
            return await self._start_background(
                command, workspace_root, params.get("description", "")
            )
        return await self._execute_sync(command, workspace_root, timeout, auto_background_after)

    async def _start_background(
        self, command: str, workspace_root: str, description: str
    ) -> ToolResult:
        manager = get_background_manager()
        job = await manager.start(command, workspace_root, description)
        try:
            await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            pass
        output = manager.get_output(job.id)
        if output is None:
            return ToolResult(success=False, error="Failed to start background job")
        if job.done:
            manager.remove(job.id)
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
        self, command: str, workspace_root: str, timeout: int, auto_background_after: int
    ) -> ToolResult:
        process = None
        try:
            shell = _resolve_shell()
            if _IS_WINDOWS and shell:
                process = await asyncio.create_subprocess_shell(
                    f'"{shell}" -NoProfile -Command {command}',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=workspace_root,
                )
            else:
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=workspace_root,
                    shell=True,
                )
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
                    job = manager.register(command, workspace_root, "", process)
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
                return ToolResult(success=True, output=output, metadata={"exit_code": exit_code})
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
