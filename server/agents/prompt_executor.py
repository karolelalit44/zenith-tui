"""Prompt execution — runs agent loop and persists results.

Supports two execution paths:
1. Standard path: AgentLoop with optional plan_context prepended to messages.
2. Sub-agent path (Aider-style): Spawns a fresh AgentLoop + ContextManager
   when build mode has an approved plan and sub_agent=True. The plan becomes
   the sub-agent's first user message; the main loop does not run this turn.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING

import server.providers.responder as r
from server.agents.context import ContextManager
from server.agents.recovery import RecoverableAgentLoop
from server.agents.sub_agent import SubAgentLoop
from server.config.settings import AGENT_MODES
from server.domain.domain import SessionState
from server.domain.events import Event, EventKind
from server.domain.message import Message
from server.persistence.repositories import TokenUsageRepository

if TYPE_CHECKING:
    from server.config.settings import AppSettings
    from server.persistence.repositories import MessageRepository, SessionRepository
    from server.providers.base import BaseProvider
    from server.skills.loader import SkillLoader
    from server.toolkit.registry import ToolRegistry
    from server.api.handlers import MethodHandlers

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
        # One ContextManager per executor (long-lived per session) so the repo
        # map / memory caches survive across turns instead of being rebuilt and
        # re-injected (and re-billed) on every prompt.
        self._context_manager = ContextManager(self._config)

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
        logger.info("_execute START session=%s mode=%s prompt=%r", session_id, mode, content)

        collected_events: list[Event] = []
        response_text = ""
        event_count = 0
        token_usage_recorded = False
        _step_count = 0

        try:
            history = await self._message_repo.get_by_session(session_id)
            logger.info("History loaded: %d messages for session %s", len(history), session_id)

            # Load plan context if in build mode
            plan_context = ""
            plan_approved = False
            if mode == "build":
                try:
                    session = await self._session_repo.get(session_id)
                    if session and session.plan_output:
                        plan_context = session.plan_output
                        plan_approved = session.plan_approved_at is not None
                        logger.info("Plan context loaded: %d chars for build session %s (approved=%s)",
                                    len(plan_context), session_id, plan_approved)
                except Exception:
                    logger.warning("Failed to load plan context for session %s", session_id)

            # Determine model override per mode (Aider-style --editor-model)
            plan_model_override: str | None = None
            if mode == "plan" and self._config.plan_model:
                plan_model_override = self._config.plan_model
                logger.info("Plan mode model override: %s", plan_model_override)

            if mode == "build" and plan_context and not plan_approved and not self._config.auto_approve_plan:
                logger.info("Plan not yet approved — emitting PLAN_READY for session %s", session_id)
                plan_ready_event = Event(kind=EventKind.PLAN_READY, data={
                    "plan": plan_context,
                    "session_id": session_id,
                }, session_id=session_id)
                if manager:
                    await manager.send_event(session_id, plan_ready_event)
                collected_events.append(plan_ready_event)
                logger.info("Plan not approved — waiting for approval before build")
                _step_count += 1
                warning_event = r.warning("Plan is pending approval. Approve in the UI or use plan.approve to continue.", session_id)
                if manager:
                    await manager.send_event(session_id, warning_event)
                collected_events.append(warning_event)
                return

            async def _confirm(tool_name: str, reason: str, risk_level: str) -> bool:
                logger.info("Confirmation requested: tool=%s reason=%s risk=%s", tool_name, reason, risk_level)
                if handlers and manager:
                    result = await handlers.request_confirmation(session_id, tool_name, reason, risk_level, manager)
                    logger.info("Confirmation result: %s for tool=%s", result, tool_name)
                    return result
                return True

            # Aider-style sub-agent: fresh AgentLoop for plan→build handoff
            mode_config = AGENT_MODES.get(mode)
            if mode == "build" and plan_context and plan_approved and mode_config and mode_config.sub_agent:
                logger.info("Spawning SubAgentLoop for session %s (plan→build handoff)", session_id)
                sub_agent = SubAgentLoop(self._config, self._provider, self._tool_registry)
                async for event in sub_agent.run(
                    session_id=session_id,
                    plan_output=plan_context,
                    user_prompt=content,
                    confirm_callback=_confirm,
                    session_repo=self._session_repo,
                    message_repo=self._message_repo,
                ):
                    event_count += 1
                    collected_events.append(event)
                    if manager:
                        await manager.send_event(session_id, event)
                logger.info("SubAgentLoop completed for session %s: %d events", session_id, event_count)
                return  # Sub-agent handled this turn

            context_manager = self._context_manager
            agent = RecoverableAgentLoop(self._config, self._provider, context_manager, self._tool_registry)
            skills_section = self._skill_loader.get_skill_prompt()
            logger.info("Agent initialized, skills loaded=%d chars", len(skills_section))

            token_repo = TokenUsageRepository(self._session_repo.db)
            budget_check = await token_repo.get_budget_status(session_id)
            if budget_check.get("active") and budget_check.get("max_monthly_cost", 0) > 0:
                monthly = budget_check.get("monthly_cost", 0)
                max_monthly = budget_check.get("max_monthly_cost", 0)
                if monthly >= max_monthly:
                    if manager:
                        await manager.send_event(session_id, r.error(f"Monthly budget ${max_monthly:.2f} exhausted (${monthly:.2f} used)", session_id, code="BUDGET_EXCEEDED"))
                    return
                if monthly / max_monthly > 0.8:
                    if manager:
                        await manager.send_event(session_id, r.warning(f"Monthly budget at {monthly / max_monthly * 100:.0f}% (${monthly:.2f}/${max_monthly:.2f})", session_id))

            async for event in agent.process_prompt(
                content, session_id, history, mode,
                skills_section=skills_section, confirm_callback=_confirm,
                plan_context=plan_context,
                model_override=plan_model_override,
                # Aider-style: architect/plan mode uses no repo map (map_tokens=0)
                # so the planning model spends its window on the plan, not the map.
                repo_map="" if mode == "plan" else None,
            ):
                event_count += 1
                collected_events.append(event)
                if event.kind == EventKind.MESSAGE:
                    if not event.data.get("partial"):
                        if event.data.get("iteration"):
                            _step_count += 1
                        logger.info("  [ASSISTANT MESSAGE]: %s", event.data.get("text", ""))
                elif event.kind == EventKind.THINKING:
                    logger.info("  [THINKING]: %s", event.data.get("text", ""))
                elif event.kind == EventKind.TOOL_CALL:
                    logger.info("  [TOOL CALL]: tool=%s params=%s",
                                event.data.get("tool", ""), str(event.data.get("params", {})))
                elif event.kind == EventKind.TOOL_RESULT:
                    out = str(event.data.get("output", ""))
                    logger.info("  [TOOL RESULT]: tool=%s success=%s output_len=%d error=%s\n%s",
                                event.data.get("tool", ""),
                                event.data.get("success"),
                                len(out),
                                event.data.get("error", ""),
                                out)

                elif event.kind == EventKind.ERROR:
                    logger.info("  ERROR: message=%s code=%s recoverable=%s",
                                event.data.get("message", ""), event.data.get("code"),
                                event.data.get("recoverable"))
                    if event.data.get("code") == "CONTEXT_EXHAUSTED":
                        try:
                            await token_repo.record_degradation(
                                session_id=session_id,
                                step_index=_step_count,
                                before_tokens=0,
                                after_tokens=0,
                                reason="context_exhausted",
                            )
                        except Exception:
                            pass
                elif event.kind == EventKind.SUCCESS:
                    logger.info("  SUCCESS: iterations=%s token_info=%s",
                                event.data.get("iterations"), event.data.get("tokenInfo"))
                    if event.data.get("tokenInfo"):
                        try:
                            ti = event.data["tokenInfo"]
                            token_repo = TokenUsageRepository(self._session_repo.db)
                            provider_name = getattr(self._provider, 'name', 'unknown')
                            model_name = getattr(self._provider, 'model', 'unknown')
                            used = ti.get("used", 0)
                            prompt_t = ti.get("prompt_tokens", used)
                            completion_t = ti.get("completion_tokens", 0)
                            cache_read_t = ti.get("cached_tokens", 0)
                            cache_creation_t = ti.get("cache_creation_tokens", 0)
                            ctx_window = ti.get("total", 128000)
                            estimated = bool(ti.get("estimated", False))

                            if _step_count > 0:
                                for s in range(1, _step_count + 1):
                                    await token_repo.record(
                                        session_id=session_id,
                                        provider=provider_name,
                                        model=model_name,
                                        total_tokens=used // _step_count,
                                        context_window=ctx_window,
                                        prompt_tokens=prompt_t // _step_count,
                                        completion_tokens=completion_t // _step_count,
                                        input_tokens=prompt_t // _step_count,
                                        output_tokens=completion_t // _step_count,
                                        cache_read_tokens=cache_read_t // _step_count,
                                        cache_creation_tokens=cache_creation_t // _step_count,
                                        step_index=s,
                                        estimated=estimated,
                                    )
                            elif not token_usage_recorded:
                                await token_repo.record(
                                    session_id=session_id,
                                    provider=provider_name,
                                    model=model_name,
                                    total_tokens=used,
                                    context_window=ctx_window,
                                    prompt_tokens=prompt_t,
                                    completion_tokens=completion_t,
                                    input_tokens=prompt_t,
                                    output_tokens=completion_t,
                                    cache_read_tokens=cache_read_t,
                                    cache_creation_tokens=cache_creation_t,
                                    estimated=estimated,
                                )
                            token_usage_recorded = True
                            logger.info("Token usage recorded: provider=%s model=%s tokens=%d/%d cache_read=%d cache_creation=%d",
                                        provider_name, model_name, used, ctx_window, cache_read_t, cache_creation_t)
                            # Update session total_tokens counter
                            try:
                                await self._session_repo.add_tokens(session_id, used)
                            except Exception as e:
                                logger.warning("Failed to update session token count: %s", e)
                        except Exception as e:
                            logger.warning("Failed to record token usage: %s", e)
                elif event.kind == EventKind.WARNING:
                    msg = event.data.get("message", "")
                    logger.info("  WARNING: %s", msg[:200])
                    if "Context" in msg and ("approaching" in msg or "summarizing" in msg or "exhausted" in msg):
                        try:
                            deg_ti = event.data.get("tokenInfo") or {}
                            await token_repo.record_degradation(
                                session_id=session_id,
                                step_index=_step_count,
                                before_tokens=deg_ti.get("used", 0),
                                after_tokens=deg_ti.get("remaining", 0),
                                reason=msg[:100],
                            )
                        except Exception as e:
                            logger.warning("Failed to record degradation: %s", e)
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
                        # auto_approve_plan: skip user confirmation (Aider-style --auto-accept-architect)
                        if self._config.auto_approve_plan:
                            session.plan_approved_at = datetime.now()
                        else:
                            session.plan_approved_at = None  # Wait for user approval
                        session.state = SessionState.SUMMARIZED
                        await self._session_repo.update(session)
                        logger.info("Plan output saved to session %s: %d chars (auto_approve=%s)",
                                    session_id, len(response_text), self._config.auto_approve_plan)
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
            if collected_events or response_text:
                text_content = response_text or "[Cancelled by user]"
                assistant_msg = Message(session_id=session_id, role="assistant", content=text_content, events=collected_events)
                await self._message_repo.create(assistant_msg)
                logger.info("Assistant message persisted: %d events, %d chars", len(collected_events), len(text_content))
            else:
                logger.info("Skipping empty assistant message (no events or text)")
        except Exception:
            logger.exception("Failed to persist assistant message for session %s", session_id)
