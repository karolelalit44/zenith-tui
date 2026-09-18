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
from server.shell_runner import run_shell_command_streamed

from ..base import BaseTool, ToolResult
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

_DIRECT_FILE_READ_POSIX = re.compile(
    r"^\s*cat\s+['\"]?([^\s|><;]+)['\"]?\s*$",
    re.IGNORECASE,
)
_DIRECT_FILE_READ_WINDOWS = re.compile(
    r"^\s*(?:cat|type|Get-Content|gc)\s+['\"]?([^\s|><;]+)['\"]?(?:\s+-(?:TotalCount|First|Head)\s+\d+)?\s*$",
    re.IGNORECASE,
)


def _assess_direct_file_read(command: str) -> str | None:
    stripped = command.strip()
    pattern = _DIRECT_FILE_READ_WINDOWS if _is_windows() else _DIRECT_FILE_READ_POSIX
    m = pattern.match(stripped)
    if m:
        path = m.group(1)
        return (
            f"Refused: Do not use shell commands to read files ('{path}'). "
            f"Use the dedicated 'file_read' tool with path='{path}'."
        )
    return None


# ---- Dedicated-tool bypass guard (WP: tool calling over bash) ---------------
#
# Every file-system operation has a dedicated tool. Shell equivalents bypass
# ignore rules, structured metadata, caching, and safety checks. They are
# refused with an actionable redirect to the canonical tool.

# list_dir / glob bypass via shell directory listing
_LIST_DIR_BYPASS = re.compile(
    r"^\s*(?:ls|dir|ll|gci|Get-ChildItem|Get-Item)\b",
    re.IGNORECASE,
)
# file viewing bypass (head/tail/bat/less/more beyond cat/type)
_FILE_VIEW_BYPASS = re.compile(
    r"^\s*(?:head|tail|less|more|bat|Get-Content|gc)\b",
    re.IGNORECASE,
)
# code search bypass via shell grep
_GREP_BYPASS = re.compile(
    r"^\s*(?:grep|egrep|fgrep|rg|ag|ack|Select-String|findstr)\b",
    re.IGNORECASE,
)
# glob/find bypass via shell file discovery
_GLOB_BYPASS = re.compile(
    r"^\s*find\b.*-name\b",
    re.IGNORECASE,
)
# file creation via shell redirection / New-Item / touch / echo >
_SHELL_WRITE_BYPASS = re.compile(
    r"^\s*(?:New-Item|touch|Set-Content|Add-Content|Out-File)\b",
    re.IGNORECASE,
)
_ECHO_REDIRECT_BYPASS = re.compile(
    r"^\s*(?:echo|Write-Output|printf)\b[^|;]*[>]{1,2}\s*\S+",
    re.IGNORECASE,
)
_SED_AWK_INPLACE_BYPASS = re.compile(
    r"^\s*(?:sed|awk)\b[^|;]*\s-i\b",
    re.IGNORECASE,
)


def _assess_dedicated_tool_bypass(command: str) -> str | None:
    stripped = command.strip()
    if not stripped:
        return None
    # Check every pipeline/chain segment so `echo hi; ls` or `a | grep x` cannot bypass.
    segments = [s.strip() for s in re.split(r"[|;&]+", stripped) if s.strip()]
    for seg in segments:
        if _LIST_DIR_BYPASS.match(seg):
            return (
                "Refused: Do not use shell 'ls/dir/Get-ChildItem/Get-Item' for listing. "
                "Use dedicated 'list_dir' for a single directory or 'glob' for pattern search. "
                "Example: list_dir(path='server') or glob(pattern='**/*.py', path='server')."
            )
        if _FILE_VIEW_BYPASS.match(seg):
            tok = seg.split()[-1].strip("'\"") if len(seg.split()) > 1 else "path/to/file"
            return (
                f"Refused: Do not use shell file viewers for reading. "
                f"Use dedicated 'file_read' tool. Example: file_read(path='{tok}')."
            )
        if _GREP_BYPASS.match(seg):
            return (
                "Refused: Do not use shell 'grep/rg/ag/Select-String' for code search. "
                "Use dedicated 'grep' tool. Example: grep(pattern='def foo', path='server', include='*.py')."
            )
        if _GLOB_BYPASS.match(seg):
            return (
                "Refused: Do not use shell 'find -name' for file discovery. "
                "Use dedicated 'glob' tool. Example: glob(pattern='**/*.py', path='server')."
            )
        if _SHELL_WRITE_BYPASS.match(seg):
            return (
                "Refused: Do not use shell 'New-Item/touch/Set-Content/Out-File' for file creation. "
                "Use dedicated 'file_write' (new file) or 'file_edit' (existing file)."
            )
        if _ECHO_REDIRECT_BYPASS.match(seg):
            return (
                "Refused: Do not use shell redirection 'echo > file' for file creation. "
                "Use dedicated 'file_write' tool. Example: file_write(path='path/to/file', content='...')."
            )
        if _SED_AWK_INPLACE_BYPASS.match(seg):
            return (
                "Refused: Do not use shell 'sed -i / awk -i' for file editing. "
                "Use dedicated 'file_edit' tool with old_content/new_content."
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

    def __init__(self, timeout: int = 30) -> None:
        self.timeout = timeout

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
            },
            "required": ["command"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        command = params.get("command", "")
        workdir = params.get(BASH_WORKDIR_PARAM) or workspace_root
        timeout = params.get("timeout", self.timeout)
        run_in_background = params.get("run_in_background", False)
        if not command.strip():
            return ToolResult(success=False, error="No command provided")
        dedicated = _assess_dedicated_tool_bypass(command)
        if dedicated:
            return ToolResult(success=False, error=dedicated)
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
        read_refusal = _assess_direct_file_read(command)
        if read_refusal:
            return ToolResult(success=False, error=read_refusal)
        if run_in_background:
            return await self._start_background(command, workdir, params.get("description", ""))
        return await self._execute_streamed(command, workdir, timeout)

    async def _execute_streamed(self, command: str, workdir: str, timeout: int) -> ToolResult:
        chunks: list[str] = []
        stderr_chunks: list[str] = []
        exit_code: int | None = None
        try:
            async for event in run_shell_command_streamed(command, cwd=workdir, timeout=timeout):
                if event.kind in ("stdout", "stderr"):
                    chunks.append(event.data)
                    if event.kind == "stderr":
                        stderr_chunks.append(event.data)
                elif event.kind == "exit":
                    exit_code = event.exit_code
        except TimeoutError:
            return ToolResult(success=False, error=f"Command timed out after {timeout}s")
        except RuntimeError as exc:
            return ToolResult(success=False, error=str(exc))

        output = "".join(chunks)
        return ToolResult(
            success=exit_code == 0,
            output=output,
            error="" if exit_code == 0 else output,
            metadata={"exit_code": exit_code, "stderr_len": len("".join(stderr_chunks))},
        )

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
