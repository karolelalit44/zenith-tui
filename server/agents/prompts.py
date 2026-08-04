
from __future__ import annotations
import platform
from datetime import UTC, datetime
from typing import Any
from server.agents.provider_adapters import detect_model_tier, get_tier_prompt_enhancements
from server.workspace.context import format_context_files, load_context_files

SYSTEM_GUIDELINES = """\
<guidelines>
- Code Actions: Use available tools to inspect, analyze, write, or modify code as needed for the user's request.
- General Queries: Answer directly in markdown text without tool calls.
</guidelines>
"""

BUILD_MODE_INSTRUCTIONS = """\
## MODE: BUILD
Objective: Complete coding tasks autonomously. Understand the codebase, make minimal targeted changes, and verify your work.
"""

PLAN_MODE_INSTRUCTIONS = """\
## MODE: PLAN
Objective: Analyze the codebase using read-only tools and output a clear, structured Markdown implementation plan.
"""


def build_system_prompt(workspace_root: str, mode: str = "build", tool_schemas: list[dict[str, Any]] | None = None, skills_section: str = "", max_context_tokens: int = 128000, provider_name: str = "", model_name: str = "") -> str:
    sections: list[str] = ["You are Zenith, an TUI AI coding assistant.", f"<env>\n{_build_env_section(workspace_root, mode)}\n</env>"]

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


def build_plan_system_prompt(workspace_root: str, provider_name: str = "", model_name: str = "") -> str:
    return build_system_prompt(workspace_root, mode="plan", provider_name=provider_name, model_name=model_name)


def _build_env_section(workspace_root: str, mode: str) -> str:
    os_name = platform.system()
    shell_name = "powershell" if os_name == "Windows" else "bash"
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    return f"OS: {os_name} | Shell: {shell_name} | Mode: {mode} | Dir: {workspace_root} | Date: {today}"
