from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

from server.config.constants import (
    BUILD_MODE,
    CONTEXT_SUMMARY_THRESHOLD,
    FILE_DELETE_TOOL,
    FILE_OVERWRITE_PARAM,
    FILE_WRITE_TOOL,
    GET_TOOL_DEFINITION_TOOL,
    PLAN_MODE,
)
from server.config.settings import AGENT_MODES, AppSettings
from server.domain.domain import FinishReason
from server.domain.errors import ZenithError
from server.domain.events import Event, EventKind
from server.domain.message import Message
from server.providers import responder as r
from server.providers.base import BaseProvider
from server.providers.parser import UnifiedResponseFormatter
from server.toolkit.param_normalizer import normalize_file_params
from server.toolkit.path_validator import validate_path
from server.toolkit.registry import ToolRegistry
from server.toolkit.resolver import SchemaResolver, build_mode_tool_seed

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
from .compaction import CHARS_PER_TOKEN, compact_tool_output, head_tail_trim
from .context import ContextManager, _adaptive_reserve, _get_model_context_window
from .llm_stream import StreamState, stream_with_retries
from .loop_detection import LoopDetector
from .prompts import build_plan_system_prompt, build_system_prompt
from .validation import reflection_error_limit, schemas_to_openai_tools

_format_tool_result = format_tool_result
logger = logging.getLogger(__name__)
COMPACTION_KEEP_TAIL = 8
# Cap how many repeated calls the "skipped calls" warning/message lists so it
# can't grow unboundedly across a pathological re-emission loop.
_SKIP_WARNING_CAP = 6


def _call_signature(tool_name: str, params: dict) -> tuple[str, str]:
    """Canonical signature for an executed tool call (tool + normalized params)."""
    return (
        tool_name,
        json.dumps(params, sort_keys=True, separators=(",", ":"), default=str),
    )


def _params_label(params: dict) -> str:
    """Short human-readable label for a call's params."""
    if not params:
        return ""
    if "tool_name" in params:
        return str(params["tool_name"])
    # Prefer an identifying param so multi-arg calls (file_write(path,
    # content)) render as file_write(path=...) instead of an ambiguous
    # file_write(). This keeps the "skipped calls" warning readable.
    for key in ("path", "pattern", "query", "url", "command", "task"):
        if key in params and params[key]:
            value = params[key]
            if isinstance(value, str) and len(value) > 48:
                value = value[:48] + "…"
            return f"{key}={value}"
    if len(params) == 1:
        key, value = next(iter(params.items()))
        return f"{key}={value}"
    return ""


def _all_calls_repeat(valid_calls: list[dict], executed: set[tuple[str, str]]) -> bool:
    """True when every requested call was already executed this turn with identical params."""
    if not valid_calls or not executed:
        return False
    return all(
        _call_signature(tc["tool"], normalize_file_params(tc.get("params", {}), tc["tool"])) in executed
        for tc in valid_calls
    )


def _find_compaction_cut(history, keep_tail: int = COMPACTION_KEEP_TAIL) -> int:
    if len(history) <= keep_tail:
        return 0
    cut = len(history) - keep_tail
    while cut > 0 and history[cut - 1].role == "assistant":
        cut -= 1
    return cut


def _group_start(history, i: int) -> int:
    j = i - 1
    if history[j].role == "tool":
        while j > 0 and history[j - 1].role == "tool":
            j -= 1
        if j > 0 and history[j - 1].role == "assistant":
            j -= 1
    return j


def _find_compaction_cut_budgeted(history, keep_tokens: int, count_fn) -> int:
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
        # Last full message text yielded this request; used to suppress duplicate
        # final answers when the model re-emits the same closing text across turns.
        self._last_emitted_message: str | None = None

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

    def _resolve_safety_iterations(self, model: str) -> int:
        ctx = _get_model_context_window(model)
        return max(10, min(ctx // 2000, 150))

    async def process_prompt(
        self,
        prompt: str,
        session_id: str,
        history: list[Message],
        mode: str = BUILD_MODE,
        skills_section: str = "",
        plan_context: str = "",
        model_override: str | None = None,
        repo_map: str | None = None,
    ) -> AsyncIterator[Event]:
        sequence = self.accept()
        # Reset usage accounting to this request only. Otherwise the provider's
        # _cumulative_usage carries over across prompts in the same session, so
        # the context-budget checks (usage_tokens) compare session totals against
        # a per-request window and trigger spurious "context approaching limit"
        # summarization on an otherwise small request.
        _reset_usage = getattr(self.provider, "_reset_cumulative_usage", None)
        if callable(_reset_usage):
            _reset_usage()
        self._last_emitted_message = None
        _original_model = self.provider.model
        if model_override and model_override != self.provider.model:
            logger.info("Mode model override: %s → %s", self.provider.model, model_override)
            self.provider.model = model_override
        try:
            async for ev in self._process_prompt_impl(
                prompt,
                session_id,
                history,
                mode,
                skills_section,
                plan_context,
                sequence,
                repo_map,
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
        mode: str = BUILD_MODE,
        skills_section: str = "",
        plan_context: str = "",
        sequence: int = 0,
        repo_map: str | None = None,
    ) -> AsyncIterator[Event]:
        provider_name = getattr(self.provider, "name", "")
        model = self.provider.model
        ws = self.config.workspace_root
        mode_config = AGENT_MODES.get(mode)
        allowed_mcp = mode_config.allowed_mcp if mode_config else None
        allowed_tools = mode_config.allowed_tools if mode_config else None
        resolver = SchemaResolver(self.tool_registry, seed=build_mode_tool_seed(allowed_tools))
        if mode == PLAN_MODE:
            logger.info("PLAN MODE: using focused plan prompt, read-only tools")
            system_prompt = build_plan_system_prompt(
                self.config.workspace_root, provider_name=provider_name, model_name=model
            )
            registered_tools = set(resolver.active_names())
            openai_tools = resolver.openai_tools(PLAN_MODE, allowed_mcp=allowed_mcp)
            logger.info("Plan mode tools: %s", sorted(registered_tools))
        else:
            active_schemas = resolver.schemas(BUILD_MODE, allowed_mcp=allowed_mcp)
            system_prompt = build_system_prompt(
                self.config.workspace_root,
                mode,
                active_schemas,
                skills_section=skills_section,
                max_context_tokens=self.config.max_context_tokens,
                provider_name=provider_name,
                model_name=model,
            )
            registered_tools = set(resolver.active_names())
            openai_tools = schemas_to_openai_tools(active_schemas)
        self.context_manager.set_aux_tokens(resolver.schema_tokens(model))
        model_use_system_prompt = True
        if not model_use_system_prompt:
            logger.info(
                "Model '%s' does not support system prompt — merging into user message", model
            )
        _reflimit = reflection_error_limit(_get_model_context_window(model))
        messages = self.context_manager.build_messages(
            history,
            system_prompt,
            prompt,
            model,
            summary=self._summary,
            plan_block=plan_context,
            use_system_prompt=model_use_system_prompt,
            repo_map=repo_map,
        )
        base_len = len(messages)
        logger.info(
            "Context built: %d messages, system_prompt=%d chars", len(messages), len(system_prompt)
        )
        yield r.thinking(f"Processing your request in {mode} mode...", session_id)
        if self.context_manager.should_summarize(messages, model, self.provider):
            _rebuild_holder: list = []
            async for _ev in self._summarize_and_rebuild(
                history,
                session_id,
                messages,
                result=_rebuild_holder,
                base_len=base_len,
                system_prompt=system_prompt,
                prompt=prompt,
                model=model,
                plan_context=plan_context,
                use_system_prompt=model_use_system_prompt,
                repo_map=repo_map,
            ):
                yield _ev
            messages = _rebuild_holder[0]
        if self.is_cancelled(sequence):
            yield r.warning("Request was cancelled before starting", session_id)
            return
        messages = self._apply_prompt_caching(messages)
        logger.info(
            "=== PROMPT READY FOR LLM session=%s mode=%s messages=%d ===",
            session_id,
            mode,
            len(messages),
        )
        for i, msg in enumerate(messages):
            role = msg.get("role", "?")
            content = str(msg.get("content", ""))
            logger.info("--- MSG [%d] role=%s (len=%d) ---\n%s", i, role, len(content), content)
        iteration = 0
        # REFLECTION_LIMIT counts CONSECUTIVE tool failures (no successful
        # execution between them). A scattered cosmetic failure such as
        # "directory already exists" - followed by progress - must NOT abort the
        # task; only an uninterrupted streak of failures signals a stuck model.
        consecutive_failures = 0
        created_files: set[str] = set()
        tools_used = False
        task_completed = False
        post_comp_iterations = 0
        files_edited: list[str] = []
        executed_calls: set[tuple[str, str]] = set()
        executed_results: dict[tuple[str, str], str] = {}
        failed_calls: set[tuple[str, str]] = set()
        stall_count = 0
        _total_completion_chars = 0
        try:
            safety_iterations = self._resolve_safety_iterations(model)
            while iteration < safety_iterations:
                if self.is_cancelled(sequence):
                    yield r.warning("Request cancelled", session_id)
                    return
                if task_completed and post_comp_iterations >= 1:
                    break
                iteration += 1
                if task_completed:
                    post_comp_iterations += 1
                token_info = self.context_manager.get_token_info(messages, model, self.provider)
                if token_info.percent > CONTEXT_SUMMARY_THRESHOLD:
                    logger.warning(
                        "Context window %.1f%% full — summarizing", token_info.percent * 100
                    )
                    yield r.warning(
                        "Context approaching limit, summarizing...",
                        session_id,
                        extra={
                            "tokenInfo": {
                                "used": token_info.used,
                                "remaining": token_info.remaining,
                                "total": token_info.total,
                                "percent": token_info.percent,
                            }
                        },
                    )
                    _rebuild_holder: list = []
                    async for ev in self._summarize_and_rebuild(
                        history,
                        session_id,
                        messages,
                        result=_rebuild_holder,
                        base_len=base_len,
                        system_prompt=system_prompt,
                        prompt=prompt,
                        model=model,
                        plan_context=plan_context,
                        use_system_prompt=model_use_system_prompt,
                        repo_map=repo_map,
                    ):
                        yield ev
                    messages = _rebuild_holder[0]
                    token_info = self.context_manager.get_token_info(messages, model, self.provider)
                    if token_info.percent > 0.95:
                        yield r.error(
                            "Context window exhausted even after summarization",
                            session_id,
                            code="CONTEXT_EXHAUSTED",
                        )
                        return
                logger.info(
                    "Agent turn %d (dynamic stop) session=%s tokens=%.1f%%",
                    iteration,
                    session_id,
                    token_info.percent * 100,
                )
                stream_state = StreamState()
                finish_reason = FinishReason.STOP
                context_exceeded = False
                # Tools are always offered. The old heuristic that withheld tools
                # on iteration 1 when a prompt didn't "look like code" left the
                # agent unable to use file_read/glob/websearch/bash for any
                # research or non-code request (it broke out of the loop with no
                # tool calls). Mode gating (plan=read-only, build=all) already
                # controls which tools exist; tool_choice="auto" lets the model
                # decide whether to actually call one.
                turn_tools = openai_tools
                try:
                    _tool_choice = mode_config.tool_choice if mode_config else "auto"
                    async for event in stream_with_retries(
                        self.provider,
                        messages,
                        turn_tools,
                        session_id,
                        iteration,
                        stream_state,
                        tool_choice=_tool_choice,
                    ):
                        if event.kind == EventKind.WARNING and event.data.get("context_exceeded"):
                            context_exceeded = True
                        yield event
                except ZenithError:
                    return
                if context_exceeded:
                    logger.info("Context exceeded at runtime — summarizing")
                    yield r.warning(
                        "Context window exceeded, summarizing and retrying...", session_id
                    )
                    _rebuild_holder: list = []
                    async for ev in self._summarize_and_rebuild(
                        history,
                        session_id,
                        messages,
                        result=_rebuild_holder,
                        base_len=base_len,
                        system_prompt=system_prompt,
                        prompt=prompt,
                        model=model,
                        plan_context=plan_context,
                        use_system_prompt=model_use_system_prompt,
                        repo_map=repo_map,
                    ):
                        yield ev
                    messages = _rebuild_holder[0]
                    token_info = self.context_manager.get_token_info(messages, model, self.provider)
                    if token_info.percent > 0.95:
                        yield r.error(
                            "Context window exhausted even after summarization",
                            session_id,
                            code="CONTEXT_EXHAUSTED",
                        )
                        return
                    continue
                finish_reason = getattr(self.provider, "_last_finish_reason", FinishReason.STOP)
                response_text = stream_state.response_text
                _total_completion_chars += len(response_text)
                native_tool_calls = getattr(self.provider, "_last_native_tool_calls", [])
                clean_response, tool_calls = UnifiedResponseFormatter.process_response(
                    response_text, native_tool_calls or None
                )
                logger.info(
                    "Agent turn %d response: %d chars, %d tool calls, clean=%d chars finish=%s",
                    iteration,
                    len(response_text),
                    len(tool_calls),
                    len(clean_response or ""),
                    finish_reason,
                )
                if clean_response:
                    # Suppress re-yielding the exact same final answer when the model
                    # repeats its closing text across iterations.
                    if clean_response != self._last_emitted_message:
                        yield r.message_event(
                            clean_response, session_id, partial=False, iteration=iteration
                        )
                        self._last_emitted_message = clean_response
                if finish_reason == FinishReason.LENGTH:
                    logger.info("FinishReason=LENGTH on turn %d — continuing response", iteration)
                    if iteration >= safety_iterations * 2:
                        yield r.error(
                            "Response length limit exceeded repeatedly",
                            session_id,
                            code="LENGTH_EXCEEDED",
                        )
                        return
                    continue
                if not tool_calls:
                    if not clean_response and (not stream_state.full_response):
                        yield r.error(
                            "Model returned empty response.",
                            session_id,
                            code="EMPTY_RESPONSE",
                            recoverable=True,
                        )
                    break
                if not self.tool_registry:
                    yield r.error("No tool registry available", session_id)
                    break
                if self.tool_registry:
                    for tc in tool_calls:
                        t_name = tc.get("tool")
                        if not t_name:
                            continue
                        if t_name == GET_TOOL_DEFINITION_TOOL:
                            target = (tc.get("params") or {}).get("tool_name")
                            if target and resolver.request_tool(target):
                                logger.info(
                                    "Discovery: loaded tool '%s' via get_tool_definition", target
                                )
                        elif t_name not in registered_tools and resolver.request_tool(t_name):
                            logger.info(
                                "Dynamic tool escalation: promoted tool '%s' into active schema",
                                t_name,
                            )
                    new_active = resolver.active_names()
                    if set(new_active) != registered_tools:
                        registered_tools = set(new_active)
                        openai_tools = resolver.openai_tools(mode, allowed_mcp=allowed_mcp)
                        self.context_manager.set_aux_tokens(resolver.schema_tokens(model))
                valid_calls, invalid_calls = validate_tool_calls(tool_calls, registered_tools)
                invalid_names = [str(tc.get("tool") or tc) for tc in invalid_calls]
                if invalid_names:
                    yield r.warning(
                        f"Hallucinated tools ignored: {', '.join(invalid_names)}", session_id
                    )
                if not valid_calls:
                    msgs = [
                        {"role": "assistant", "content": response_text or "[tool calls]"},
                        {
                            "role": "user",
                            "content": f"Tool calls for non-existent tools: {', '.join(invalid_names)}. Available: {', '.join(sorted(registered_tools))}.",
                        },
                    ]
                    messages.extend(msgs)
                    continue
                messages.append({"role": "assistant", "content": response_text or "[tool calls]"})
                if _all_calls_repeat(valid_calls, executed_calls):
                    # The model re-issued calls that already ran. No regex guesses
                    # intent here: fall through so the per-call loop skips them and
                    # the stall handler injects targeted feedback, letting the model
                    # self-correct (write the final summary or call something new).
                    logger.info(
                        "All requested calls already executed this turn; falling through so the "
                        "per-call loop can skip them and the stall handler can guide the model."
                    )
                if task_completed:
                    yield r.warning(
                        "Model emitted tool calls after signaling completion; finalizing the turn.",
                        session_id,
                        extra={"skipped_tool_calls": [tc.get("tool") for tc in valid_calls]},
                    )
                    break
                stop_turn = False
                skipped_calls: list[str] = []
                replayed_results = 0
                newly_executed = False
                for tc in valid_calls:
                    tool_name = tc["tool"]
                    tool_params = normalize_file_params(tc.get("params", {}), tc["tool"])
                    sig = _call_signature(tool_name, tool_params)
                    if sig in executed_calls:
                        failed_flag = " [failed]" if sig in failed_calls else ""
                        skipped_calls.append(f"{tool_name}({_params_label(tool_params)}){failed_flag}")
                        # Re-present a bounded number of stored results so the model can
                        # actually see the output. A "shown above" pointer is not enough
                        # after a compaction (results are gone), which drives the model to
                        # re-issue identical calls. Cap the number re-injected per
                        # iteration so a pathological re-emission batch can't inflate
                        # context; the rest are covered by the skip warning below.
                        if stall_count == 0 and not newly_executed and replayed_results < 2:
                            stored = executed_results.get(sig)
                            if stored is not None:
                                messages.append({"role": "user", "content": stored})
                                replayed_results += 1
                        continue
                    reject_msg = validate_tool_rejection(tool_name, tool_params, created_files, ws)
                    if tool_name in ("bash", "terminal") and (not reject_msg):
                        from server.toolkit.command_safety import assess_command

                        assessment = assess_command(tool_params.get("command", ""))
                        if assessment.is_risky and not self.config.auto_risky:
                            reject_msg = f"Command denied: {tool_params.get('command', '')} ({assessment.reason})"
                    if tool_name == FILE_WRITE_TOOL and (not reject_msg):
                        target = tool_params.get("filepath") or tool_params.get("path") or ""
                        if target:
                            resolved = validate_path(target, ws)
                            if resolved is not None and resolved.exists():
                                if not self.config.auto_overwrite:
                                    reject_msg = (
                                        f"File overwrite denied: '{target}' already exists. Pass "
                                        f"overwrite=true to replace it, or delete it first."
                                    )
                                else:
                                    tool_params[FILE_OVERWRITE_PARAM] = True
                    if tool_name == FILE_DELETE_TOOL and (not reject_msg):
                        target = tool_params.get("path") or ""
                        if target:
                            resolved = validate_path(target, ws)
                            if resolved is not None and resolved.exists():
                                if not self.config.auto_risky:
                                    reject_msg = f"File delete denied: '{target}'."
                    if reject_msg:
                        yield r.warning(f"Tool '{tool_name}' rejected: {reject_msg}", session_id)
                        messages.append(
                            {"role": "user", "content": f"[Tool rejected] {reject_msg}"}
                        )
                        consecutive_failures += 1
                        if consecutive_failures >= _reflimit:
                            yield r.error(
                                f"Too many errors ({consecutive_failures}).",
                                session_id,
                                code="REFLECTION_LIMIT",
                                recoverable=True,
                            )
                            return
                        continue
                    yield r.tool_call(tool_name, tool_params, session_id)
                    tools_used = True
                    newly_executed = True
                    result, duration_ms = await execute_tool(
                        self.tool_registry,
                        tool_name,
                        tool_params,
                        ws,
                        mode,
                        allowed_mcp=mode_config.allowed_mcp if mode_config else None,
                    )
                    yield r.tool_result(
                        tool_name,
                        result.success,
                        session_id,
                        output=result.output or "",
                        error=result.error or "",
                        metadata=build_tool_metadata(tool_name, tool_params, result, duration_ms),
                    )
                    if result.stop_turn:
                        logger.info("Tool '%s' requested stop_turn", tool_name)
                        stop_turn = True
                    if not result.success:
                        consecutive_failures += 1
                        err_msg = result.error or f"Tool '{tool_name}' execution failed"
                        messages.append(
                            {
                                "role": "user",
                                "content": f"[Tool error] {tool_name} failed: {err_msg}. Try a different approach.",
                            }
                        )
                        if consecutive_failures >= _reflimit:
                            yield r.error(
                                f"Too many errors ({consecutive_failures}).",
                                session_id,
                                code="REFLECTION_LIMIT",
                                recoverable=True,
                            )
                            return
                    else:
                        # A successful execution is progress; reset the streak so a
                        # few scattered cosmetic failures never abort the task.
                        consecutive_failures = 0
                    _ti = self.context_manager.get_token_info(messages, model, self.provider)
                    _remaining = _ti.total - _ti.used
                    _threshold = 20000 if _ti.total >= 200000 else int(_ti.total * 0.2)
                    if _remaining <= _threshold and _remaining > 0:
                        yield r.warning(
                            f"Context approaching limit ({_ti.percent * 100:.0f}%), summarizing...",
                            session_id,
                            extra={"tokenInfo": vars(_ti)},
                        )
                        _rebuild_holder: list = []
                        async for ev in self._summarize_and_rebuild(
                            history,
                            session_id,
                            messages,
                            result=_rebuild_holder,
                            base_len=base_len,
                            system_prompt=system_prompt,
                            prompt=prompt,
                            model=model,
                            plan_context=plan_context,
                            use_system_prompt=model_use_system_prompt,
                            repo_map=repo_map,
                        ):
                            yield ev
                        messages = _rebuild_holder[0]
                        _ti2 = self.context_manager.get_token_info(messages, model, self.provider)
                        if _ti2.percent > 0.95:
                            yield r.error(
                                f"Context exhausted ({_ti2.percent:.0f}%)",
                                session_id,
                                code="CONTEXT_EXHAUSTED",
                                recoverable=True,
                            )
                            return
                        yield r.warning("Context summarized, continuing", session_id)
                    executed_calls.add(sig)
                    if not result.success:
                        failed_calls.add(sig)
                    if result.success:
                        p = tool_params.get("filepath") or tool_params.get("path") or ""
                        if p:
                            if tool_name == "file_write":
                                created_files.add(p)
                            if tool_name in ("file_edit", "file_write"):
                                files_edited.append(p)
                    for ev in await post_execution_hooks(
                        tool_name, tool_params, result, ws, session_id
                    ):
                        yield ev
                    model_ctx = _get_model_context_window(model)
                    dynamic_max = _dynamic_max_output(model_ctx)
                    result_limit = dynamic_max
                    _compacted, cstats = compact_tool_output(
                        result.output or "", max_output=result_limit
                    )
                    if cstats.chars_removed > 0:
                        yield r.context_compacted(
                            tool_name,
                            cstats.chars_removed,
                            cstats.tokens_saved,
                            cstats.reason,
                            session_id,
                            original_chars=cstats.original_chars,
                            compacted_chars=cstats.compacted_chars,
                        )
                    messages.append(
                        {
                            "role": "user",
                            "content": format_tool_result(tool_name, result, result_limit),
                        }
                    )
                    executed_results[sig] = messages[-1]["content"]
                    self._loop_detector.record(tool_name, tool_params, messages[-1]["content"])
                if skipped_calls:
                    shown = ", ".join(skipped_calls[:_SKIP_WARNING_CAP])
                    omitted = len(skipped_calls) - _SKIP_WARNING_CAP
                    if omitted > 0:
                        shown += f", +{omitted} more"
                    yield r.warning(
                        "Skipped calls already completed with identical params this turn: "
                        + shown,
                        session_id,
                    )
                    failed_skips = [s for s in skipped_calls if " [failed]" in s]
                    msg = (
                        "[System] These calls were already attempted earlier in this turn "
                        "with identical parameters and were NOT re-run: "
                        + shown
                        + ". Their results are already shown above in this conversation."
                    )
                    if failed_skips:
                        msg += (
                            " The calls marked [failed] did not succeed; do NOT retry them "
                            "with identical parameters - use different parameters or a "
                            "different approach."
                        )
                    msg += " Do not re-run any of the listed calls; continue with the next unfinished step."
                    messages.append({"role": "user", "content": msg})
                if skipped_calls and not newly_executed and not task_completed:
                    stall_count += 1
                    if stall_count == 1:
                        used_tools = {name for name, _ in executed_calls}
                        all_tools = (
                            self.tool_registry.list_tools() if self.tool_registry else []
                        )
                        remaining = sorted(
                            t
                            for t in all_tools
                            if t not in used_tools and t not in ("discover_capabilities", "get_tool_definition")
                        )
                        stall_msg = (
                            "[System] No new tool was executed this iteration; every call you "
                            "emitted was already attempted earlier with identical parameters. "
                            "You are stuck repeating previous work."
                        )
                        if remaining:
                            stall_msg += (
                                " Tools still NOT used this turn: " + ", ".join(remaining)
                                + ". If you need any of them, call "
                                "get_tool_definition('<tool>') NOW and then call that tool. "
                                "Do not emit any other calls this response."
                            )
                        else:
                            stall_msg += (
                                " All available tools have been used. If the task is done, "
                                "write your final summary and stop."
                            )
                        yield r.warning(stall_msg, session_id)
                        messages.append({"role": "user", "content": stall_msg})
                    else:
                        task_completed = True
                        yield r.warning(
                            "No new tool work for several consecutive iterations; finalizing the turn.",
                            session_id,
                        )
                        break
                elif newly_executed:
                    stall_count = 0
                if stop_turn:
                    logger.info("Stopping turn: tool requested stop_turn")
                    break
                if self._loop_detector.is_loop_detected():
                    yield r.error(
                        "Loop detected: the same tool calls are repeating without progress.",
                        session_id,
                        code="LOOP_DETECTED",
                        recoverable=True,
                    )
                    return
                # Completion is decided by the model's own behavior — it stops
                # emitting tool calls (the text-only break above), or the stall
                # handler finalizes after repeated identical work. No text-phrase
                # regex is used to guess whether the model is "done".
                if files_edited:
                    auto_commit(ws, files_edited)
                    files_edited.clear()
            else:
                yield r.error(
                    f"Safety net exceeded ({safety_iterations} iterations)",
                    session_id,
                    code="MAX_ITERATIONS",
                )
                return
        finally:
            pass
        token_info = self.context_manager.get_token_info(messages, model, self.provider)
        prompt_tokens = token_info.used
        estimated_completion = max(1, _total_completion_chars // 4)
        cum_usage: dict = getattr(self.provider, "_cumulative_usage", {})
        is_estimated = cum_usage.get("total_tokens", 0) == 0
        if mode == BUILD_MODE and tools_used and (not created_files):
            yield r.warning(
                "Build completed but no files were created. The model output text instead of using file_write.",
                session_id,
                code="NO_FILES_CREATED",
            )
        yield r.success(
            "Request processed successfully",
            session_id,
            iteration,
            {
                "used": token_info.used,
                "remaining": token_info.remaining,
                "total": token_info.total,
                "percent": round(token_info.percent, 3),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": estimated_completion,
                "cached_tokens": cum_usage.get("cached_tokens", 0),
                "cache_creation_tokens": cum_usage.get("cache_creation_tokens", 0),
                "estimated": is_estimated,
                "mode": mode,
            },
        )

    async def _maybe_summarize(self, history, session_id, messages=None, reason="automatic"):
        from server.agents.summarizer import ConversationSummarizer

        model = self.provider.model
        token_info = (
            self.context_manager.get_token_info(messages or [], model, self.provider)
            if messages
            else None
        )
        used = token_info.used if token_info else 0
        total = token_info.total if token_info else 0
        yield r.context_compaction_started(session_id, reason, used, total)
        yield r.warning("Context approaching limit, summarizing...", session_id)
        try:
            if messages:
                pruned = self._prune_tool_outputs(messages)
                if pruned["count"]:
                    yield r.context_compacted(
                        "context",
                        pruned["chars_removed"],
                        pruned["tokens_saved"],
                        f"pruned {pruned['count']} old tool result(s)",
                        session_id,
                    )
            ctx = min(_get_model_context_window(model), self.config.max_context_tokens)
            reserve = _adaptive_reserve(model, ctx)
            keep_tokens = max(8000, min(20000, int(max(0, ctx - reserve) * 0.25)))
            cut = _find_compaction_cut_budgeted(
                history,
                keep_tokens,
                lambda m: self.context_manager.count_tokens(getattr(m, "content", str(m)), model),
            )
            target = history[:cut] if cut > 0 else history
            self._summary = await ConversationSummarizer(self.config, self.provider).summarize(
                target, model, session_id=session_id, previous_summary=self._summary
            )
            tokens_saved = 0
            if messages:
                target_tokens = sum(
                    self.context_manager.count_tokens(getattr(m, "content", str(m)), model)
                    for m in target
                )
                tokens_saved = max(
                    0, target_tokens - self.context_manager.count_tokens(self._summary, model)
                )
            yield r.context_compaction_ended(
                session_id,
                reason,
                used,
                total,
                tokens_saved=tokens_saved,
                summary_chars=len(self._summary),
            )
            yield r.warning("Context summarized", session_id)
        except Exception as e:
            yield r.warning(f"Summarization failed: {e}", session_id)

    def _prune_tool_outputs(
        self, messages: list[dict], keep_turns: int = 2, max_output: int = 2000
    ) -> dict:
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
        live_tail = messages[base_len:]
        rebuilt = self.context_manager.build_messages(
            history,
            system_prompt,
            prompt,
            model,
            summary=self._summary,
            plan_block=plan_context,
            use_system_prompt=use_system_prompt,
            repo_map=repo_map,
        )
        if live_tail:
            rebuilt.extend(live_tail)
            rebuilt.append(
                {
                    "role": "user",
                    "content": "Continue if you have next steps, or stop and ask for clarification for how to proceed.",
                }
            )
            logger.info("Replayed live turn after compaction: %d messages", len(live_tail))
        sanitized = [m for m in rebuilt if isinstance(m, dict)]
        dropped = len(rebuilt) - len(sanitized)
        if dropped:
            logger.warning(
                "Rebuild dropped %d non-dict message(s): %r",
                dropped,
                [type(m).__name__ for m in rebuilt if not isinstance(m, dict)],
            )
        return sanitized

    async def _summarize_and_rebuild(
        self,
        history,
        session_id,
        messages,
        *,
        result,
        base_len,
        system_prompt,
        prompt,
        model,
        plan_context,
        use_system_prompt,
        repo_map,
    ) -> AsyncIterator[Event]:
        """Summarize the conversation then rebuild the active message list.

        Yields the summarization events produced by ``_maybe_summarize`` and
        stores the freshly rebuilt message list into ``result`` (a one-element
        list) so the caller can continue the loop against the compacted
        context.
        """
        async for ev in self._maybe_summarize(history, session_id, messages):
            yield ev
        result.append(
            self._rebuild_messages(
                messages,
                base_len,
                history,
                system_prompt,
                prompt,
                model,
                plan_context,
                use_system_prompt,
                repo_map,
            )
        )

    def _get_tool_schemas(self) -> list[dict]:
        return self.tool_registry.get_schemas() if self.tool_registry else []

    def _get_tool_names(self) -> list[str]:
        return self.tool_registry.list_tools() if self.tool_registry else []

    def _apply_prompt_caching(self, messages: list[dict]) -> list[dict]:
        if not messages:
            return messages
        provider_name = getattr(self.provider, "name", "") or ""
        catalog = self._catalog_for_provider(provider_name)
        if not catalog.get("supports_prompt_caching", False):
            return messages
        cached = [dict(msg) for msg in messages]
        for i in range(min(2, len(cached))):
            cached[i]["cache_control"] = {"type": "ephemeral"}
        if len(cached) >= 1:
            cached[-1]["cache_control"] = {"type": "ephemeral"}
        return cached

    @staticmethod
    def _catalog_for_provider(provider_name: str) -> dict:
        try:
            from server.persistence.repositories import load_catalog

            return load_catalog().get("providers", {}).get(provider_name) or {}
        except Exception:
            return {}
