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
- **Tool Usage Boundary**: Use tools (`file_read`, `file_edit`, `file_write`, `bash`, `glob`, `grep`, `lsp`) when inspecting, searching, or modifying code or executing commands. For greetings, general questions, or non-file queries, answer directly in markdown text without tools.
- **Editing Rule**: Always `file_read` before `file_edit`. Match exact whitespace and context lines. Make surgical edits and verify with tests.
- **Directness**: Keep outputs direct, concise, and non-repetitive.
</guidelines>
"""

BUILD_MODE_INSTRUCTIONS = """\
## MODE: BUILD (Autonomous Execution Engine)
You are in **BUILD mode**. Your objective is to resolve tasks autonomously and cleanly:
- **Code Actions**: Use tools (`file_read`, `file_edit`, `file_write`, `bash`, `glob`, `grep`, `lsp`) to search, inspect, modify, and test code.
- **Surgical Execution**: Read before editing. Make exact edits. Run test verification when changes are complete.
- **Fluid Intent**: For greetings, general Q&A, or post-task summaries, respond directly in standard markdown without tool calls.
"""

PLAN_MODE_INSTRUCTIONS = """\
## MODE: PLAN (Architectural Design & Read-Only Analysis)
You are in **PLAN mode**. Your objective is to analyze the codebase and design structured technical implementation plans:
- **Read-Only Scope**: Use exploration tools (`file_read`, `glob`, `grep`, `lsp`) to inspect existing files. NEVER call mutating tools (`file_edit`, `file_write`) or modifying shell commands.
- **Plan Output**: Produce a clean Markdown plan with:
  1. **Overview**: Objectives & technical approach.
  2. **Architecture & File Changes**: Affected components, new/modified files (`file:line`).
  3. **Implementation Steps**: Numbered sequential steps.
  4. **Verification Plan**: Commands to test the implementation.
- Conclude by asking: *"Ready to implement? Switch to build mode with `/build`"*
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
    is_windows = os_name == "Windows"

    parts: list[str] = [
        f"Working directory: {workspace_root}",
        f"Agent mode: {mode}",
        f"OS: {os_name} {platform.release()}",
        f"Today's date: {datetime.now(UTC).strftime('%Y-%m-%d')}",
    ]

    if is_windows:
        parts.append("PLATFORM: Windows (PowerShell) | Use PowerShell commands")
    else:
        parts.append("PLATFORM: Unix-like | Shell: bash")

    return "\n".join(parts)
