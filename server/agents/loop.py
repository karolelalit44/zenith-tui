"""Agent loop — multi-step prompt → LLM → tool calls → response."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable

from server.config.settings import AGENT_MODES, AppSettings
from server.domain.domain import FinishReason
from server.domain.errors import ZenithError
from server.domain.events import Event, EventKind
from server.domain.message import Message
from server.providers import responder as r
from server.providers.base import BaseProvider
from server.providers.parser import UnifiedResponseFormatter
from server.toolkit.param_normalizer import normalize_file_params
from server.toolkit.registry import ToolRegistry

from .context import ContextManager, _adaptive_reserve, _get_model_context_window
from .compaction import CHARS_PER_TOKEN, compact_tool_output, head_tail_trim
from .llm_stream import StreamState, stream_with_retries
from .loop_detection import LoopDetector
from .prompts import build_plan_system_prompt, build_system_prompt
from ..toolkit.executor import (
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

# pi-style compaction: when summarizing, keep this many most-recent messages
# verbatim and only summarize the older prefix (never cut at a tool result).
COMPACTION_KEEP_TAIL = 8


def _find_compaction_cut(history, keep_tail: int = COMPACTION_KEEP_TAIL) -> int:
    """Return the split index for compaction: summarize history[:cut] verbatim-keep history[cut:].

    Backs the cut up to a non-assistant boundary so a tool-result exchange
    (assistant tool call + tool result) is never split across the boundary.
    0 means "summarize everything".
    """
    if len(history) <= keep_tail:
        return 0
    cut = len(history) - keep_tail
    while cut > 0 and history[cut - 1].role == "assistant":
        cut -= 1
    return cut


def _group_start(history, i: int) -> int:
    """Start index of the exchange group ending at `i` (exclusive).

    An exchange is an assistant tool call plus all of its tool results; the
    group is the atomic unit for a compaction cut so results are never
    separated from their call.
    """
    j = i - 1
    if history[j].role == "tool":
        while j > 0 and history[j - 1].role == "tool":
            j -= 1
        if j > 0 and history[j - 1].role == "assistant":
            j -= 1
    return j


def _find_compaction_cut_budgeted(history, keep_tokens: int, count_fn) -> int:
    """Token-budgeted compaction cut (P2.8): keep the newest exchanges verbatim
    up to `keep_tokens`, snapped to turn boundaries.

    The newest exchange is always kept whole, even when it alone exceeds the
    budget (opencode splitTurn — a mid-turn compaction never summarizes away
    the live turn). Returns 0 when the whole history fits (summarize all).
    """
    if not history:
        return 0
    i = len(history)
    j = _group_start(history, i)
    used = sum(count_fn(m.content) for m in history[j:i])
    i = j
    while i > 0:
        j = _group_start(history, i)
        group_tokens = sum(count_fn(m.content) for m in history[j:i])
        if used + group_tokens > keep_tokens:
            break
        used += group_tokens
        i = j
    return i


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
        repo_map: str | None = None,
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
                confirm_callback, plan_context, sequence, repo_map,
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
        repo_map: str | None = None,
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
                model_name=model,
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
                model_name=model,
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

        messages = self.context_manager.build_messages(history, system_prompt, prompt, model, summary=self._summary, plan_block=plan_context, use_system_prompt=model_use_system_prompt, repo_map=repo_map)
        base_len = len(messages)
        logger.info("Context built: %d messages, system_prompt=%d chars", len(messages), len(system_prompt))
        yield r.thinking(f"Processing your request in {mode} mode...", session_id)

        if self.context_manager.should_summarize(messages, model, self.provider):
            async for ev in self._maybe_summarize(history, session_id, messages):
                yield ev
            messages = self._rebuild_messages(messages, base_len, history, system_prompt, prompt, model, plan_context, model_use_system_prompt, repo_map)

        if self.is_cancelled(sequence):
            yield r.warning("Request was cancelled before starting", session_id)
            return

        messages = self._apply_prompt_caching(messages)
        logger.info("=== PROMPT READY FOR LLM session=%s mode=%s messages=%d ===", session_id, mode, len(messages))
        for i, msg in enumerate(messages):
            role = msg.get("role", "?")
            content = str(msg.get("content", ""))
            logger.info("--- MSG [%d] role=%s (len=%d) ---\n%s", i, role, len(content), content)

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
                token_info = self.context_manager.get_token_info(messages, model, self.provider)
                if token_info.percent > 0.85:
                    logger.warning("Context window %.1f%% full — summarizing", token_info.percent * 100)
                    yield r.warning("Context approaching limit, summarizing...", session_id, extra={"tokenInfo": {"used": token_info.used, "remaining": token_info.remaining, "total": token_info.total, "percent": token_info.percent}})
                    async for ev in self._maybe_summarize(history, session_id, messages):
                        yield ev
                    messages = self._rebuild_messages(messages, base_len, history, system_prompt, prompt, model, plan_context, model_use_system_prompt, repo_map)
                    token_info = self.context_manager.get_token_info(messages, model, self.provider)
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
                    async for ev in self._maybe_summarize(history, session_id, messages):
                        yield ev
                    messages = self._rebuild_messages(messages, base_len, history, system_prompt, prompt, model, plan_context, model_use_system_prompt, repo_map)
                    token_info = self.context_manager.get_token_info(messages, model, self.provider)
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
                        from server.toolkit.command_safety import assess_command
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
                    _ti = self.context_manager.get_token_info(messages, model, self.provider)
                    _remaining = _ti.total - _ti.used
                    _threshold = 20000 if _ti.total >= 200000 else int(_ti.total * 0.2)
                    if _remaining <= _threshold and _remaining > 0:
                        yield r.warning(f"Context approaching limit ({_ti.percent:.0f}%), summarizing...", session_id, extra={"tokenInfo": vars(_ti)})
                        async for _ev in self._maybe_summarize(history, session_id, messages):
                            yield _ev
                        messages = self._rebuild_messages(messages, base_len, history, system_prompt, prompt, model, plan_context, model_use_system_prompt, repo_map)
                        _ti2 = self.context_manager.get_token_info(messages, model, self.provider)
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
                    result_limit = min(dynamic_max, configured_max)
                    _compacted, cstats = compact_tool_output(result.output or "", max_output=result_limit)
                    if cstats.chars_removed > 0:
                        yield r.context_compacted(
                            tool_name, cstats.chars_removed, cstats.tokens_saved,
                            cstats.reason, session_id,
                            original_chars=cstats.original_chars,
                            compacted_chars=cstats.compacted_chars,
                        )
                    messages.append({"role": "user", "content": format_tool_result(tool_name, result, result_limit)})
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

        token_info = self.context_manager.get_token_info(messages, model, self.provider)
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

    async def _maybe_summarize(self, history, session_id, messages=None, reason="automatic"):
        from server.agents.summarizer import ConversationSummarizer
        model = self.provider.model
        token_info = self.context_manager.get_token_info(messages or [], model, self.provider) if messages else None
        used = token_info.used if token_info else 0
        total = token_info.total if token_info else 0
        yield r.context_compaction_started(session_id, reason, used, total)
        yield r.warning("Context approaching limit, summarizing...", session_id)
        try:
            # Cheap reclaim first: truncate old tool outputs before spending a
            # full summarization pass (opencode reclaim-before-compaction).
            if messages:
                pruned = self._prune_tool_outputs(messages)
                if pruned["count"]:
                    yield r.context_compacted(
                        "context", pruned["chars_removed"], pruned["tokens_saved"],
                        f"pruned {pruned['count']} old tool result(s)", session_id,
                    )
            ctx = min(_get_model_context_window(model), self.config.max_context_tokens)
            reserve = _adaptive_reserve(model, ctx)
            keep_tokens = max(8000, min(20000, int(max(0, ctx - reserve) * 0.25)))
            cut = _find_compaction_cut_budgeted(
                history, keep_tokens,
                lambda m: self.context_manager.count_tokens(getattr(m, 'content', str(m)), model),
            )
            target = history[:cut] if cut > 0 else history
            self._summary = await ConversationSummarizer(self.config, self.provider).summarize(
                target, model, session_id=session_id, previous_summary=self._summary,
            )
            tokens_saved = 0
            if messages:
                target_tokens = sum(self.context_manager.count_tokens(getattr(m, 'content', str(m)), model) for m in target)
                tokens_saved = max(0, target_tokens - self.context_manager.count_tokens(self._summary, model))
            yield r.context_compaction_ended(session_id, reason, used, total, tokens_saved=tokens_saved, summary_chars=len(self._summary))
            yield r.warning("Context summarized", session_id)
        except Exception as e:
            yield r.warning(f"Summarization failed: {e}", session_id)

    def _prune_tool_outputs(
        self,
        messages: list[dict],
        keep_turns: int = 2,
        max_output: int = 2000,
    ) -> dict:
        """Compact old tool-result messages in place to reclaim context cheaply.

        Walks the message list backward, protects the last `keep_turns` user
        turns, and truncates older `[Tool: ...]` result messages to
        `max_output` chars (keeping the tool-name/status header and the
        output tail). Returns aggregate stats for a CONTEXT_COMPACTED event.
        """
        stats: dict = {"count": 0, "chars_removed": 0, "tokens_saved": 0}
        if not messages:
            return stats
        turns = 0
        boundary = 0
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                turns += 1
                if turns > keep_turns:
                    boundary = i + 1
                    break
        for msg in messages[:boundary]:
            content = msg.get("content", "")
            if not isinstance(content, str) or not content.startswith("[Tool:"):
                continue
            if msg.get("time") == "compacted":
                continue
            lines = content.split("\n", 1)
            head = lines[0]
            rest = lines[1] if len(lines) > 1 else ""
            if len(rest) <= max_output:
                continue
            compacted_rest, _ = head_tail_trim(rest, max_output)
            msg["content"] = head + "\n" + compacted_rest
            msg["time"] = "compacted"
            stats["count"] += 1
            stats["chars_removed"] += len(rest) - len(compacted_rest)
            stats["tokens_saved"] += (len(rest) - len(compacted_rest)) // CHARS_PER_TOKEN
        return stats

    def _rebuild_messages(
        self,
        messages: list[dict],
        base_len: int,
        history: list[Message],
        system_prompt: str,
        prompt: str,
        model: str,
        plan_context: str,
        use_system_prompt: bool,
        repo_map: str | None,
    ) -> list[dict]:
        """Rebuild the message list after compaction, replaying the live turn.

        Persisted history holds only user/assistant turns; the tool traffic
        that accumulated in `messages` since the initial build (`base_len`)
        would be silently dropped by a plain rebuild. Re-append that live turn
        so mid-turn compaction never forces the model to re-run its tools, and
        add an explicit continuation nudge (opencode overflow-replay pattern).
        """
        live_tail = messages[base_len:]
        rebuilt = self.context_manager.build_messages(
            history, system_prompt, prompt, model,
            summary=self._summary, plan_block=plan_context,
            use_system_prompt=use_system_prompt, repo_map=repo_map,
        )
        if live_tail:
            rebuilt.extend(live_tail)
            rebuilt.append({
                "role": "user",
                "content": "Continue if you have next steps, or stop and ask for clarification for how to proceed.",
            })
            logger.info("Replayed live turn after compaction: %d messages", len(live_tail))
        return rebuilt

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
        # Stable prefix: mark the first system messages (system prompt + repo
        # map) so the cached prefix is reused verbatim on the next turn.
        for i in range(min(2, len(cached))):
            cached[i]["cache_control"] = {"type": "ephemeral"}
        # Volatile tail: mark the last message so the turn that immediately
        # follows can re-use the whole prefix (opencode-style).
        if len(cached) >= 1:
            cached[-1]["cache_control"] = {"type": "ephemeral"}
        return cached


from ..toolkit.executor import format_tool_result as _format_tool_result  # noqa: F401, E402
