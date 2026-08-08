from __future__ import annotations

import platform
from datetime import UTC, datetime
from typing import Any

from server.agents.provider_adapters import detect_model_tier, get_tier_prompt_enhancements
from server.config.constants import BUILD_MODE, DEFAULT_CONTEXT_WINDOW, PLAN_MODE
from server.workspace.context import format_context_files, load_context_files

SYSTEM_GUIDELINES = "<guidelines>\n- Code Actions: Use available tools to inspect, analyze, write, or modify code as needed for the user's request.\n- General Queries: Answer directly in markdown text without tool calls.\n</guidelines>\n"
BUILD_MODE_INSTRUCTIONS = "## MODE: BUILD\nObjective: Complete coding tasks autonomously. Understand the codebase, make minimal targeted changes, and verify your work.\n"
PLAN_MODE_INSTRUCTIONS = "## MODE: PLAN\nObjective: Analyze the codebase using read-only tools and output a clear, structured Markdown implementation plan.\n"
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
    return f"OS: {os_name} | Shell: {shell_name} | Mode: {mode} | Dir: {workspace_root} | Date: {today}"
