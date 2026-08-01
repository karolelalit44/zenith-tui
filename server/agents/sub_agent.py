"""Sub-agent — Aider-style fresh agent instance for plan→build handoff.

When build mode is configured with sub_agent=True, the plan output is
passed to a brand-new AgentLoop + ContextManager instead of being prepended
to the existing conversation. This gives the sub-agent a clean context window,
independent tool budget, and isolated state.

Design (Aider-inspired):
  ArchitectCoder.reply_completed()
    → Coder.create(edit_format="editor-diff", with_message=architect_plan)
    → EditorCoder.run()  # fresh instance, own message history
    → carries back costs + commit hashes

SubAgentLoop:
    → fresh RecoverableAgentLoop  (no summary, no loop detector state)
    → fresh ContextManager        (separate token budget)
    → plan is passed as the first user message
    → runs independently, yields events to caller
    → child session created, linked to parent
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable

from config.settings import AGENT_MODES, AppSettings
from core.domain import SessionState
from core.events import Event, EventKind
from core.message import Message
from providers.base import BaseProvider
from tools.registry import ToolRegistry

from .context import ContextManager
from .recovery import RecoverableAgentLoop

logger = logging.getLogger(__name__)


class SubAgentLoop:
    """Aider-style sub-agent with a fresh AgentLoop + ContextManager.

    Creates a child session, passes the plan as input, runs the agent
    independently, and links costs/summary back to the parent.
    """

    def __init__(
        self,
        config: AppSettings,
        provider: BaseProvider,
        tool_registry: ToolRegistry,
    ) -> None:
        self.config = config
        self.provider = provider
        self.tool_registry = tool_registry

    async def run(
        self,
        session_id: str,
        plan_output: str,
        user_prompt: str,
        confirm_callback: Callable | None = None,
        session_repo=None,
        message_repo=None,
    ) -> AsyncIterator[Event]:
        """Run the sub-agent with the given plan as its input.

        Yields events just like the main agent loop, including the final
        SUCCESS event with token usage.
        """
        # 1. Create child session (clean slate for the sub-agent)
        child_session_id = await self._create_child_session(session_id, session_repo)

        # 2. Fresh context manager — separate token budget from parent
        context_manager = ContextManager(self.config)

        # 3. Fresh agent loop — no summary, no loop detector state
        agent = RecoverableAgentLoop(
            self.config, self.provider, context_manager, self.tool_registry,
        )

        # 4. Build input: plan is the first user message, followed by user prompt
        if user_prompt and user_prompt.strip():
            sub_prompt = (
                f"Implement this plan:\n\n{plan_output}\n\n"
                f"User request: {user_prompt}"
            )
        else:
            sub_prompt = f"Implement this plan:\n\n{plan_output}"

        # 5. Run agent — clean history (empty list), plan as prompt
        mode_config = AGENT_MODES.get("build")
        model_override = (mode_config.model_override
                          if mode_config and mode_config.model_override
                          else None)

        response_text = ""
        metrics = {}

        async for event in agent.process_prompt(
            prompt=sub_prompt,
            session_id=child_session_id,
            history=[],
            mode="build",
            confirm_callback=confirm_callback,
            plan_context="",
            model_override=model_override,
        ):
            if event.kind == EventKind.MESSAGE and not event.data.get("partial"):
                response_text += event.data.get("text", "")
            if event.kind == EventKind.SUCCESS:
                metrics = event.data
            yield event

        # 6. Persist sub-agent output
        if message_repo and response_text:
            try:
                assistant_msg = Message(
                    session_id=child_session_id,
                    role="assistant",
                    content=response_text,
                )
                await message_repo.create(assistant_msg)
                logger.info(
                    "Sub-agent message persisted: session=%s %d chars",
                    child_session_id, len(response_text),
                )
            except Exception:
                logger.exception("Failed to persist sub-agent message")

        # 7. Link costs to parent session via token repo
        if session_repo and metrics:
            try:
                parent = await session_repo.get(session_id)
                if parent:
                    parent.total_tokens += metrics.get("used", 0)
                    parent.message_count += 1
                    await session_repo.update(parent)
            except Exception:
                logger.warning("Failed to update parent token totals")

    async def _create_child_session(self, parent_id: str, session_repo=None) -> str:
        """Create a child session linked to the parent. Returns child session id."""
        if not session_repo:
            import uuid
            return str(uuid.uuid4())

        try:
            parent = await session_repo.get(parent_id)
            if not parent:
                import uuid
                return str(uuid.uuid4())

            from core.session import Session
            child = Session(
                title=f"sub-agent-{parent.title}",
                mode=parent.mode,
                parent_session_id=parent_id,
                workspace_root=parent.workspace_root,
                state=SessionState.CREATED,
                provider=parent.provider,
                model=parent.model,
            )
            child.transition(SessionState.ACTIVE)
            created = await session_repo.create(child)

            # Link parent → child
            parent.add_child(created.id)
            await session_repo.update(parent)

            logger.info(
                "Created child session %s → %s for sub-agent",
                parent_id, created.id,
            )
            return created.id
        except Exception as e:
            logger.warning("Failed to create child session: %s", e)
            import uuid
            return str(uuid.uuid4())
