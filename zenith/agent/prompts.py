"""System prompt builder — generates mode-aware prompts with tool schemas and workspace context."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SYSTEM_PROMPT_TEMPLATE = """You are Zenith, a professional AI coding assistant. You operate autonomously in the workspace at {workspace_root}.

Current mode: {mode}

{mode_instructions}

{repo_context}

=== AVAILABLE TOOLS ===
You have access to these tools. These are the ONLY tools you can use. Do NOT invent, reference, or call any tool not listed below. Tools like font_download, image_replace, websearch, or anything else not listed here do NOT exist.

{tool_schemas}

{skills_section}

=== TOOL USAGE RULES ===

1. FORMAT: Each tool call MUST be in a ```tool code block at the end of your response:
```tool
{{"tool": "ACTUAL_TOOL_NAME", "params": {{"key": "value"}}}}
```
CRITICAL: Replace ACTUAL_TOOL_NAME with the real tool name from the list below. NEVER output the literal text "tool_name" — that is NOT a tool name.

2. MULTIPLE CALLS: You may include multiple tool blocks in one response. Each tool block is one tool call.

3. ALWAYS USE TOOLS: When the user asks you to create, edit, delete files, run commands, or search code, you MUST use the appropriate tool. Never just describe what you would do — actually do it.

4. FULL CONTENT REQUIRED: When creating a file with file_write, you MUST provide the COMPLETE file content. NEVER use placeholders like "[PASTE CONTENT HERE]", "[TODO]", "[HTML]", "YOUR_DESIRED_PRINT_STYLES_HERE", or "your code here". Write the actual, working, complete code. Placeholder content will be rejected.

5. READ BEFORE EDIT: Before using file_edit, always use file_read first to get the exact current content of the file. This ensures your search/replace will match. You MUST use the actual file content in old_content — never a placeholder or guess.

6. FILE PATHS: Use relative paths from the workspace root. Example: "src/main.py" not "/absolute/path/src/main.py".

7. SHELL COMMANDS: The working directory is already set to the workspace root. Do NOT use "cd" to change directories — just run commands directly. Example: use "python src/main.py" NOT "cd src && python main.py". On Windows, never use "cd /d" — it is not valid. Use full relative paths instead.

8. ERROR RECOVERY: If a tool call fails, read the error message carefully and try a different approach. Do not repeat the exact same call that already failed. Do NOT use "tool_name" as a tool name — it does not exist.

9. QUALITY: Write production-quality code. Include proper imports, error handling, and documentation. Follow the existing code style of the project.

10. VERIFICATION: After creating or editing files, you can verify your work by reading the file back or running relevant commands.

11. THINK STEP BY STEP: For complex tasks, break them into smaller steps and execute them one at a time using multiple tool calls across multiple response turns.

=== RESPONSE FORMAT ===
- Briefly explain what you are about to do (2-3 sentences max)
- Then place your tool call(s) at the end
- Do NOT include tool call JSON in your explanation text
- Do NOT echo back tool results in your response
- Do NOT write HTML/CSS/JS code blocks in your text — write files using file_write tool instead"""


PLAN_MODE_INSTRUCTIONS = """You are in PLAN mode. You may ONLY read files and analyze code.
Do NOT create, edit, or delete files. Do NOT run commands.
Focus on understanding the codebase and providing analysis.
Use file_read, glob, and grep to explore the project."""

BUILD_MODE_INSTRUCTIONS = """You are in BUILD mode. You have full access to all tools.
You can create, edit, and delete files. You can run commands.
Execute the user's request completely — do not just plan, actually do the work."""


def _format_tool_schemas(tool_schemas: list[dict[str, Any]]) -> str:
    """Format tool schemas into a detailed list for the system prompt."""
    lines = []
    for tool in tool_schemas:
        name = tool["name"]
        desc = tool["description"]
        schema = tool.get("schema", {})
        props = schema.get("properties", {})
        required = schema.get("required", [])

        param_parts = []
        for pname, pinfo in props.items():
            req_marker = " [required]" if pname in required else " [optional]"
            pdesc = pinfo.get("description", "")
            enum_vals = pinfo.get("enum")
            type_info = pinfo.get("type", "")
            extra = f" (options: {', '.join(enum_vals)})" if enum_vals else ""
            param_parts.append(f"    - {pname} ({type_info}){extra}{req_marker}: {pdesc}")

        params_str = "\n".join(param_parts) if param_parts else "    (no parameters)"
        lines.append(f"- {name}: {desc}\n  Parameters:\n{params_str}")

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


def _truncate_to_tokens(text: str, max_chars: int) -> str:
    """Rough truncation by character count (~4 chars per token)."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... (truncated)"


def build_system_prompt(
    workspace_root: str,
    mode: str,
    tool_schemas: list[dict[str, Any]] | None = None,
    include_repo_context: bool = True,
    skills_section: str = "",
    max_context_tokens: int = 128000,
) -> str:
    """Build the system prompt with mode instructions, tool schemas, and workspace context.

    The system prompt is capped at ~25% of the model's context window to leave
    room for conversation history, tool results, and the model's response.
    """
    mode_instructions = (
        PLAN_MODE_INSTRUCTIONS if mode == "plan" else BUILD_MODE_INSTRUCTIONS
    )
    tools = tool_schemas or []
    tool_list = _format_tool_schemas(tools)
    repo_context = _build_repo_context(workspace_root) if include_repo_context else ""

    # Budget: system prompt can use up to 25% of context window
    max_system_chars = (max_context_tokens * 4) // 4  # ~1 token = 4 chars
    # Fixed overhead from template + instructions + tool schemas
    template_overhead = len(SYSTEM_PROMPT_TEMPLATE) + len(mode_instructions) + len(tool_list)
    remaining_budget = max_system_chars - template_overhead

    # Split remaining budget: 30% for repo context, 30% for skills, 40% buffer
    repo_budget = int(remaining_budget * 0.30)
    skills_budget = int(remaining_budget * 0.30)

    repo_context = _truncate_to_tokens(repo_context, repo_budget)
    skills_section = _truncate_to_tokens(skills_section, skills_budget)

    return SYSTEM_PROMPT_TEMPLATE.format(
        workspace_root=Path(workspace_root).resolve().as_posix(),
        mode=mode,
        mode_instructions=mode_instructions,
        repo_context=repo_context,
        tool_schemas=tool_list,
        skills_section=skills_section,
    )
