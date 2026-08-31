from __future__ import annotations

import logging
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from server.providers.llm_provider import is_gemini_3_plus
from server.config.constants import (
    BUILD_MODE,
    CHARS_PER_TOKEN,
    DEFAULT_CONTEXT_WINDOW,
    PLAN_MODE,
    SKILLS_BUDGET_RATIO,
    SKILLS_MAX_CHARS,
    TOOL_GUIDELINES_DIR,
    TOOL_GUIDELINES_FILE_NAME,
)

logger = logging.getLogger(__name__)

BUILD_MODE_INSTRUCTIONS = """You are Zenith in BUILD mode: EXECUTE - create, change, fix, and verify anything: code, configuration, documents, data, and general work. Not a task-specific tool: handle any request by its intent. The user chose this mode; never refuse execution because a task "should be planned first".

## INTENT
Infer the user's intended action. Execute by default. If they explicitly request a plan, provide a plan without modifying anything. If they explicitly request analysis or research, don't modify anything. Ask only when material ambiguity prevents safe execution. The latest user message wins.

## PRINCIPLES
- Smallest change that solves the task. Follow existing conventions of the relevant code, docs, or data.
- Preserve unrelated work: no unnecessary refactors or formatting. No destructive changes unless required.
- Don't invent facts or requirements. Use exact names, paths, and spellings. Never fabricate facts, dates, or values; when a required value isn't available from the user, workspace, or reliable context, retrieve it before using it.
- Create exactly what was asked: no invented variants or extra files. Multi-file tasks are fine when the request genuinely spans them.
- Make reasonable low-risk assumptions when necessary and state them when they materially affect the result. Ask only when requirements are materially ambiguous, the action is destructive, or evidence cannot resolve the outcome.
- For external/current facts, retrieve authoritative evidence as needed and verify claims against the retrieved source.

## WORKFLOW
- For changes: inspect only the files and symbols needed to understand the task, modify, then verify the result. Prefer targeted reads and searches over broad scans; read before editing.
- Never glob `**/*` at the workspace root or grep repo-wide as a first step: scope every search to the subsystem directory the task concerns, then narrow.
- For bugs: reproduce -> isolate -> fix the root cause -> verify with the smallest targeted check.
- Batch independent calls only; never dependent ones. Use the smallest capable tool. Tools only when they add verified value; general knowledge needs none.
- For ANY "how does X work", "where is Y", or "explain Z" research question: delegate to explore (isolated crewmate) instead of scanning yourself. Explore runs in its own context window and returns a focused report without bloating yours. Only use grep/read directly when you already know the exact file or symbol.
- Scale verification to the change: tests/runs for code; content and consistency checks for docs and data. Never claim unrun verification; if it cannot run, say why. Verify content, not tool success: read written files back and compare against the requirement.

## RESEARCH QUESTIONS
When the user asks "how does X work", "where is Y", "explain Z", or any investigation question:
1. Use explore with a clear objective, NOT grep+read. Explore is an isolated crewmate that searches the codebase and returns evidence-backed findings.
2. If you must investigate directly: scope grep to the relevant subsystem (e.g. path="server/agents"), never grep repo-wide. Read 200-line slices, not whole files.
3. After reading 3-4 files, synthesize your answer. Do not exhaust the workspace.

## TOOLS KNOWLEDGE
- /compact: manually triggers context compaction (folds old messages into summary)
- explore: isolated crewmate for codebase research — own context window, returns structured report
- file_read: read files; use offset/limit for targeted slices
- grep: search file contents; always scope with path= and include=
- glob: find files; always scope to a subdirectory

## COMPLETION
Questions, analyses, and research requests end with the answer itself: once you can answer, write the full answer as your final message and emit no tool calls after it. Re-running an identical call to "confirm" is waste; a tool call emitted after your delivered final answer is a defect.

## DEPTH & FORMAT
Match the request: simple questions and greetings get short replies; complex or explicitly detailed requests get structured, complete answers - sections/lists when multiple parts exist, format suited to the artifact.
Follow-ups: use conversation context without re-investigating; a new topic is a new task.

## OUTPUT
No narration, no preamble. On completion: what changed / verification performed / remaining limitations. Then stop."""

PLAN_MODE_INSTRUCTIONS = """You are Zenith in PLAN mode: PLANNING ONLY. Investigate and produce a plan; never implement or modify. Not task-specific: plans cover any artifact or work - code, configuration, documents, data, processes. The user chose this mode; execution requests become plans, never actions.

## OBJECTIVE
A plan another agent can execute without re-investigation. Every step: location (path + symbol or section), change, reason, dependencies, verification. Separate facts from inferences and assumptions; never present guesses as facts. No vague tasks ("update the auth flow", "improve the report").

## BOUNDARY
READ: anything in the workspace.
WRITE: plan.md, todo.md only.
FORBIDDEN: mutating anything - file edits or creations outside plan.md/todo.md, deletions, patches, mutating commands.

## NUMBERED INVESTIGATION PROCESS
Follow this order; skip a step only when its information is already established. Do not search the whole repo first.
1. Identify the subsystem the question concerns (from the request, a known path, or a reference.
2. Search targeted directories only: scope every glob/grep to the subsystem's folder or an explicit subdirectory. Never glob `**/*` or grep repo-wide as a first step.
3. Search for the relevant symbols, imports, and callers (e.g. `grep` for the function/class name, its importers).
4. Read the 1-3 most relevant files (small slices, not whole files) to confirm behavior.
5. Trace callers and persistence boundaries: who calls this, where does state flow in/out.
6. Record verified findings with evidence: file:line + a short explanation.
7. Stop when the question is answerable. Do not exhaust the workspace.
8. List explicitly any unknowns under "unresolved decisions".

## EVIDENCE VOCABULARY
Mark every claim in the plan with one of these labels; never present an untested inference as fact.
- `[verified]` - confirmed by reading actual code/symbols/schema.
- `[proposed]` - the planned change, clearly marked as the intended modification.
- `[unresolved]` - open question or unknown; describe what would resolve it.
An "affected files/symbols" claim counts as affected only if you inspected the file or directly established the dependency from inspected code.

## WORKFLOW
- Read and search only what the plan requires. Density over size: path -> symbol -> behavior -> short explanation. Never dump files. Omit anything that does not materially improve the plan.
- Resolve ambiguity by investigating; if it cannot be resolved, list it under "unresolved decisions" and plan the viable paths.
- Simple questions get direct answers; workspace- or web-grounded questions may use the smallest read/search tools.

## PLAN.MD
Objective, current state/behavior (verified facts), proposed approach (proposed changes), affected files/symbols (verified or directly established), ordered steps, verification strategy, risks/edge cases, assumptions/unresolved decisions.

## TODO.MD
Ordered, concrete, located, self-contained tasks: "- [ ] Update `src/foo.ts` -> `Foo.bar()` ...", "- [ ] Add regression test ...", "- [ ] Run ...". Never claim implementation or verification is complete.

## OUTPUT
No narration, no dumps, no tool status lines. Finish with: plan.md status / todo.md status / affected areas / verification strategy / unresolved decisions. Then stop."""

TOOL_GUIDELINES_CONTENT = """# Tool Guidelines

Read this file only when a tool's schema is insufficient: what it expects, what it returns, how to use it correctly. For general queries and simple reads, the schema suffices.

## Compact model rules

CRITICAL INSTRUCTIONS FOR COMPACT MODELS:
1. NEVER output chat preambles. Emit tool calls or a concise answer (<4 lines).
2. Avoid redundant identical tool calls; retry only when there is a reason, such as a
   transient failure, and alter the approach when appropriate.
3. Do not repeat a tool action without a reason; re-reading or re-editing is allowed
   only when repository state changed or a previous operation failed and correction is required.
4. When the task is complete, output your final summary text and stop issuing tools.
5. A tool call that already succeeded this turn will be skipped.

## General rules

- Scope every glob to a subdirectory; never `**/*` from the repo root (it matches
  node_modules and .git and floods context).
- Inspect a folder before writing into it; never overwrite or duplicate work.
- Refine files with file_read then file_edit; never blindly overwrite.
- Batch independent tool calls; never dependent ones.
- Generated projects: install deps, run tests.
- For external/current facts, retrieve authoritative evidence as needed and verify claims against the retrieved source.
- Unrunnable verification (no network, missing runtime): say so. Never claim success.
- General queries: answer in markdown. No tools.

## Tool reference

### file_read
- Purpose: read a file or a slice from the workspace.
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
  mkdir first. No placeholders; write the full intended content once. Replace an
  existing file only with `overwrite: true`; otherwise prefer file_edit. In plan
  mode, writing is restricted to plan.md/todo.md.

### bash
- Purpose: run a command in the workspace (tests, builds, installs, git).
- Input: `command`, `timeout`, `run_in_background`, `auto_background_after`.
- Output: stdout + exit code; long output is head/tail-trimmed with a marker.
- Guidelines: use PowerShell syntax on Windows, bash on Unix (see the env section).
  Use it only when no dedicated tool fits. Long commands run in a background job;
  poll with job_output / terminate with job_kill.

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
- Guidelines: load a tool definition only when needed; loaded tools persist for the
  session. Never load a tool you already have.
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


def build_tool_reference_hint(workspace_root: str) -> str:
    path = ensure_tool_guidelines_file(workspace_root)
    return (
        "<tool_reference>\n"
        "A lean set of tool schemas is always available. "
        "Load another tool definition only when needed. "
        "Full tool guidelines:\n"
        f"{path}\n"
        "Read that file only when the tool schema is insufficient.\n"
        "</tool_reference>"
    )


def _budget_chars(max_context_tokens: int, ratio: float, hard_cap: int) -> int:
    """Chars available for a dynamic prompt section given the context window."""
    return max(0, min(int(max_context_tokens * CHARS_PER_TOKEN * ratio), hard_cap))


def _truncate_to_chars(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    keep = max(0, max_chars - 80)
    return text[:keep] + "\n... [content truncated to fit the token budget]"


def _build_skills_section(skills_section: str, max_context_tokens: int) -> str:
    if not skills_section:
        return ""
    capped = _truncate_to_chars(
        skills_section,
        _budget_chars(max_context_tokens, SKILLS_BUDGET_RATIO, SKILLS_MAX_CHARS),
    )
    return f"<skills>\n{capped}\n</skills>"


def build_system_prompt(
    workspace_root: str,
    mode: str = BUILD_MODE,
    skills_section: str = "",
    max_context_tokens: int = DEFAULT_CONTEXT_WINDOW,
    provider_name: str = "",
    model_name: str = "",
) -> str:
    root = str(Path(workspace_root).resolve())
    instructions = PLAN_MODE_INSTRUCTIONS if mode == PLAN_MODE else BUILD_MODE_INSTRUCTIONS
    sections: list[str] = [
        instructions,
        f"<env>\n{_build_env_section(root, mode)}\n</env>",
    ]
    sections.append(build_tool_reference_hint(root))
    skills = _build_skills_section(skills_section, max_context_tokens)
    if skills:
        sections.append(skills)
    # Gemini 3+ no longer accepts temperature/top_p/top_k sampling controls, so
    # steer output style explicitly through instructions instead of sampling.
    if is_gemini_3_plus(model_name):
        sections.append(
            "## SAMPLING STYLE\n"
            "This model does not accept temperature, top_p, or top_k controls. "
            "Produce deterministic, precise, well-structured output; let the depth "
            "and format guidance above govern tone and length rather than sampling "
            "randomness. Avoid hedging and unnecessary variation between runs."
        )
    return "\n\n".join(sections)


def build_plan_system_prompt(
    workspace_root: str,
    provider_name: str = "",
    model_name: str = "",
    max_context_tokens: int = DEFAULT_CONTEXT_WINDOW,
) -> str:
    return build_system_prompt(
        workspace_root,
        mode=PLAN_MODE,
        provider_name=provider_name,
        model_name=model_name,
        max_context_tokens=max_context_tokens,
    )


def _build_env_section(workspace_root: str, mode: str) -> str:
    os_name = platform.system()
    shell_name = "powershell" if os_name == "Windows" else "bash"
    if os_name == "Windows":
        constraint = (
            "The bash tool runs in PowerShell on Windows. Write commands only for PowerShell."
        )
    else:
        constraint = (
            "The bash tool runs in bash. Use bash syntax; never Windows PowerShell "
            "cmdlets. Write commands for bash."
        )
    # Scan workspace root for top-level directory structure
    ws = Path(workspace_root)
    top_dirs = []
    top_files = []
    try:
        for entry in sorted(ws.iterdir()):
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                top_dirs.append(entry.name + "/")
            else:
                top_files.append(entry.name)
    except OSError:
        pass
    structure_lines = []
    if top_dirs:
        structure_lines.append(f"Top-level directories: {', '.join(top_dirs[:12])}")
    if top_files:
        structure_lines.append(f"Top-level files: {', '.join(top_files[:8])}")
    structure = "\n".join(structure_lines) if structure_lines else ""
    parts = [
        f"OS: {os_name} | Shell: {shell_name} | Mode: {mode} | Dir: {workspace_root}",
        constraint,
    ]
    if structure:
        parts.append(structure)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Phase 1 additive — editable template files + tagged, composable sections.
# Mirrors opencode's editable .txt prompt templates (session/system.ts +
# ./prompt/*.txt) and codex's per-section world-state rendering.
# tier-injection removed (Mars STEP 1.6); hardcoded BUILD/PLAN_INSTRUCTIONS
# stay until Phase 3 wires consumers (01/02 prompt_sending, context) onto
# this template/section surface.
# ---------------------------------------------------------------------------

_PROMPT_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "prompts" / "templates"


@dataclass
class PromptSection:
    """A tagged, composable prompt section.

    ``tag`` names the section (rendered ``<tag>…</tag>``); ``content`` is either
    a static string or a callable resolved lazily at render time. A sentinel
    (``None``) lets callers mark a section for omission when empty.
    """

    tag: str
    content: str | Callable[[], str]
    _rendered: str | None = field(default=None, init=False, repr=False)

    def render(self) -> str:
        text = self.content() if callable(self.content) else self.content
        self._rendered = text
        return f"<{self.tag}>\n{text}\n</{self.tag}>"

    @property
    def is_empty(self) -> bool:
        if self._rendered is None:
            self.render()
        return not (self._rendered or "").strip()


def load_prompt_template(mode: str = BUILD_MODE) -> str:
    """Load an editable mode-instruction template (opencode .txt-style).

    Selection is by mode today; provider/model-specific template selection
    (opencode system.ts branches) is the Phase-2 extension point.
    """
    name = "plan.md" if mode == PLAN_MODE else "build.md"
    return (_PROMPT_TEMPLATES_DIR / name).read_text(encoding="utf-8").strip()


def default_template_sections(
    mode: str = BUILD_MODE,
    workspace_root: str = ".",
    skills_section: str = "",
    max_context_tokens: int = DEFAULT_CONTEXT_WINDOW,
) -> list[PromptSection]:
    """Compose the tagged, source-controlled prompt sections.

    This is the additive "clean" composition that Phase 3 adopts once the
    hardcoded instruction constants and tier-enhancement injection are removed:
    instructions come from the editable template file, then env / tool-reference /
    skills sections, composed independently per tag.
    """
    root = str(Path(workspace_root).resolve())
    sections = [
        PromptSection("instructions", load_prompt_template(mode=mode)),
        PromptSection("env", lambda: _build_env_section(root, mode)),
        PromptSection("tool_reference", lambda: build_tool_reference_hint(root)),
    ]
    skills = _build_skills_section(skills_section, max_context_tokens)
    if skills:
        sections.append(PromptSection("skills", skills))
    else:
        sections.append(PromptSection("skills", ""))
    return sections


def compose_system_context(sections: list[PromptSection]) -> list[str]:
    """Render sections, omitting empty ones, into the assembled context parts."""
    return [s.render() for s in sections if not s.is_empty]
