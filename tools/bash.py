"""Bash tool — execute shell commands with timeout, background job support, and streaming output."""

from __future__ import annotations

import asyncio
import logging
import platform
import shutil
from typing import Any

from .base import BaseTool, ToolResult
from .background import get_background_manager

logger = logging.getLogger(__name__)

_OS_NAME = platform.system()
_IS_WINDOWS = _OS_NAME == "Windows"


def _resolve_shell() -> str | None:
    """Detect the best available shell for the current platform."""
    if _IS_WINDOWS:
        return shutil.which("pwsh") or shutil.which("powershell")
    return shutil.which("bash")


class BashTool(BaseTool):
    name = "bash"
    description = "Execute a shell command. Supports background execution for long-running commands."

    @property
    def risk_level(self) -> str:
        return "medium"

    def __init__(self, timeout: int = 30, auto_background_after: int = 60) -> None:
        self.timeout = timeout
        self.auto_background_after = auto_background_after

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 30)",
                    "default": 30,
                },
                "run_in_background": {
                    "type": "boolean",
                    "description": "Set to true to run the command in the background. Use job_output to read the output later.",
                    "default": False,
                },
                "auto_background_after": {
                    "type": "integer",
                    "description": "Seconds to wait before automatically moving the command to a background job (default: 60)",
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

        # Explicit background request
        if run_in_background:
            return await self._start_background(command, workspace_root, params.get("description", ""))

        # Synchronous execution with auto-background support
        return await self._execute_sync(command, workspace_root, timeout, auto_background_after)

    async def _start_background(
        self, command: str, workspace_root: str, description: str,
    ) -> ToolResult:
        """Start a command in the background immediately."""
        manager = get_background_manager()
        job = manager.start(command, workspace_root, description)

        # Wait briefly to detect fast failures
        try:
            await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            pass

        output = manager.get_output(job.id)
        if output is None:
            return ToolResult(success=False, error="Failed to start background job")

        if job.done:
            # Completed quickly — return result directly
            manager.remove(job.id)
            return ToolResult(
                success=job.exit_code == 0,
                output=output,
                error="" if job.exit_code == 0 else output,
                metadata={"exit_code": job.exit_code, "background": False, "job_id": job.id},
            )

        # Still running — return job ID
        return ToolResult(
            success=True,
            output=(
                f"Background job started with ID: {job.id}\n"
                f"Command: {command}\n\n"
                f"Use job_output tool to view output or job_kill to terminate."
            ),
            metadata={"background": True, "job_id": job.id},
        )

    async def _execute_sync(
        self, command: str, workspace_root: str, timeout: int, auto_background_after: int,
    ) -> ToolResult:
        """Execute a command synchronously with streaming output and auto-background support."""
        process = None
        try:
            shell = _resolve_shell()

            if _IS_WINDOWS and shell:
                # PowerShell: wrap command in -Command to handle pipes and redirects
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

            # Stream output incrementally for better responsiveness
            stdout_chunks: list[bytes] = []
            stderr_chunks: list[bytes] = []

            async def _read_stream(reader: asyncio.StreamReader, chunks: list[bytes]) -> None:
                while True:
                    chunk = await reader.read(4096)
                    if not chunk:
                        break
                    chunks.append(chunk)

            stdout_task = asyncio.create_task(_read_stream(process.stdout, stdout_chunks)) if process.stdout else None
            stderr_task = asyncio.create_task(_read_stream(process.stderr, stderr_chunks)) if process.stderr else None

            try:
                # Wait for completion or auto-background threshold
                auto_bg_timeout = min(auto_background_after, timeout)
                await asyncio.wait_for(
                    process.wait(),
                    timeout=auto_bg_timeout,
                )
            except asyncio.TimeoutError:
                if process.returncode is None:
                    # Command still running — move to background
                    manager = get_background_manager()
                    job = manager.start(command, workspace_root)
                    manager._jobs[job.id].process = process
                    manager._jobs[job.id].done = False

                    # Cancel streaming tasks (process will continue in background)
                    for t in (stdout_task, stderr_task):
                        if t and not t.done():
                            t.cancel()

                    return ToolResult(
                        success=True,
                        output=(
                            f"Command is taking longer than expected and has been moved to background.\n"
                            f"Background job ID: {job.id}\n"
                            f"Command: {command}\n\n"
                            f"Use job_output tool to view output or job_kill to terminate."
                        ),
                        metadata={"background": True, "job_id": job.id},
                    )
                else:
                    return ToolResult(
                        success=False,
                        error=f"Command timed out after {timeout}s",
                    )
            except asyncio.CancelledError:
                if process.returncode is None:
                    process.kill()
                    try:
                        await process.wait()
                    except Exception:
                        pass
                raise

            # Wait for streaming tasks to finish
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
                return ToolResult(
                    success=True,
                    output=output,
                    metadata={"exit_code": exit_code},
                )
            else:
                return ToolResult(
                    success=False,
                    output=output,
                    error=error,
                    metadata={"exit_code": exit_code},
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
