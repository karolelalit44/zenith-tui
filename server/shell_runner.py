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
import time as _time
from collections.abc import AsyncIterator
from dataclasses import dataclass

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


# ---------------------------------------------------------------------------
# Phase 1 additive — live output streaming + wait-for-completion (module 05).
# Mirrors opencode bash.ts (streams decoded chunks into part.state.metadata.output
# as they arrive) and codex ExecCommandOutputDelta (ExecExpiration: run until
# done / timeout / cancelled). Purely additive: the buffering background+poll
# model in bash.py stays until Phase 2 wires consumers onto this generator.
# ---------------------------------------------------------------------------


@dataclass
class ShellStreamEvent:
    """One live command-output event.

    ``kind`` is ``"stdout"`` or ``"stderr"`` for an emitted chunk, or ``"exit"``
    as the terminal event carrying the process exit code.
    """

    kind: str
    data: str
    exit_code: int | None = None


async def run_shell_command_streamed(
    command: str,
    *,
    cwd: str | None = None,
    timeout: float | None = None,
) -> AsyncIterator[ShellStreamEvent]:
    """Run ``command`` and yield output chunks live as they arrive.

    Streams stdout/stderr decoded chunks in arrival order (opencode live output),
    then a final ``exit`` event with the process exit code. Stops on: the command
    completing, ``timeout`` seconds elapsing (the process is killed and
    ``asyncio.TimeoutError`` raised), or the consumer cancelling the generator
    (the process is killed and the cancellation propagated). No background job or
    separate poll is involved — the caller awaits the stream to completion.
    """
    process = await run_shell_command(command, cwd=cwd)
    out_q: asyncio.Queue[tuple[str, str, str | None]] = asyncio.Queue()

    async def _pump(reader: asyncio.StreamReader, kind: str) -> None:
        try:
            while True:
                chunk = await reader.read(4096)
                if not chunk:
                    break
                await out_q.put(("data", kind, chunk.decode("utf-8", errors="replace")))
        except asyncio.CancelledError:
            pass
        finally:
            await out_q.put(("eof", kind, None))

    reader_tasks = [
        asyncio.create_task(_pump(reader, kind))
        for kind, reader in (("stdout", process.stdout), ("stderr", process.stderr))
        if reader is not None
    ]
    wait_task = asyncio.create_task(process.wait())
    eofs: set[str] = set()
    try:
        deadline = _time.monotonic() + timeout if timeout else None
        while True:
            if deadline is not None:
                remaining = deadline - _time.monotonic()
                if remaining <= 0:
                    process.kill()
                    raise asyncio.TimeoutError(f"command timed out after {timeout}s")
                pending = asyncio.ensure_future(out_q.get())
                done, _ = await asyncio.wait({pending}, timeout=remaining)
                if pending not in done:
                    pending.cancel()
                    process.kill()
                    raise asyncio.TimeoutError(f"command timed out after {timeout}s")
                ev = pending.result()
            else:
                ev = await out_q.get()
            if ev[0] == "data":
                yield ShellStreamEvent(ev[1], ev[2])
            else:
                eofs.add(ev[1])
            if len(eofs) == len(reader_tasks):
                break
    finally:
        for t in reader_tasks:
            t.cancel()
        await asyncio.gather(*reader_tasks, return_exceptions=True)
    await wait_task
    yield ShellStreamEvent("exit", "", process.returncode)
