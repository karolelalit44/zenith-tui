"""Platform-shell subprocess runner for all agent-driven commands.

On Windows every command MUST execute through PowerShell (pwsh or
powershell) via ``create_subprocess_exec`` so the full command string
reaches PowerShell as one argument. Routing through
``create_subprocess_shell`` makes cmd.exe parse the string first, which
misinterprets PowerShell syntax (``|``, ``$_``, ``Where-Object`` ...)
and fails with "'X' is not recognized as an internal or external
command".
"""

from __future__ import annotations

import asyncio
import logging
import platform
import shutil

logger = logging.getLogger(__name__)

_IS_WINDOWS = platform.system() == "Windows"


def resolve_shell() -> str | None:
    if _IS_WINDOWS:
        return shutil.which("pwsh") or shutil.which("powershell")
    return shutil.which("bash")


async def run_shell_command(
    command: str,
    *,
    cwd: str | None = None,
    stdin=asyncio.subprocess.PIPE,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
) -> asyncio.subprocess.Process:
    """Spawn ``command`` under the correct platform shell."""
    if _IS_WINDOWS:
        shell = resolve_shell()
        if not shell:
            raise RuntimeError(
                "PowerShell (powershell/pwsh) was not found on PATH; "
                "cannot execute Windows commands safely."
            )
        return await asyncio.create_subprocess_exec(
            shell,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            command,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            cwd=cwd,
        )
    return await asyncio.create_subprocess_shell(
        command,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        cwd=cwd,
    )
