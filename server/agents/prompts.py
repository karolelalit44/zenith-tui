from __future__ import annotations

import platform
from datetime import UTC, datetime
from typing import Any

from server.agents.provider_adapters import detect_model_tier, get_tier_prompt_enhancements
from server.config.constants import BUILD_MODE, DEFAULT_CONTEXT_WINDOW, PLAN_MODE
from server.workspace.context import format_context_files, load_context_files

SYSTEM_GUIDELINES = (
    "<guidelines>\n"
    "- Code Actions: Use available tools to inspect, analyze, write, or modify code as needed for the user's request.\n"
    "- Tool Choice: Prefer the dedicated tool for each job - file_write/file_edit to create or modify "
    "files, file_read/glob/grep to inspect code, websearch/webfetch for web research. Use bash only for "
    "operations with no dedicated tool (running tests, builds, installs, git commands).\n"
    "- Workspace Scoping: Never list the whole repository. Scope globs to the subdirectory you "
    "are working in (e.g. glob pattern='<target>/**/*' or 'src/**/*.py'); never run glob '**/*' "
    "from the repo root and never run a recursive shell listing (Get-ChildItem -Recurse / "
    "find .). Whole-repo listings match node_modules and .git, return thousands of files, and "
    "blow the context.\n"
    "- Inspect Before Writing: before creating files in a folder, inspect what is already there "
    "with a scoped glob or file_read so you do not overwrite or duplicate existing work.\n"
    "- Write Discipline: file_write requires path and content - always pass both. After file_write "
    "confirms a file was created, do not re-write it; to change an existing file, read it first "
    "(file_read) then edit it (file_edit).\n"
    "- Batching: You may emit several independent tool calls in a single response (e.g. multiple "
    "file_write calls to scaffold a project). Only batch calls that do not depend on each other.\n"
    "- Verify Generated Projects: after generating a new project, install its dependencies and "
    "run its tests to confirm it actually works before finishing.\n"
    "- Environment Limits: if a verification step (install, test, build, compose) cannot run in "
    "this environment (no network, missing runtime), report that explicitly instead of claiming "
    "it succeeded.\n"
    "- External Products: If the request is about an external product, tool, framework, or service, "
    "research it with websearch to find sources, then webfetch specific pages to read them; for long "
    "pages, pass an 'extract' question to webfetch to get just the relevant answer. Do not "
    "substitute this local codebase for the real product.\n"
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
    "Tool schemas are loaded on demand to keep the context small. Only call "
    "discover_capabilities when you do not yet know which tools are available, "
    "and only call get_tool_definition('<tool_name>') for a tool whose schema "
    "you have not loaded yet. Once a schema is loaded it stays loaded and is "
    "always available to you, so NEVER call discover_capabilities or "
    "get_tool_definition a second time in the same turn, and never re-call a "
    "tool that already succeeded this turn. If no tool functions are available "
    "for this turn, answer directly instead.\n"
    "</tool_discovery>\n"
)


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
    today = datetime.now(UTC).strftime("%Y-%m-%d")
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
        f"OS: {os_name} | Shell: {shell_name} | Mode: {mode} | Dir: {workspace_root} | "
        f"Date: {today}\n{constraint}"
    )
