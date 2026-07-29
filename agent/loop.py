"""Agent loop — multi-step prompt → LLM → tool calls → response."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable

from config.settings import AGENT_MODES, AppSettings
from core.domain import FinishReason
from core.errors import ZenithError
from core.events import Event, EventKind
from core.message import Message
from providers import responder as r
from providers.base import BaseProvider
from providers.parser import UnifiedResponseFormatter
from tools.param_normalizer import normalize_file_params
from tools.registry import ToolRegistry

from .context import ContextManager, _get_model_context_window
from .llm_stream import StreamState, stream_with_retries
from .loop_detection import LoopDetector
from .prompts import build_plan_system_prompt, build_system_prompt
from .tool_executor import (
    _dynamic_max_output,
    auto_commit,
    build_tool_metadata,
    execute_tool,
    format_tool_result,
    post_execution_hooks,
    validate_tool_calls,
    validate_tool_rejection,
)
from .validation import (
    _COMPLETION_SIGNALS as COMPLETION_SIGNALS,
)
from .validation import (
    reflection_error_limit,
    schemas_to_openai_tools,
)

logger = logging.getLogger(__name__)


class AgentLoop:
    """Core agent loop: prompt → context build → LLM stream → tool calls → repeat."""

    def __init__(
        self,
        config: AppSettings,
        provider: BaseProvider,
        context_manager: ContextManager | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self.config = config
        self.provider = provider
        self.context_manager = context_manager or ContextManager(config)
        self.tool_registry = tool_registry
        self._summary: str | None = None
        self._loop_detector = LoopDetector()
        self._accept_sequence: int = 0
        self._cancel_sequence: int = -1

    def accept(self) -> int:
        self._accept_sequence += 1
        return self._accept_sequence

    def cancel(self) -> None:
        self._cancel_sequence = self._accept_sequence

    def is_cancelled(self, sequence: int) -> bool:
        return self._cancel_sequence >= sequence

    @property
    def summary(self) -> str | None:
        return self._summary

    def set_summary(self, summary: str | None) -> None:
        self._summary = summary

    async def process_prompt(
        self,
        prompt: str,
        session_id: str,
        history: list[Message],
        mode: str = "build",
        skills_section: str = "",
        confirm_callback: Callable[[str, str, str], Awaitable[bool]] | None = None,
        plan_context: str = "",
        model_override: str | None = None,
    ) -> AsyncIterator[Event]:
        sequence = self.accept()

        # Model override per mode (Aider-style --editor-model / --architect-model)
        _original_model = self.provider.model
        if model_override and model_override != self.provider.model:
            logger.info("Mode model override: %s → %s", self.provider.model, model_override)
            self.provider.model = model_override
        try:
            async for ev in self._process_prompt_impl(
                prompt, session_id, history, mode, skills_section,
                confirm_callback, plan_context, sequence,
            ):
                yield ev
        finally:
            if model_override and model_override != _original_model:
                self.provider.model = _original_model

    async def _process_prompt_impl(
        self,
        prompt: str,
        session_id: str,
        history: list[Message],
        mode: str = "build",
        skills_section: str = "",
        confirm_callback: Callable[[str, str, str], Awaitable[bool]] | None = None,
        plan_context: str = "",
        sequence: int = 0,
    ) -> AsyncIterator[Event]:
        provider_name = getattr(self.provider, 'name', '')
        model = self.provider.model
        ws = self.config.workspace_root
        mode_config = AGENT_MODES.get(mode)

        # --- Mode-specific prompt and tool selection (Crush-style config-driven agents) ---
        if mode == "plan":
            logger.info("PLAN MODE: using focused plan prompt, read-only tools")
            # Plan mode: minimal prompt, no skills, no tool schemas
            system_prompt = build_plan_system_prompt(
                self.config.workspace_root,
                provider_name=provider_name,
            )
            # Plan mode: only read-only tools (file_read, glob, grep, bash)
            if self.tool_registry and mode_config and mode_config.allowed_tools:
                plan_tool_names = self.tool_registry.list_tools_for_mode(
                    "plan", allowed_mcp=mode_config.allowed_mcp,
                )
                registered_tools = set(plan_tool_names)
                plan_schemas = self.tool_registry.get_schemas_for_mode(
                    "plan", allowed_mcp=mode_config.allowed_mcp,
                )
                openai_tools = schemas_to_openai_tools(plan_schemas)
                logger.info("Plan mode tools: %s", sorted(registered_tools))
            else:
                registered_tools = set()
                openai_tools = []
        else:
            # Build mode: full prompt, all tools
            allowed_mcp = mode_config.allowed_mcp if mode_config else None
            all_tool_schemas = self.tool_registry.get_schemas_for_mode(
                "build", allowed_mcp=allowed_mcp,
            ) if self.tool_registry else []
            all_tool_names = {s["name"] for s in all_tool_schemas}
            system_prompt = build_system_prompt(
                self.config.workspace_root, mode, all_tool_schemas,
                skills_section=skills_section,
                max_context_tokens=self.config.max_context_tokens,
                provider_name=provider_name,
            )
            registered_tools = all_tool_names
            openai_tools = schemas_to_openai_tools(all_tool_schemas)

        model_use_system_prompt = True

        if not model_use_system_prompt:
            logger.info("Model '%s' does not support system prompt — merging into user message", model)

        # Dynamic reflection error limit based on model context window
        _reflimit = reflection_error_limit(_get_model_context_window(model))

        # Safety net — dynamic stopping is the primary mechanism
        SAFETY_NET_MAX_ITERATIONS = 100

        messages = self.context_manager.build_messages(history, system_prompt, prompt, model, summary=self._summary, plan_block=plan_context, use_system_prompt=model_use_system_prompt)
        logger.info("Context built: %d messages, system_prompt=%d chars", len(messages), len(system_prompt))
        yield r.thinking(f"Processing your request in {mode} mode...", session_id)

        if self.context_manager.should_summarize(messages, model):
            async for ev in self._maybe_summarize(history, session_id):
                yield ev
            messages = self.context_manager.build_messages(history, system_prompt, prompt, model, summary=self._summary, plan_block=plan_context, use_system_prompt=model_use_system_prompt)

        if self.is_cancelled(sequence):
            yield r.warning("Request was cancelled before starting", session_id)
            return

        messages = self._apply_prompt_caching(messages)
        logger.info("Messages ready for LLM: %d messages", len(messages))
        for i, msg in enumerate(messages):
            role = msg.get("role", "?")
            content = msg.get("content", "")
            logger.info("  msg[%d] role=%s content_len=%d preview=%r", i, role, len(str(content)), str(content)[:150])

        iteration = 0
        reflection_errors = 0
        created_files: set[str] = set()
        task_completed = False
        post_comp_iterations = 0
        files_edited: list[str] = []
        _total_completion_chars = 0

        try:
            while iteration < SAFETY_NET_MAX_ITERATIONS:
                if self.is_cancelled(sequence):
                    yield r.warning("Request cancelled", session_id)
                    return
                if task_completed and post_comp_iterations >= 2:
                    break

                iteration += 1
                if task_completed:
                    post_comp_iterations += 1

                # --- Dynamic stop: context window exhaustion ---
                token_info = self.context_manager.get_token_info(messages, model)
                if token_info.percent > 0.85:
                    logger.warning("Context window %.1f%% full — summarizing", token_info.percent * 100)
                    yield r.warning("Context approaching limit, summarizing...", session_id, extra={"tokenInfo": {"used": token_info.used, "remaining": token_info.remaining, "total": token_info.total, "percent": token_info.percent}})
                    async for ev in self._maybe_summarize(history, session_id):
                        yield ev
                    messages = self.context_manager.build_messages(history, system_prompt, prompt, model, summary=self._summary, plan_block=plan_context, use_system_prompt=model_use_system_prompt)
                    token_info = self.context_manager.get_token_info(messages, model)
                    if token_info.percent > 0.95:
                        yield r.error("Context window exhausted even after summarization", session_id, code="CONTEXT_EXHAUSTED")
                        return

                logger.info("Agent turn %d (dynamic stop) session=%s tokens=%.1f%%", iteration, session_id, token_info.percent * 100)

                stream_state = StreamState()
                finish_reason = FinishReason.STOP
                context_exceeded = False
                try:
                    _tool_choice = mode_config.tool_choice if mode_config else "auto"
                    async for event in stream_with_retries(
                        self.provider, messages, openai_tools, session_id, iteration, stream_state,
                        tool_choice=_tool_choice,
                    ):
                        if event.kind == EventKind.WARNING and event.data.get("context_exceeded"):
                            context_exceeded = True
                        yield event
                except ZenithError:
                    return

                # Handle runtime context exceeded — summarize and retry
                if context_exceeded:
                    logger.info("Context exceeded at runtime — summarizing")
                    yield r.warning("Context window exceeded, summarizing and retrying...", session_id)
                    async for ev in self._maybe_summarize(history, session_id):
                        yield ev
                    messages = self.context_manager.build_messages(history, system_prompt, prompt, model, summary=self._summary, plan_block=plan_context, use_system_prompt=model_use_system_prompt)
                    token_info = self.context_manager.get_token_info(messages, model)
                    if token_info.percent > 0.95:
                        yield r.error("Context window exhausted even after summarization", session_id, code="CONTEXT_EXHAUSTED")
                        return
                    continue

                # Check if stream completed due to length truncation
                finish_reason = getattr(self.provider, '_last_finish_reason', FinishReason.STOP)

                response_text = stream_state.response_text
                _total_completion_chars += len(response_text)
                native_tool_calls = getattr(self.provider, '_last_native_tool_calls', [])
                clean_response, tool_calls = UnifiedResponseFormatter.process_response(response_text, native_tool_calls or None)
                logger.info("Agent turn %d response: %d chars, %d tool calls, clean=%d chars finish=%s",
                            iteration, len(response_text), len(tool_calls), len(clean_response or ""), finish_reason)
                if clean_response:
                    yield r.message_event(clean_response, session_id, partial=False, iteration=iteration)

                if finish_reason == FinishReason.LENGTH:
                    logger.info("FinishReason=LENGTH on turn %d — continuing response", iteration)
                    if iteration >= SAFETY_NET_MAX_ITERATIONS * 2:
                        yield r.error("Response length limit exceeded repeatedly", session_id, code="LENGTH_EXCEEDED")
                        return
                    continue

                if not tool_calls:
                    if not clean_response and not stream_state.full_response:
                        yield r.error("Model returned empty response.", session_id, code="EMPTY_RESPONSE", recoverable=True)
                    if mode == "build" and not created_files:
                        yield r.warning("Model returned no tool calls in build mode — no files will be created.", session_id)
                    break

                if not self.tool_registry:
                    yield r.error("No tool registry available", session_id)
                    break

                valid_calls, invalid_names = validate_tool_calls(tool_calls, registered_tools)
                if invalid_names:
                    yield r.warning(f"Hallucinated tools ignored: {', '.join(invalid_names)}", session_id)
                if not valid_calls:
                    msgs = [{"role": "assistant", "content": response_text or "[tool calls]"}, {"role": "user", "content": f"Tool calls for non-existent tools: {', '.join(invalid_names)}. Available: {', '.join(sorted(registered_tools))}."}]
                    messages.extend(msgs)
                    continue

                messages.append({"role": "assistant", "content": response_text or "[tool calls]"})

                stop_turn = False
                for tc in valid_calls:
                    tool_name = tc["tool"]
                    tool_params = normalize_file_params(tc.get("params", {}))

                    # Pre-execution validation
                    reject_msg = validate_tool_rejection(tool_name, tool_params, created_files, ws)
                    if tool_name in ("bash", "terminal") and not reject_msg and confirm_callback:
                        from tools.command_safety import assess_command
                        assessment = assess_command(tool_params.get("command", ""))
                        if assessment.is_risky:
                            try:
                                approved = await confirm_callback(tool_name, assessment.reason, assessment.risk_level)
                            except Exception:
                                approved = False
                            if not approved:
                                reject_msg = f"Command denied: {tool_params.get('command', '')} ({assessment.reason})"

                    if reject_msg:
                        yield r.warning(f"Tool '{tool_name}' rejected: {reject_msg}", session_id)
                        messages.append({"role": "user", "content": f"[Tool rejected] {reject_msg}"})
                        reflection_errors += 1
                        if reflection_errors >= _reflimit:
                            yield r.error(f"Too many errors ({reflection_errors}).", session_id, code="REFLECTION_LIMIT", recoverable=True)
                            return
                        continue

                    yield r.tool_call(tool_name, tool_params, session_id)
                    result, duration_ms = await execute_tool(
                        self.tool_registry, tool_name, tool_params, ws, mode,
                        allowed_mcp=mode_config.allowed_mcp if mode_config else None,
                    )
                    yield r.tool_result(tool_name, result.success, session_id,
                        output=result.output or "", error=result.error or "",
                        metadata=build_tool_metadata(tool_name, tool_params, result, duration_ms))

                    # --- Dynamic stop: tool requested turn end ---
                    if result.stop_turn:
                        logger.info("Tool '%s' requested stop_turn", tool_name)
                        stop_turn = True

                    if not result.success:
                        reflection_errors += 1
                        err_msg = result.error or f"Tool '{tool_name}' execution failed"
                        messages.append({"role": "user", "content": f"[Tool error] {tool_name} failed: {err_msg}. Try a different approach."})
                        if reflection_errors >= _reflimit:
                            yield r.error(f"Too many errors ({reflection_errors}).", session_id, code="REFLECTION_LIMIT", recoverable=True)
                            return

                    # StopWhen-style context check after each step (Crush pattern)
                    _ti = self.context_manager.get_token_info(messages, model)
                    _remaining = _ti.total - _ti.used
                    _threshold = 20000 if _ti.total >= 200000 else int(_ti.total * 0.2)
                    if _remaining <= _threshold and _remaining > 0:
                        yield r.warning(f"Context approaching limit ({_ti.percent:.0f}%), summarizing...", session_id, extra={"tokenInfo": vars(_ti)})
                        async for _ev in self._maybe_summarize(history, session_id):
                            yield _ev
                        messages = self.context_manager.build_messages(history, system_prompt, prompt, model, summary=self._summary, plan_block=plan_context, use_system_prompt=model_use_system_prompt)
                        _ti2 = self.context_manager.get_token_info(messages, model)
                        if _ti2.percent > 0.95:
                            yield r.error(f"Context exhausted ({_ti2.percent:.0f}%)", session_id, code="CONTEXT_EXHAUSTED", recoverable=True)
                            return
                        yield r.warning("Context summarized, continuing", session_id)

                    # Track created files + edited files
                    if result.success:
                        p = tool_params.get("filepath") or tool_params.get("path") or ""
                        if p:
                            if tool_name == "file_write":
                                created_files.add(p)
                            if tool_name in ("file_edit", "file_write"):
                                files_edited.append(p)

                    for ev in await post_execution_hooks(tool_name, tool_params, result, ws, session_id):
                        yield ev

                    model_ctx = _get_model_context_window(model)
                    dynamic_max = _dynamic_max_output(model_ctx)
                    configured_max = self.config.tools.max_tool_output
                    messages.append({"role": "user", "content": format_tool_result(tool_name, result, min(dynamic_max, configured_max))})
                    self._loop_detector.record(tool_name, tool_params, messages[-1]["content"])

                # --- Dynamic stop conditions (checked after each full tool-call batch) ---

                # 1. Tool requested turn end
                if stop_turn:
                    logger.info("Stopping turn: tool requested stop_turn")
                    break

                # 2. Loop detection (Crush-style SHA-256 signature matching)
                if self._loop_detector.is_loop_detected():
                    yield r.error("Loop detected: the same tool calls are repeating without progress.", session_id, code="LOOP_DETECTED", recoverable=True)
                    return

                # 3. Task completion signal
                if not task_completed and clean_response and COMPLETION_SIGNALS.search(clean_response):
                    task_completed = True

                if files_edited:
                    auto_commit(ws, files_edited)
                    files_edited.clear()
            else:
                yield r.error(f"Safety net exceeded ({SAFETY_NET_MAX_ITERATIONS} iterations)", session_id, code="MAX_ITERATIONS")
                return
        finally:
            pass

        token_info = self.context_manager.get_token_info(messages, model)
        prompt_tokens = token_info.used
        estimated_completion = max(1, _total_completion_chars // 4)
        cum_usage: dict = getattr(self.provider, '_cumulative_usage', {})
        is_estimated = cum_usage.get("total_tokens", 0) == 0
        if mode == "build" and not created_files:
            yield r.warning("Build completed but no files were created. The model output text instead of using file_write.", session_id, code="NO_FILES_CREATED")
        yield r.success("Request processed successfully", session_id, iteration, {
            "used": token_info.used, "remaining": token_info.remaining,
            "total": token_info.total, "percent": round(token_info.percent, 3),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": estimated_completion,
            "cached_tokens": cum_usage.get("cached_tokens", 0),
            "cache_creation_tokens": cum_usage.get("cache_creation_tokens", 0),
            "estimated": is_estimated,
            "mode": mode,
        })

    async def _maybe_summarize(self, history, session_id):
        from session.history import HistoryManager
        yield r.warning("Context approaching limit, summarizing...", session_id)
        try:
            history_mgr = HistoryManager(self.config, self.provider)
            self._summary = await history_mgr.summarize(history, self.provider.model)
            yield r.warning("Context summarized", session_id)
        except Exception as e:
            yield r.warning(f"Summarization failed: {e}", session_id)

    def _get_tool_schemas(self) -> list[dict]:
        return self.tool_registry.get_schemas() if self.tool_registry else []

    def _get_tool_names(self) -> list[str]:
        return self.tool_registry.list_tools() if self.tool_registry else []

    def _apply_prompt_caching(self, messages: list[dict]) -> list[dict]:
        if not messages:
            return messages
        if 'anthropic' not in getattr(self.provider, 'name', '').lower():
            return messages
        cached = [dict(msg) for msg in messages]
        if cached:
            cached[0]["cache_control"] = {"type": "ephemeral"}
        if len(cached) >= 2:
            cached[-1]["cache_control"] = {"type": "ephemeral"}
            cached[-2]["cache_control"] = {"type": "ephemeral"}
        return cached


from .tool_executor import format_tool_result as _format_tool_result  # noqa: F401, E402
