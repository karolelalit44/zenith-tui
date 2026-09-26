from __future__ import annotations

import datetime
import logging
import platform
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from server.config.constants import (
    BUILD_MODE,
    DEFAULT_CONTEXT_WINDOW,
    PLAN_MODE,
)
from server.prompts import BUILD_MODE_PROMPT, PLAN_MODE_PROMPT

logger = logging.getLogger(__name__)


def build_tool_reference_hint(workspace_root: str = "") -> str:
    return (
        "A lean set of tool schemas is active this turn for direct use; the full capability "
        "catalog is available on demand. "
        "Call get_tool_definition('<tool_name>') for a tool's full parameter schema and usage "
        "guidelines, and discover_capabilities() to list all available tools."
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
        "to inspect targeted windows rather than dumping full pages.\n"
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
    now = datetime.datetime.now(datetime.timezone.utc)
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


def load_prompt_template(mode: str = BUILD_MODE) -> str:
    """Return the mode prompt template (memory-backed, zero disk I/O)."""
    return PLAN_MODE_PROMPT if mode == PLAN_MODE else BUILD_MODE_PROMPT


def default_template_sections(
    mode: str = BUILD_MODE,
    workspace_root: str = ".",
    max_context_tokens: int = DEFAULT_CONTEXT_WINDOW,
) -> list[PromptSection]:
    """Compose the tagged, source-controlled prompt sections."""
    root = str(Path(workspace_root).resolve())
    return [
        PromptSection("instructions", load_prompt_template(mode=mode)),
        PromptSection("env", lambda: _build_env_section(root, mode)),
        PromptSection("web_research", _build_web_research_guidelines),
        PromptSection("tool_reference", lambda: build_tool_reference_hint(root)),
    ]


def compose_system_context(sections: list[PromptSection]) -> list[str]:
    """Render sections, omitting empty ones, into the assembled context parts."""
    return [s.render() for s in sections if not s.is_empty]


def build_system_prompt(
    workspace_root: str,
    mode: str = BUILD_MODE,
    max_context_tokens: int = DEFAULT_CONTEXT_WINDOW,
    provider_name: str = "",
    model_name: str = "",
) -> str:
    sections = default_template_sections(
        mode=mode,
        workspace_root=workspace_root,
        max_context_tokens=max_context_tokens,
    )
    return "\n\n".join(compose_system_context(sections))


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


BUILD_MODE_INSTRUCTIONS = load_prompt_template(BUILD_MODE)
PLAN_MODE_INSTRUCTIONS = load_prompt_template(PLAN_MODE)
