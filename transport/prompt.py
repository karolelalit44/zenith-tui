"""Prompt execution — runs agent loop and persists results."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from core.events import Event, EventKind
from core.message import Message
from agent.recovery import RecoverableAgentLoop
from agent.context import ContextManager

if TYPE_CHECKING:
    from config.settings import AppSettings
    from providers.base import BaseProvider
    from tools.registry import ToolRegistry
    from db.repository import SessionRepository, MessageRepository
    from skills.loader import SkillLoader
    from transport.handlers import MethodHandlers

logger = logging.getLogger(__name__)


class PromptExecutor:
    """Runs the agent loop for a prompt and persists the result."""

    def __init__(
        self,
        config: AppSettings,
        provider: BaseProvider,
        tool_registry: ToolRegistry,
        session_repo: SessionRepository,
        message_repo: MessageRepository,
        skill_loader: SkillLoader,
    ) -> None:
        self._config = config
        self._provider = provider
        self._tool_registry = tool_registry
        self._session_repo = session_repo
        self._message_repo = message_repo
        self._skill_loader = skill_loader
        self._active_task: asyncio.Task | None = None

    def cancel_active(self) -> None:
        if self._active_task and not self._active_task.done():
            self._active_task.cancel()

    def run(self, session_id: str, content: str, mode: str = "build", handlers: MethodHandlers | None = None, manager=None) -> None:
        self._active_task = asyncio.create_task(
            self._execute(session_id, content, mode, handlers, manager)
        )

    async def _execute(
        self,
        session_id: str,
        content: str,
        mode: str,
        handlers: MethodHandlers | None,
        manager,
    ) -> None:
        logger.info("_execute START session=%s mode=%s", session_id, mode)
        collected_events: list[Event] = []
        response_text = ""

        try:
            history = await self._message_repo.get_by_session(session_id)
            context_manager = ContextManager(self._config)
            agent = RecoverableAgentLoop(self._config, self._provider, context_manager, self._tool_registry)
            skills_section = self._skill_loader.get_skill_prompt()

            async def _confirm(tool_name: str, reason: str, risk_level: str) -> bool:
                if handlers and manager:
                    return await handlers.request_confirmation(session_id, tool_name, reason, risk_level, manager)
                return True

            async for event in agent.process_prompt(
                content, session_id, history, mode,
                skills_section=skills_section, confirm_callback=_confirm,
            ):
                collected_events.append(event)
                if manager:
                    await manager.send_event(session_id, event)
                if event.kind == EventKind.MESSAGE and not event.data.get("partial"):
                    response_text += event.data.get("text", "")
        except Exception as e:
            logger.exception("PromptExecutor._execute failed for session %s", session_id)
            error_event = Event(kind=EventKind.ERROR, data={"message": str(e)}, session_id=session_id)
            if manager:
                await manager.send_event(session_id, error_event)
            collected_events.append(error_event)

        try:
            assistant_msg = Message(session_id=session_id, role="assistant", content=response_text, events=collected_events)
            await self._message_repo.create(assistant_msg)
        except Exception:
            logger.exception("Failed to persist assistant message for session %s", session_id)
