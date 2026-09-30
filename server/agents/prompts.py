from __future__ import annotations

import datetime
import logging
import platform
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from server.config.constants import (
    BUILD_MODE,
    PLAN_MODE,
)
from server.prompts import BUILD_MODE_PROMPT, PLAN_MODE_PROMPT

logger = logging.getLogger(__name__)


def build_tool_reference_hint() -> str:
    return (
        "Tool schemas in this request are authoritative and complete for the tools "
        "active this turn; prefer them over any description of a tool you remember. "
        "Call get_tool_definition('<tool_name>') for a tool's full parameter schema and "
        "usage guidelines, and discover_capabilities() to list tools not currently offered."
    )


def _build_web_research_guidelines() -> str:
    return (
        "Guidelines for Web Tools (websearch, webfetch):\n"
        "1. The >10% Temporal Instability Rule: Whenever you are about to make an assertion "
        "about a topic where there is greater than a 10% probability that facts, APIs, package "
        "versions, deprecations, or features have evolved since model training cutoff, web search "
        "is MANDATORY before answering or writing code.\n"
        "2. Mandatory Search Categories: Current package versions and syntax (include current year "
        "in queries), active GitHub issues, PRs, breaking changes, CVE security advisories, and cloud "
        "API documentation.\n"
        "3. When NOT to Search: Never search the web for local workspace code or files (use grep, "
        "glob, file_read instead). Never search for stable language fundamentals.\n"
        "4. Escalation Ladder: Use websearch to discover sources, webfetch to read a specific URL. "
        "For large documents, use webfetch with start_line and end_line or pattern (find_in_page) "
        "to inspect targeted windows rather than dumping full pages. To download or save files "
        "(PDFs, images, audio, video, archives, datasets, or any web resource) directly to the workspace, "
        "invoke webfetch with download_path.\n"
        "5. Citation Formatting: Every factual statement derived from the web must include an "
        "inline citation [descriptive title](url) placed immediately after the punctuation of the "
        "sentence it supports. Never place citations inside code blocks or dump bare URLs.\n"
        "6. Copyright & Fair Use: Quote no more than 25 words verbatim from any single source; "
        "synthesize and summarize in your own words."
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
    now = datetime.datetime.now(datetime.UTC)
    date_str = now.strftime("%Y-%m-%d")
    year_str = str(now.year)
    return (
        f"OS: {os_name} | Shell: {shell_name} | Mode: {mode} | Dir: {workspace_root}\n"
        f"Current Date: {date_str} | Current Year: {year_str}\n"
        f"{constraint}"
    )


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


def _build_file_operation_guidelines() -> str:
    """Tell the model which tool covers which file operation.

    Codex states its editing constraints in the system prompt, on the theory
    that a stated rule and a guard reinforce each other. Zenith enforces far
    more of it at the tool layer — the shell tool refuses `cat`, `grep`, `ls`,
    `sed -i`, and now `mv`/`cp`/`rm`/`stat` — but a refusal teaches the rule only
    after the model has spent a turn being told off. Naming the coverage up
    front means the first attempt is the right one.

    The coverage table is the point. Every operation a model might reach for
    through a shell is listed against the tool that handles it, so there is no
    remaining gap for the shell to be the obvious answer to.
    """
    return (
        "File operations: use the dedicated tools, not the shell.\n"
        "The bash tool refuses shell equivalents of the operations below, so a "
        "shell command for any of them is a wasted turn.\n"
        "\n"
        "  inspect metadata (size, lines, type, content hash)  file_stat(path=...)\n"
        "  read a file                                   file_read(path, offset, limit)\n"
        "  read a symbol list without reading             file_read(path, outline=true)\n"
        "  search file contents with surrounding lines    grep(pattern, path, include, context=N)\n"
        "  find files by name                             glob(pattern, path)\n"
        "  list one directory                             list_dir(path)\n"
        "  create a file                                  file_write(path, content)\n"
        "  replace a file's whole content                 file_write(path, content, mode='overwrite')\n"
        "  append to a file                               file_write(path, content, mode='append')\n"
        "  replace text you can quote exactly             file_edit(path, old_content, new_content)\n"
        "  replace a region you cannot quote exactly      file_edit(path, start_line, end_line, new_content)\n"
        "  multi-file / multi-hunk changes                apply_patch\n"
        "  move or rename a file                          file_move(path, to)\n"
        "  copy a file                                   file_copy(path, to)\n"
        "  delete a file or directory                     file_delete(path)\n"
        "\n"
        "Editing rules:\n"
        "1. Always use apply_patch for manual code edits. Do not use cat, sed, tee, "
        "python -c, or any other command to create or edit a file. Formatting "
        "commands and bulk generated changes are the exception.\n"
        "2. Do not re-read a file after editing it to check the edit landed. Every "
        "mutating tool returns a receipt saying what changed, on which lines, and "
        "which match rule fired. Re-reading wastes a turn and a large amount of "
        "context.\n"
        "3. A not-found or ambiguous error is meant to be acted on: the message "
        "carries the near-miss alternatives or the range that must be made unique. "
        "Use it rather than retrying the same call.\n"
        "4. If a file may have changed since you read it, pass its expected_sha256 "
        "(from file_stat) to the mutating tool. The write is then refused if it "
        "drifted, instead of landing on content you did not review.\n"
        "5. Use bash for what only a shell can do: running tests, linters, builds, "
        "package managers, and version control."
    )


def load_prompt_template(mode: str = BUILD_MODE) -> str:
    """Return the mode prompt template (memory-backed, zero disk I/O)."""
    return PLAN_MODE_PROMPT if mode == PLAN_MODE else BUILD_MODE_PROMPT


def default_template_sections(
    mode: str = BUILD_MODE,
    workspace_root: str = ".",
) -> list[PromptSection]:
    """Compose the tagged, source-controlled prompt sections.

    Tool-to-operation coverage lives once, in ``file_operations``. It used to
    also appear as a bullet list of parameter signatures inside the mode template
    and again as a prose mapping in one of its invariants — three restatements of
    what the JSON schemas in the same request already say exactly, paid on every
    request of every turn. What stays is what the schemas cannot carry: which
    operation to use when, why the shell refuses it, and how to fetch the rest.
    """
    root = str(Path(workspace_root).resolve())
    return [
        PromptSection("instructions", load_prompt_template(mode=mode)),
        PromptSection("env", lambda: _build_env_section(root, mode)),
        PromptSection("file_operations", _build_file_operation_guidelines),
        PromptSection("web_research", _build_web_research_guidelines),
        PromptSection("tool_reference", build_tool_reference_hint),
    ]


def compose_system_context(sections: list[PromptSection]) -> list[str]:
    """Render sections, omitting empty ones, into the assembled context parts."""
    return [s.render() for s in sections if not s.is_empty]


def build_system_prompt(workspace_root: str, mode: str = BUILD_MODE) -> str:
    return "\n\n".join(compose_system_context(default_template_sections(mode=mode, workspace_root=workspace_root)))


def build_plan_system_prompt(workspace_root: str) -> str:
    return build_system_prompt(workspace_root, mode=PLAN_MODE)


BUILD_MODE_INSTRUCTIONS = load_prompt_template(BUILD_MODE)
PLAN_MODE_INSTRUCTIONS = load_prompt_template(PLAN_MODE)
