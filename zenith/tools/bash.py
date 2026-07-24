"""Bash tool — execute shell commands with timeout."""

from __future__ import annotations

import asyncio
import platform
from typing import Any

from .base import BaseTool, ToolResult


class BashTool(BaseTool):
    name = "bash"
    description = "Execute a shell command"
    permission_level = "HIGH"

    def __init__(self, timeout: int = 30) -> None:
        self.timeout = timeout

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
            },
            "required": ["command"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        command = params.get("command", "")
        timeout = params.get("timeout", self.timeout)

        if not command.strip():
            return ToolResult(success=False, error="No command provided")

        shell = "cmd" if platform.system() == "Windows" else "bash"

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workspace_root,
                shell=True,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.communicate()
                return ToolResult(
                    success=False,
                    error=f"Command timed out after {timeout}s",
                )

            output = stdout.decode("utf-8", errors="replace")
            error = stderr.decode("utf-8", errors="replace")
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

        except Exception as e:
            return ToolResult(success=False, error=str(e))
