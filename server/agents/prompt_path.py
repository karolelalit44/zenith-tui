"""Additive single prompt path for prompt_sending (module 02).

Phase 1 additive core for the prompt-sending redesign. Provides:

- ``resolve_user_parts(content, attachments, workspace_root)`` — resolves each
  attachment (file, folder, inline, agent, MCP resource) into a tagged user
  part *at prompt time*, mirroring opencode's ``resolveUserPart`` and codex's
  ``ResponseItem`` multipart model. This is the capability the redesign
  identified as missing today.
- ``PromptPath`` — a single clean forward path: resolve parts, assemble the
  user message, and stream one LLM turn through ``SimpleLoop`` (module 01).
  No captain/crewmate/default delegation branching — exactly one path, per
  ``agent_engine_redesign/prompt_sending/feature.md``.
- ``build_clean_system_context(...)`` — the additive "clean" system-prompt
  assembly built on module 15's tagged ``PromptSection`` surface (opencode
  ``.txt`` templates + codex world-state sections), ready for Phase-3 adoption.

Additive only: the legacy ``PromptExecutor``/``AgentLoop`` 3-way delegation
branch is left intact so the harness and TUI keep working; removal is Phase 3.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from pathlib import Path

from server.config.constants import ATTACHMENT_MAX_TOTAL, BUILD_MODE
from server.config.settings import AppSettings
from server.domain.events import Event
from server.domain.message import Message
from server.providers.base import BaseProvider
from server.toolkit.registry import ToolRegistry

from .context import ContextManager
from .prompt_executor import _format_folder_tree, list_attachment, read_attachment
from .prompts import compose_system_context, default_template_sections
from .simple_loop import SimpleLoop

logger = logging.getLogger(__name__)


async def resolve_user_parts(
    content: str, attachments: list[dict] | None, workspace_root: str | Path
) -> tuple[str, list[dict]]:
    """Resolve text + attachments into a single tagged user message at prompt time.

    Mirrors opencode's ``resolveUserPart``: each attachment becomes a tagged
    part. File attachments are embedded as text; folder attachments become a
    bounded scope/tree reference; inline content is used as-is; agent and MCP
    parts are wrapped with a directive telling the model to act on them.

    Returns ``(combined_content, parts)`` where ``parts`` is the list of
    resolved ``{type, path, ...}`` dicts for recording/telemetry.
    """
    blocks: list[str] = []
    parts: list[dict] = []
    total = 0
    if content:
        blocks.append(f"<user>\n{content}\n</user>")
        parts.append({"type": "text"})

    for att in attachments or []:
        kind = att.get("kind", "file") if isinstance(att, dict) else "file"
        path = att.get("path", "") if isinstance(att, dict) else ""
        inline = att.get("content") if isinstance(att, dict) else None

        if isinstance(inline, str) and inline.strip():
            text = inline
            parts.append({"type": kind, "path": path, "resolved": "inline"})
        elif kind == "folder":
            data, error = await list_attachment(path, workspace_root)
            if error:
                blocks.append(f'<attachment path="{path}" kind="{kind}" error="{error}" />')
                parts.append({"type": kind, "path": path, "resolved": False, "error": error})
                continue
            tree = _format_folder_tree(data or {}, path)
            text = f"Folder scope: {path}\n{tree}"
            parts.append(
                {
                    "type": kind,
                    "path": path,
                    "resolved": True,
                    "entries": (data or {}).get("entries", 0),
                }
            )
        elif kind == "agent":
            text = (
                f"The user asks to delegate to agent '{path}'. Use the task tool to invoke "
                f"that agent on the objective, and incorporate its result here."
            )
            parts.append({"type": "agent", "path": path, "resolved": True})
        elif kind == "mcp":
            text = f"The user referenced an MCP resource: {path}. Read the resource and include its content."
            parts.append({"type": "mcp", "path": path, "resolved": True})
        else:
            read_text, error = await read_attachment(path, workspace_root)
            if error:
                blocks.append(f'<attachment path="{path}" kind="{kind}" error="{error}" />')
                parts.append({"type": kind, "path": path, "resolved": False, "error": error})
                continue
            text = read_text if isinstance(read_text, str) else ""
            parts.append({"type": kind, "path": path, "resolved": True})

        size = len(text.encode("utf-8"))
        total += size
        if total > ATTACHMENT_MAX_TOTAL:
            blocks.append(
                f'<attachment path="{path}" kind="{kind}" error="total attachment size exceeds {ATTACHMENT_MAX_TOTAL} bytes" />'
            )
            continue
        blocks.append(f'<attachment path="{path}" kind="{kind}">\n{text}\n</attachment>')

    return "\n\n".join(blocks) if blocks else content, parts


def build_clean_system_context(
    mode: str = BUILD_MODE,
    workspace_root: str = ".",
    skills_section: str = "",
    max_context_tokens: int = 0,
) -> list[str]:
    """Assemble the clean, tagged system context (module 15 surface).

    Wraps ``default_template_sections`` + ``compose_system_context`` so prompt-
    sending can consume the editable-template/tagged-section design at runtime.
    Returns rendered section parts.
    """
    from server.config.constants import DEFAULT_CONTEXT_WINDOW

    sections = default_template_sections(
        mode=mode,
        workspace_root=workspace_root,
        skills_section=skills_section,
        max_context_tokens=max_context_tokens or DEFAULT_CONTEXT_WINDOW,
    )
    return compose_system_context(sections)


class PromptPath:
    """Single, airline-free prompt path: parts -> SimpleLoop.

    Explicitly a single path (feature doc): no captain/crewmate/default
    delegation branching. This is the additive replacement surface that Phase 3
    wires into the API handler once the legacy executor is retired.
    """

    def __init__(
        self,
        config: AppSettings,
        provider: BaseProvider,
        tool_registry: ToolRegistry,
        context_manager: ContextManager | None = None,
    ) -> None:
        self.config = config
        self.provider = provider
        self.tool_registry = tool_registry
        self.context_manager = context_manager or ContextManager(config)
        self.loop = SimpleLoop(
            config,
            provider,
            context_manager=self.context_manager,
            tool_registry=tool_registry,
        )

    async def send(
        self,
        content: str,
        session_id: str,
        history: list[Message] | None = None,
        mode: str = BUILD_MODE,
        skills_section: str = "",
        plan_context: str = "",
        model_override: str | None = None,
        repo_map: str | None = None,
        attachments: list[dict] | None = None,
    ) -> AsyncIterator[Event]:
        """Resolve parts and stream one LLM turn through ``SimpleLoop``."""
        resolved, parts = await resolve_user_parts(content, attachments, self.config.workspace_root)
        if parts:
            logger.info("Resolved %d prompt part(s) for session %s", len(parts), session_id)

        async for event in self.loop.process_prompt(
            resolved,
            session_id,
            history or [],
            mode,
            skills_section=skills_section,
            plan_context=plan_context,
            model_override=model_override,
            repo_map=repo_map,
        ):
            yield event
