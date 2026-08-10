from __future__ import annotations

import logging
import platform
from pathlib import Path
from typing import Any

from server.agents.provider_adapters import detect_model_tier, get_tier_prompt_enhancements
from server.config.constants import (
    BUILD_MODE,
    DEFAULT_CONTEXT_WINDOW,
    PLAN_MODE,
    TOOL_GUIDELINES_DIR,
    TOOL_GUIDELINES_FILE_NAME,
)
from server.workspace.context import format_context_files, load_context_files

logger = logging.getLogger(__name__)

SYSTEM_GUIDELINES = (
    "<guidelines>\n"
    "- Use dedicated tools: file_write/file_edit to create/modify files, file_read/glob/grep to inspect "
    "code, websearch/webfetch for web research. Use bash only when no dedicated tool fits (tests, builds, "
    "installs, git).\n"
    "- Workspace Scoping: scope globs to a subdirectory (e.g. glob pattern='src/**/*.py'); never glob "
    "'**/*' from the repo root or run a recursive shell listing - it matches node_modules/.git and blows "
    "context.\n"
    "- Inspect Before Writing: before creating files in a folder, scoped glob or file_read what is already "
    "there so you do not overwrite or duplicate work.\n"
    "- Write Discipline: file_write requires path and content. After it confirms a file was created, do not "
    "re-write it; to change an existing file, read it first (file_read) then edit it (file_edit).\n"
    "- Batching: you may emit several independent tool calls in a single response (e.g. multiple file_write "
    "calls to scaffold a project); only batch calls that do not depend on each other.\n"
    "- Verify Generated Projects: after generating a new project, install its dependencies and run its tests "
    "to confirm it actually works before finishing.\n"
    "- Environment Limits: if a verification step cannot run here (no network, missing runtime), report that "
    "explicitly instead of claiming it succeeded.\n"
    "- External Products: research them with websearch then webfetch specific pages; pass an 'extract' "
    "question for long pages. Do not substitute this codebase for the real product.\n"
    "- General Queries: Answer directly in markdown text without tool calls.\n"
    "</guidelines>\n"
)
BUILD_MODE_INSTRUCTIONS = "## MODE: BUILD\nObjective: Complete coding tasks autonomously. Understand the codebase, make minimal targeted changes, and verify your work.\n"
PLAN_MODE_INSTRUCTIONS = (
    "## MODE: PLAN\n"
    "Objective: Analyze the codebase using read-only tools and output a clear, structured "
    "Markdown implementation plan.\n"
    "In this mode only read-only tools are available (e.g. file_read, glob, grep, websearch, "
    "webfetch, and LSP query tools). Execution tools such as bash, file_write, and file_edit "
    "are disabled; do not attempt to call them - use read-only tools instead.\n"
)
TOOL_DISCOVERY_HINT = (
    "<tool_discovery>\n"
    "A lean set of tool schemas is always available. To use any other tool, load "
    "it once via get_tool_definition('<tool_name>'); loaded tools persist.\n"
    "</tool_discovery>\n"
)
TOOL_GUIDELINES_HINT = (
    "<tool_reference>\n"
    "Tool definitions and usage guidelines are available at '{path}'. Use file_read "
    "to load them only when you need details beyond a tool's schema (inputs, outputs, "
    "do's and don'ts).\n"
    "</tool_reference>\n"
)

TOOL_GUIDELINES_CONTENT = """# Tool Guidelines

Read this file with `file_read` only when you need details beyond a tool's schema:
what a tool expects, what it returns, and the rules for using it correctly. For
general queries and simple reads the schema you already have is enough.

## General rules

- Scope every glob to a subdirectory; never `**/*` from the repo root (it matches
  node_modules and .git and floods context).
- Inspect a folder before writing into it so you do not overwrite or duplicate work.
- After creating a file, do not write it again; to change it, file_read then file_edit.
- Batch independent tool calls into a single response; never batch dependent ones.
- After generating a project, install its dependencies and run its tests.
- If a verification step cannot run here (no network, missing runtime), say so
  explicitly; never claim it succeeded.
- Answer general queries directly in markdown; do not call tools for them.

## Tool reference

### file_read
- Purpose: read a file (or a slice) from the workspace.
- Input: `path` (required), `offset` (0-indexed start line), `limit` (max lines).
- Output: numbered lines `N: content`; metadata includes `total_lines`/`showing`.
- Guidelines: read small slices, not whole files; use offset/limit to page through
  large files. Path must stay inside the workspace.

### file_edit
- Purpose: change an existing file via exact search-and-replace.
- Input: `path`, `old_content` (exact text to replace), `new_content`.
- Output: confirmation of the applied edit.
- Guidelines: read the file first so `old_content` matches exactly.

### file_write
- Purpose: create a new file or overwrite an existing one.
- Input: `path`, `content` (full file body), `overwrite` (bool, default false).
- Output: `Created <path> (<bytes> bytes)`.
- Guidelines: missing parent directories are created automatically - do not run
  mkdir first. Do not include placeholders; write the full intended content once.

### bash
- Purpose: run a command in the workspace (tests, builds, installs, git).
- Input: `command`, `timeout`, `run_in_background`, `auto_background_after`.
- Output: stdout + exit code; long output is head/tail-trimmed with a marker.
- Guidelines: use PowerShell syntax on Windows, bash on Unix (see the env section).
  Use it only when no dedicated tool fits. Long commands are moved to a background
  job; poll with job_output / terminate with job_kill.

### glob
- Purpose: find files by glob pattern.
- Input: `pattern` (required, e.g. 'app/**/*.py'), `path`.
- Output: matched paths, capped at 500 results.
- Guidelines: always scope the pattern to a subdirectory; never `**/*` from the root.

### grep
- Purpose: search file contents by regex.
- Input: `pattern` (required), `path`, `include` (file filter).
- Output: `path:line: content` matches, or "No matches found".
- Guidelines: scope `path` so results stay small.

### discover_capabilities
- Purpose: list every capability and the tools that provide it.
- Input: none.
- Output: capability list with read-only/mutating flags and tool names.

### get_tool_definition
- Purpose: load the full schema + metadata for a tool not in the always-on set.
- Input: `tool_name` (required).
- Output: JSON with the tool's function schema and metadata.
- Guidelines: call once per tool; loaded tools persist for the session. Never load
  a tool you already have.
"""


def ensure_tool_guidelines_file(workspace_root: str) -> str:
    """Write the tool-guidelines reference file if missing; return its absolute path.

    Best-effort: failures to write are logged and never raised so prompt building
    and tests are unaffected when the target directory is read-only.
    """
    root = Path(workspace_root).resolve()
    path = root / TOOL_GUIDELINES_DIR / TOOL_GUIDELINES_FILE_NAME
    try:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(TOOL_GUIDELINES_CONTENT, encoding="utf-8")
    except OSError as e:
        logger.warning("Could not write tool guidelines file %s: %s", path, e)
    return str(path)


def build_system_prompt(
    workspace_root: str,
    mode: str = BUILD_MODE,
    tool_schemas: list[dict[str, Any]] | None = None,
    skills_section: str = "",
    max_context_tokens: int = DEFAULT_CONTEXT_WINDOW,
    provider_name: str = "",
    model_name: str = "",
) -> str:
    sections: list[str] = [
        "You are Zenith, an TUI AI coding assistant.",
        f"<env>\n{_build_env_section(workspace_root, mode)}\n</env>",
    ]
    tier_enhancements = get_tier_prompt_enhancements(detect_model_tier(model_name, provider_name))
    if tier_enhancements:
        sections.append(tier_enhancements)
    sections.append(PLAN_MODE_INSTRUCTIONS if mode == PLAN_MODE else BUILD_MODE_INSTRUCTIONS)
    sections.append(SYSTEM_GUIDELINES)
    sections.append(TOOL_DISCOVERY_HINT)
    sections.append(TOOL_GUIDELINES_HINT.format(path=ensure_tool_guidelines_file(workspace_root)))
    if skills_section:
        sections.append(skills_section)
    context_files = load_context_files(workspace_root)
    if context_files:
        sections.append(
            f"<project_context>\n{format_context_files(context_files)}\n</project_context>"
        )
    return "\n\n".join(sections)


def build_plan_system_prompt(
    workspace_root: str, provider_name: str = "", model_name: str = ""
) -> str:
    return build_system_prompt(
        workspace_root, mode=PLAN_MODE, provider_name=provider_name, model_name=model_name
    )


def _build_env_section(workspace_root: str, mode: str) -> str:
    os_name = platform.system()
    shell_name = "powershell" if os_name == "Windows" else "bash"
    if os_name == "Windows":
        constraint = (
            "The bash tool runs in PowerShell on Windows. Use PowerShell commands and "
            "syntax only; Unix shell syntax (mkdir -p, rm -rf, ls -la, brace expansion, "
            "/-style paths as commands) will fail. Write commands for PowerShell, not Unix."
        )
    else:
        constraint = (
            "The bash tool runs in bash. Use bash commands and syntax; do not use "
            "Windows PowerShell cmdlets. Write commands for bash."
        )
    return (
        f"OS: {os_name} | Shell: {shell_name} | Mode: {mode} | Dir: {workspace_root}\n"
        f"{constraint}"
    )
