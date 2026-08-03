"""System prompt builder — constructs smart, high-density system prompts for BUILD and PLAN modes."""

from __future__ import annotations

import platform
from datetime import UTC, datetime
from typing import Any

from server.agents.provider_adapters import detect_model_tier, get_tier_prompt_enhancements
from server.workspace.context import format_context_files, load_context_files
from server.workspace.git import GitOps

SYSTEM_GUIDELINES = """\
<guidelines>
- Code Actions: Use tools (file_read, file_edit, file_write, bash, glob, grep) to search, inspect, modify, test code.
- General Queries: Answer directly in markdown text without tool calls.
</guidelines>
"""

BUILD_MODE_INSTRUCTIONS = """\
## MODE: BUILD
Objective: Resolve coding tasks autonomously. Read before editing, make surgical edits, verify with tests. For greetings/general questions, respond in markdown without tools.
"""

PLAN_MODE_INSTRUCTIONS = """\
## MODE: PLAN
Objective: Read-only codebase analysis & planning. Use read-only tools (file_read, glob, grep), output Markdown plan.
"""


def build_system_prompt(
    workspace_root: str,
    mode: str = "build",
    tool_schemas: list[dict[str, Any]] | None = None,
    skills_section: str = "",
    max_context_tokens: int = 128000,
    provider_name: str = "",
    model_name: str = "",
) -> str:
    """Build a smart, high-density system prompt for BUILD or PLAN mode."""
    sections: list[str] = [
        "You are Zenith, an AI coding assistant running in the CLI.",
        f"<env>\n{_build_env_section(workspace_root, mode)}\n</env>",
    ]

    tier_enhancements = get_tier_prompt_enhancements(detect_model_tier(model_name, provider_name))
    if tier_enhancements:
        sections.append(tier_enhancements)

    sections.append(PLAN_MODE_INSTRUCTIONS if mode == "plan" else BUILD_MODE_INSTRUCTIONS)
    sections.append(SYSTEM_GUIDELINES)

    if skills_section:
        sections.append(skills_section)

    context_files = load_context_files(workspace_root)
    if context_files:
        sections.append(f"<project_context>\n{format_context_files(context_files)}\n</project_context>")

    return "\n\n".join(sections)


def build_plan_system_prompt(
    workspace_root: str,
    provider_name: str = "",
    model_name: str = "",
) -> str:
    """Build a focused system prompt for plan mode."""
    return build_system_prompt(workspace_root, mode="plan", provider_name=provider_name, model_name=model_name)


def _build_env_section(workspace_root: str, mode: str) -> str:
    """Build the <env> metadata block efficiently."""
    os_name = platform.system()
    today = datetime.now(UTC).strftime('%Y-%m-%d')
    return f"OS: {os_name} | Mode: {mode} | Dir: {workspace_root} | Date: {today}"
