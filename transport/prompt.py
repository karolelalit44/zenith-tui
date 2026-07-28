"""Prompt execution — runs agent loop and persists results."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING

from core.events import Event, EventKind
from core.message import Message
from core.domain import SessionState
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
        import functools
        self._active_task = asyncio.create_task(
            self._execute(session_id, content, mode, handlers, manager)
        )
        self._active_task.add_done_callback(
            functools.partial(self._on_task_done, session_id)
        )

    def _on_task_done(self, session_id: str, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            logger.error(
                "BACKGROUND TASK FAILED session=%s error=%s",
                session_id, exc, exc_info=exc,
            )

    async def _execute(
        self,
        session_id: str,
        content: str,
        mode: str,
        handlers: MethodHandlers | None,
        manager,
    ) -> None:
        logger.info("=" * 60)
        logger.info("_execute START session=%s mode=%s prompt=%r", session_id, mode, content[:200])
        collected_events: list[Event] = []
        response_text = ""
        event_count = 0

        try:
            history = await self._message_repo.get_by_session(session_id)
            logger.info("History loaded: %d messages for session %s", len(history), session_id)

            # Load plan context if in build mode
            plan_context = ""
            if mode == "build":
                try:
                    session = await self._session_repo.get(session_id)
                    if session and session.plan_output:
                        plan_context = session.plan_output
                        logger.info("Plan context loaded: %d chars for build session %s", len(plan_context), session_id)
                except Exception:
                    logger.warning("Failed to load plan context for session %s", session_id)

            context_manager = ContextManager(self._config)
            agent = RecoverableAgentLoop(self._config, self._provider, context_manager, self._tool_registry)
            skills_section = self._skill_loader.get_skill_prompt()
            logger.info("Agent initialized, skills loaded=%d chars", len(skills_section))

            async def _confirm(tool_name: str, reason: str, risk_level: str) -> bool:
                logger.info("Confirmation requested: tool=%s reason=%s risk=%s", tool_name, reason, risk_level)
                if handlers and manager:
                    result = await handlers.request_confirmation(session_id, tool_name, reason, risk_level, manager)
                    logger.info("Confirmation result: %s for tool=%s", result, tool_name)
                    return result
                return True

            async for event in agent.process_prompt(
                content, session_id, history, mode,
                skills_section=skills_section, confirm_callback=_confirm,
                plan_context=plan_context,
            ):
                event_count += 1
                collected_events.append(event)
                if event.kind == EventKind.MESSAGE:
                    pass
                elif event.kind == EventKind.THINKING:
                    logger.info("  THINKING: %s", event.data.get("text", "")[:200])
                elif event.kind == EventKind.TOOL_CALL:
                    logger.info("  TOOL_CALL: tool=%s params=%s",
                                event.data.get("tool", ""), str(event.data.get("params", {}))[:200])
                elif event.kind == EventKind.TOOL_RESULT:
                    logger.info("  TOOL_RESULT: tool=%s success=%s output_len=%d error=%s",
                                event.data.get("tool", ""),
                                event.data.get("success"),
                                len(event.data.get("output", "")),
                                event.data.get("error", "")[:100])
                elif event.kind == EventKind.ERROR:
                    logger.info("  ERROR: message=%s code=%s recoverable=%s",
                                event.data.get("message", ""), event.data.get("code"),
                                event.data.get("recoverable"))
                elif event.kind == EventKind.SUCCESS:
                    logger.info("  SUCCESS: iterations=%s token_info=%s",
                                event.data.get("iterations"), event.data.get("tokenInfo"))
                elif event.kind == EventKind.WARNING:
                    logger.info("  WARNING: %s", event.data.get("message", "")[:200])
                else:
                    logger.info("  OTHER: %s", str(event.data)[:200])

                if manager:
                    await manager.send_event(session_id, event)
                if event.kind == EventKind.MESSAGE and not event.data.get("partial"):
                    response_text += event.data.get("text", "")

            # Save plan output to session if in plan mode
            if mode == "plan" and response_text:
                try:
                    session = await self._session_repo.get(session_id)
                    if session:
                        session.plan_output = response_text
                        session.plan_approved_at = datetime.now()
                        session.state = SessionState.SUMMARIZED
                        await self._session_repo.update(session)
                        logger.info("Plan output saved to session %s: %d chars", session_id, len(response_text))
                except Exception:
                    logger.warning("Failed to save plan output for session %s", session_id)

            logger.info("=" * 60)
            logger.info("_execute COMPLETE: events=%d response_text_len=%d", event_count, len(response_text))
        except Exception as e:
            logger.exception("PromptExecutor._execute FAILED for session %s after %d events", session_id, event_count)
            error_event = Event(kind=EventKind.ERROR, data={"message": str(e)}, session_id=session_id)
            if manager:
                await manager.send_event(session_id, error_event)
            collected_events.append(error_event)

        try:
            assistant_msg = Message(session_id=session_id, role="assistant", content=response_text, events=collected_events)
            await self._message_repo.create(assistant_msg)
            logger.info("Assistant message persisted: %d events, %d chars", len(collected_events), len(response_text))
        except Exception:
            logger.exception("Failed to persist assistant message for session %s", session_id)
