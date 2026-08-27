"""F2 regression: bash tool must execute Windows commands via PowerShell with
the full command string as a single argument — never pre-parsed by cmd.exe.

The original bug (AGENT_RELIABILITY_PLAN §10 F2): the command was launched via
``create_subprocess_shell("<powershell> -NoProfile -Command <cmd>")``, so
cmd.exe parsed the string first and treated any ``|`` as a CMD pipe. The
PowerShell segment after the pipe was then executed by cmd itself, producing
"'Where-Object' is not recognized as an internal or external command".

Probe 1 proves the mechanism empirically (shell vs exec for the same string).
The BashTool tests then pin the fixed behavior end-to-end.
"""

import asyncio

import pytest

from server.shell_runner import resolve_shell as _resolve_shell
from server.toolkit.tools.bash import BashTool


def _run(coro):
    return asyncio.run(coro)


def test_mechanism_shell_vs_exec_for_piped_command():
    """Empirical proof: cmd.exe splits pipes in shell-mode; exec does not."""
    command = "Write-Output 'alpha' | ForEach-Object { $_ }"
    shell = _resolve_shell()
    assert shell, "PowerShell must be resolvable on this machine"

    async def both():
        # OLD path: create_subprocess_shell → COMSPEC (cmd.exe) parses first.
        old = await asyncio.create_subprocess_shell(
            f'"{shell}" -NoProfile -Command {command}',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        o_out, o_err = await old.communicate()
        # NEW path: exec → the whole string is ONE argv element to PowerShell.
        new = await asyncio.create_subprocess_exec(
            shell,
            "-NoProfile",
            "-Command",
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        n_out, n_err = await new.communicate()
        return (o_out, o_err), (n_out, n_err)

    (_, old_err), (new_out, _) = _run(both())
    assert b"not recognized" in old_err or old_err == b"", "unexpected old-path behavior"
    assert b"alpha" in new_out, f"exec path failed: {new_out!r}"


@pytest.mark.asyncio
async def test_bash_tool_powershell_pipeline_survives(temp_dir):
    """End-to-end F2 regression through BashTool.execute."""
    tool = BashTool(timeout=30)
    result = await tool.execute(
        {"command": "Write-Output 'alpha' | ForEach-Object { $_ }"},
        str(temp_dir),
    )
    assert result.success, f"pipeline failed: {result.error!r}"
    assert "alpha" in result.output


@pytest.mark.asyncio
async def test_bash_tool_quotes_and_special_chars(temp_dir):
    """Quotes, $_ and braces must survive intact (single-argument contract)."""
    tool = BashTool(timeout=30)
    result = await tool.execute(
        {"command": "$v = @{ k = 'v' }; Write-Output $v.k"},
        str(temp_dir),
    )
    assert result.success, f"failed: {result.error!r}"
    assert "v" in result.output


@pytest.mark.asyncio
async def test_bash_tool_exit_code_propagates(temp_dir):
    tool = BashTool(timeout=30)
    result = await tool.execute({"command": "exit 3"}, str(temp_dir))
    assert result.success is False
    assert result.metadata.get("exit_code") == 3


@pytest.mark.asyncio
async def test_bash_tool_cwd_is_workspace(temp_dir):
    marker = temp_dir / "cwd_marker.txt"
    marker.write_text("here", encoding="utf-8")
    tool = BashTool(timeout=30)
    result = await tool.execute({"command": "Get-ChildItem -Name"}, str(temp_dir))
    assert result.success
    assert "cwd_marker.txt" in result.output
