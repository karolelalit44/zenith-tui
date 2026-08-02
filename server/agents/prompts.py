"""System prompt builder — constructs the system prompt for the agent loop."""

from __future__ import annotations

import platform
import sys
from datetime import UTC, datetime
from typing import Any

from server.agents.provider_adapters import detect_model_tier, get_tier_prompt_enhancements
from server.workspace.context import format_context_files, load_context_files
from server.workspace.git import GitOps

# ---------------------------------------------------------------------------
# Structured XML sections
# ---------------------------------------------------------------------------

CRITICAL_RULES = """\
1. **READ BEFORE EDIT**: Read a file before editing it. Match text exactly.
2. **BE AUTONOMOUS**: Search, read, decide, act. Don't ask — do. Break tasks into steps. Systematically try alternatives until blocked by a hard external limit.
3. **TEST AFTER CHANGES**: Run tests after each modification.
4. **BE CONCISE**: Output <4 lines of text (tool use doesn't count). Fully implement everything requested regardless. No preamble/postamble. No emojis. One-word answers when possible. Never send acknowledgement-only responses.
5. **NEVER COMMIT** unless explicitly told. Never commit secrets. Never add comments unless asked. No URL guessing.
"""

WORKFLOW = """\
For every task (don't narrate):
- **Before**: Search codebase, read affected files, check git log/blame.
- **While**: Read entire file before editing. Verify exact whitespace. Make one logical change at a time. Test after each change. Fix failures immediately. Keep going until query is fully resolved.
- **Before finishing**: Verify entire query resolved. Run lint/typecheck if available. Keep response <4 lines.
"""

EDITING_FILES = """\
Tools: `file_edit` (find/replace), `file_write` (create/overwrite), `file_read`.
When using file_edit: read context first → note exact indentation → copy exact text with 3-5 surrounding lines → verify old_content appears once → verify edit succeeded → run tests.
Use absolute paths. Run tools in parallel when safe.
"""

TOOL_USAGE = """\
- Use tools over speculation
- Search before assuming, read before editing
- Explain non-trivial bash commands briefly
- Avoid interactive commands
- Reference code via `file:line` pattern
"""

PROACTIVENESS = """\
Do it fully (including ALL follow-ups). Never describe what you'll do — just do it. Plans/TODOs without execution are failure. After completing, stop. When asked how to approach, explain first; don't auto-implement.
"""

CODE_CONVENTIONS = """\
Verify libraries exist before using them (check imports, package.json, pyproject.toml). Read similar code for patterns. Match existing style. Respect surrounding code. Be surgical in existing codebases, ambitious in new projects. Follow security best practices.
"""

# ---------------------------------------------------------------------------
# Plan mode instructions (inspired by Crush's task.md.tpl)
# ---------------------------------------------------------------------------

PLAN_MODE_INSTRUCTIONS = """\
## PLAN MODE — Read-Only Analysis & Architecture

You are in **PLAN mode**. Your job is to think, analyze, and produce structured plans. You do NOT execute changes.

### What to do in PLAN mode:
- **Analyze** the request and break it into concrete, actionable steps
- **Search** the codebase to understand existing patterns and constraints
- **Read** files to understand current state before proposing changes
- **Propose** a clear architecture with file paths, function names, and data flow
- **Structure** your plan with numbered steps, each referencing specific files/lines
- **Be specific** — say exactly which files to create/modify, what functions to add, what patterns to follow

### What NOT to do in PLAN mode:
- Do NOT use file_edit, file_write, or file_delete
- Do NOT run bash commands that modify files
- Do NOT create directories or write any code
- Do NOT auto-commit anything

### Plan output format:
Use Markdown with clear sections:
1. **Overview** — what we're building and why
2. **Architecture** — services, modules, data flow
3. **File Structure** — exact paths and their purpose
4. **Implementation Steps** — numbered list with file:line references
5. **Data Models** — schemas, types, interfaces
6. **API Design** — endpoints, request/response shapes
7. **Testing Strategy** — what to test and how

### When to transition to build mode:
After presenting the plan, ask the user: "Ready to implement? Switch to build mode with /build"
"""

# ---------------------------------------------------------------------------
# Build mode instructions
# ---------------------------------------------------------------------------

BUILD_MODE_INSTRUCTIONS = """\
## BUILD MODE — Full Execution

You are in **BUILD mode**. Your job is to execute the task completely using tools.

### What to do in BUILD mode:
- Use all available tools to implement the changes
- Be autonomous — search, read, edit, test, commit
- Make all changes, run all tests, verify everything works
- Don't ask questions — just do it

### Plan Execution (when a `<plan_to_execute>` block is present):
If a `<plan_to_execute>` XML block is included in the system messages, that is your task specification. Follow it exactly:
1. Create every file listed in the plan's file structure
2. Implement each architecture component as described
3. Follow the exact implementation order specified in the plan
4. Use the exact data models, API design, and patterns from the plan
5. Do NOT deviate from the plan unless blocked by a hard error
6. If blocked, explain the blocker and propose a minimal deviation

### Workflow:
1. Search for relevant files
2. Read files to understand current state
3. Make changes (file_edit, file_write, bash)
4. Run tests after each change
5. Fix any failures immediately
6. Continue until task is complete
"""

# ---------------------------------------------------------------------------
# Universal Model Guidelines (consistent high-quality output across ALL providers)
# ---------------------------------------------------------------------------

UNIVERSAL_MODEL_GUIDELINES = """\
<universal_guidelines>
1. ALWAYS deliver your complete user-facing response (explanations, plans, code, answers) in the message content body.
2. For reasoning/thinking models: write your full response in the final message content payload outside of thinking/reasoning blocks.
3. Be autonomous: search before assuming, read before editing, verify after changes.
4. Format all responses using high-quality GitHub-flavored markdown.
</universal_guidelines>
"""

# ---------------------------------------------------------------------------
# Few-shot examples for key tools
# ---------------------------------------------------------------------------

FEW_SHOT_EXAMPLES = """\

<tool_usage_examples>
Below are examples of correct tool usage patterns:

## file_read then file_edit (the only safe editing pattern)

user: Rename the `calculate_total` function to `compute_total` in utils.py

assistant: [file_read utils.py]
[finds `def calculate_total(items):` on line 42]
[file_edit utils.py with old_content="def calculate_total(items):" new_content="def compute_total(items):"]
Done

## file_read for context before editing

user: Add error handling to the database connection in db.py

assistant: [file_read db.py]
[reads the connect() function and surrounding code]
[file_edit db.py with exact old_content including 3-5 surrounding lines, new_content with try/except added]
[runs tests]
Done

## bash for testing

user: Run the test suite

assistant: [bash command="python -m pytest server/tests/ -v"]
[sees 3 failures, reads the failing test files]
[file_edit to fix the source code]
[re-runs tests]
All 47 tests pass

## Multi-step: read → understand → edit → verify

user: The login function should also validate email format

assistant: [grep pattern="def login" include="*.py"]
[file_read the auth.py file at the login function]
[file_edit to add email validation regex]
[bash command="python -m pytest server/tests/test_auth.py -v"]
Done — added email format validation using RFC 5322 regex pattern

## What NOT to do (these patterns cause errors):

file_edit without file_read first → "old_content not found" error
Guessing file contents instead of reading → wrong edit location
Editing without running tests → silent breakage
Asking "what should I do?" when tools can answer → be autonomous
</tool_usage_examples>
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
    """Build the complete system prompt with all sections."""
    sections: list[str] = []

    tier = detect_model_tier(model_name, provider_name)
    tier_enhancements = get_tier_prompt_enhancements(tier)

    # --- Role ---
    sections.append("You are Zenith, a powerful AI coding assistant that runs in the CLI.")

    # --- Environment block ---
    env_section = _build_env_section(workspace_root, mode)
    sections.append(f"<env>\n{env_section}</env>")

    # --- Universal Guidelines & Tier Enhancements ---
    sections.append(UNIVERSAL_MODEL_GUIDELINES)
    sections.append(tier_enhancements)

    # --- Mode-specific instructions ---
    if mode == "plan":
        sections.append(f"<plan_mode>\n{PLAN_MODE_INSTRUCTIONS}</plan_mode>")
    else:
        sections.append(f"<build_mode>\n{BUILD_MODE_INSTRUCTIONS}</build_mode>")

    # --- Critical Rules ---
    sections.append(f"<critical_rules>\n{CRITICAL_RULES}</critical_rules>")

    # --- Workflow ---
    sections.append(f"<workflow>\n{WORKFLOW}</workflow>")

    # --- Editing Files ---
    sections.append(f"<editing_files>\n{EDITING_FILES}</editing_files>")

    # --- Tool Usage ---
    sections.append(f"<tool_usage>\n{TOOL_USAGE}</tool_usage>")

    # --- Proactiveness ---
    sections.append(f"<proactiveness>\n{PROACTIVENESS}</proactiveness>")

    # --- Code Conventions ---
    sections.append(f"<code_conventions>\n{CODE_CONVENTIONS}</code_conventions>")

    # --- Few-shot Examples ---
    sections.append(FEW_SHOT_EXAMPLES)

    # --- Skills (if provided) ---
    if skills_section:
        sections.append(skills_section)

    # --- Git context ---
    git_section = _build_git_section(workspace_root)
    if git_section:
        sections.append(f"<git_context>\n{git_section}</git_context>")

    # --- Project context files ---
    context_files = load_context_files(workspace_root)
    if context_files:
        formatted = format_context_files(context_files)
        sections.append(
            "# Project-Specific Context\n"
            "Make sure to follow the instructions in the context below.\n"
            f"<project_context>\n{formatted}\n</project_context>"
        )

    # --- Tool schemas (for reference) ---
    if tool_schemas:
        tool_block = _format_tool_schemas(tool_schemas)
        sections.append(f"<available_tools>\n{tool_block}\n</available_tools>")

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Standalone plan mode prompt (inspired by Crush's task.md.tpl + Aider's
# architect_prompts.py — lightweight, focused, read-only)
# ---------------------------------------------------------------------------

def build_plan_system_prompt(
    workspace_root: str,
    provider_name: str = "",
    model_name: str = "",
) -> str:
    """Build a focused, lightweight system prompt for plan mode."""
    sections: list[str] = []

    tier = detect_model_tier(model_name, provider_name)
    tier_enhancements = get_tier_prompt_enhancements(tier)

    sections.append(
        "You are Zenith in PLAN mode — an expert software architect.\n"
        "Analyze the codebase and produce a structured implementation plan.\n"
        "You do NOT write code, edit files, or make changes."
    )

    env = _build_env_section(workspace_root, "plan")
    sections.append(f"<env>\n{env}</env>")

    sections.append(UNIVERSAL_MODEL_GUIDELINES)
    sections.append(tier_enhancements)

    sections.append("""<rules>
1. NEVER edit, create, or delete files. NEVER run commands that modify the filesystem.
2. Use glob, grep, file_read, and lsp tools to explore. Search before assuming.
3. Be specific: name exact files, functions, types, and line numbers.
4. If ambiguous, state assumptions and proceed with the most reasonable interpretation.
</rules>""")

    sections.append("""Respond with a plan using these sections:
## Overview — one paragraph
## Architecture — services, modules, data flow
## File Structure — exact paths and purpose
## Implementation Steps — numbered, referencing files/lines
## Data Models — schemas as code fences
## API Design — endpoints
## Testing Strategy — what to test
End with: "Ready to implement? Switch to build mode with `/build`"

CRITICAL FOR ALL MODELS (INCLUDING REASONING/THINKING MODELS):
You MUST output your complete final plan / answer text in your final response message CONTENT payload (outside thinking/reasoning blocks).
Do NOT output an empty or tiny message content payload.
""")

    git = _build_git_section(workspace_root)
    if git:
        sections.append(f"<git_context>\n{git}</git_context>")

    context_files = load_context_files(workspace_root)
    if context_files:
        sections.append(
            "<project_context>\n"
            + format_context_files(context_files)
            + "\n</project_context>"
        )

    return "\n\n".join(sections)


def _build_env_section(workspace_root: str, mode: str) -> str:
    """Build the <env> block with environment metadata."""
    import shutil
    import subprocess

    os_name = platform.system()
    is_windows = os_name == "Windows"

    if is_windows:
        shell_name = "PowerShell"
        shell_exe = shutil.which("pwsh") or shutil.which("powershell") or "powershell"
        try:
            shell_version = subprocess.check_output(
                [shell_exe, "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"],
                timeout=5, stderr=subprocess.DEVNULL,
            ).decode().strip()
        except Exception:
            shell_version = "unknown"
    else:
        shell_name = "bash"
        shell_exe = shutil.which("bash") or "/bin/bash"
        try:
            shell_version = subprocess.check_output(
                [shell_exe, "--version"], timeout=5, stderr=subprocess.DEVNULL,
            ).decode().splitlines()[0].strip() if os_name != "Darwin" else "bash (macOS)"
        except Exception:
            shell_version = "unknown"

    parts: list[str] = []

    # Platform prefix (CRITICAL: this must come first so the model knows which OS)
    if is_windows:
        parts.append(
            "PLATFORM: Windows\n"
            "SHELL: PowerShell\n"
            "CRITICAL: Every command you run MUST use PowerShell syntax.\n"
            "PowerShell equivalents:\n"
            "  ls / dir       → Get-ChildItem\n"
            "  cat            → Get-Content\n"
            "  grep pattern   → Select-String -Pattern 'pattern'\n"
            "  head -N        → Select-Object -First N\n"
            "  tail -N        → Select-Object -Last N\n"
            "  find . -name   → Get-ChildItem -Recurse -Filter\n"
            "  wc -l          → Measure-Object -Line\n"
            "  cp             → Copy-Item\n"
            "  mv             → Move-Item\n"
            "  rm             → Remove-Item\n"
            "  mkdir          → New-Item -ItemType Directory\n"
            "  echo > file    → Set-Content file\n"
            "  which / where  → Get-Command\n"
            "  env vars       → $env:VARIABLE_NAME\n"
            "  path separator → \\ (backslash)\n"
            "DO NOT use: ls, cat, grep, find, head, tail, chmod, curl, wget, sed, awk, tee, wc, touch, cp, mv, rm\n"
            "DO NOT pass UNIX flags like '-la', '-l', '-rf' to PowerShell commands (e.g., use 'ls tui/' or 'Get-ChildItem tui/' instead of 'ls -la tui/').\n"
            "In PLAN mode, prefer using structured tools ('glob', 'grep', 'file_read') over shell commands to explore files.\n"
            "These are Linux commands and WILL fail.\n"
        )
    else:
        parts.append(
            "PLATFORM: Unix-like\n"
            "SHELL: bash\n"
            "Use standard bash/sh commands.\n"
        )

    # Metadata
    parts.extend([
        f"Working directory: {workspace_root}",
        f"Agent mode: {mode}",
        f"Platform: {sys.platform}",
        f"OS: {os_name} {platform.release()}",
        f"Shell: {shell_name} ({shell_exe})",
        f"Shell version: {shell_version}",
        f"Python: {platform.python_version()}",
        f"Today's date: {datetime.now(UTC).strftime('%Y-%m-%d')}",
    ])

    # Windows-specific reminders (reinforce the top-level prefix)
    if is_windows:
        parts.append(
            "\nREMEMBER: You are on Windows. Use PowerShell-compatible commands only.\n"
            "- Use: Get-ChildItem, Select-String, Get-Content, Set-Content\n"
            "- Use: Get-Process, Get-Service, Test-Path, Copy-Item, Remove-Item\n"
            "- Use: Select-Object -First N (instead of head), Select-Object -Last N\n"
            "- Use: Where-Object { $_ -match 'pattern' } (instead of grep)\n"
            "- Use: ForEach-Object, Sort-Object, Measure-Object\n"
            "- Do NOT use: ls, cat, grep, find, head, tail, chmod, curl, wget, sed, awk, tee, wc\n"
            "- Pipeline: pipe | works the same way\n"
            "- File paths: use forward slashes or backslashes, both work in PowerShell\n"
        )

    return "\n".join(parts)


def _build_git_section(workspace_root: str) -> str:
    """Build the <git_context> block with git status, branch, and recent commits.

    Returns empty string if not a git repo.
    """
    try:
        git = GitOps(workspace_root)
        return git.get_prompt_context()
    except Exception:
        return ""


def _format_tool_schemas(schemas: list[dict[str, Any]]) -> str:
    """Format tool schemas into a readable reference block."""
    parts: list[str] = []
    for s in schemas:
        name = s.get("name", "")
        desc = s.get("description", "")
        schema = s.get("schema", {})
        params = schema.get("properties", {})
        required = schema.get("required", [])

        param_lines = []
        for pname, pdef in params.items():
            ptype = pdef.get("type", "any")
            pdesc = pdef.get("description", "")
            req_marker = " (required)" if pname in required else ""
            param_lines.append(f"  - {pname} ({ptype}){req_marker}: {pdesc}")

        param_str = "\n".join(param_lines) if param_lines else "  (no parameters)"
        parts.append(f"- **{name}**: {desc}\n{param_str}")

    return "\n".join(parts)
