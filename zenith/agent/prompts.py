"""System prompt builder — generates mode-aware prompts with tool list and workspace context."""

from __future__ import annotations

from pathlib import Path
from typing import Optional


SYSTEM_PROMPT_TEMPLATE = """You are Zenith, an AI coding assistant working in {workspace_root}.

Current mode: {mode}

{mode_instructions}

{repo_context}

You have access to these tools:
{tool_list}

{skills_section}

When you need to use a tool, explain your plan briefly in regular text, then place your tool call at the end of your response in a tool block:
```tool
{{"tool": "tool_name", "params": {{"key": "value"}}}}
```

Do not mix raw JSON tool calls inside your explanation text.
You can make multiple tool calls by including multiple tool blocks."""


PLAN_MODE_INSTRUCTIONS = """You are in PLAN mode. You may ONLY read files and analyze code.
Do NOT create, edit, or delete files. Do NOT run commands.
Focus on understanding the codebase and providing analysis."""

BUILD_MODE_INSTRUCTIONS = """You are in BUILD mode. You have full access to all tools.
You can create, edit, and delete files. You can run commands.
Execute the user's request completely."""


def _format_tool_list(tool_names: list[str]) -> str:
    """Format tool names into a readable list for the system prompt."""
    descriptions = {
        "bash": "Execute shell commands",
        "file_read": "Read file contents with line numbers",
        "file_write": "Create new files",
        "file_edit": "Edit existing files using search/replace",
        "file_delete": "Delete files",
        "glob": "Search files by glob pattern",
        "grep": "Search file contents using regex",
        "webfetch": "Fetch content from a URL",
        "websearch": "Search the web",
    }
    lines = []
    for name in tool_names:
        desc = descriptions.get(name, "")
        lines.append(f"- {name}: {desc}")
    return "\n".join(lines) if lines else "- (no tools available)"


def _build_repo_context(workspace_root: str) -> str:
    """Build workspace context section for the system prompt."""
    try:
        from zenith.workspace.repo_map import RepoMap

        repo = RepoMap(workspace_root)
        summary = repo.get_summary()
        key_files = repo.get_key_files()

        parts = [f"Project summary: {summary}"]
        if key_files:
            parts.append(f"Key files: {', '.join(key_files[:15])}")

        return "\n".join(parts)
    except Exception:
        return ""


def build_system_prompt(
    workspace_root: str,
    mode: str,
    tool_names: list[str] | None = None,
    include_repo_context: bool = True,
    skills_section: str = "",
) -> str:
    """Build the system prompt with mode instructions, tools, and workspace context."""
    mode_instructions = (
        PLAN_MODE_INSTRUCTIONS if mode == "plan" else BUILD_MODE_INSTRUCTIONS
    )
    tools = tool_names or []
    tool_list = _format_tool_list(tools)
    repo_context = _build_repo_context(workspace_root) if include_repo_context else ""

    return SYSTEM_PROMPT_TEMPLATE.format(
        workspace_root=Path(workspace_root).resolve().as_posix(),
        mode=mode,
        mode_instructions=mode_instructions,
        repo_context=repo_context,
        tool_list=tool_list,
        skills_section=skills_section,
    )
