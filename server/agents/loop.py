from __future__ import annotations
import json
import logging
from collections import Counter
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from server.config.constants import (
    BG_OUTPUT_TAIL,
    BUILD_MODE,
    CHARS_PER_TOKEN,
    COMPACTION_KEEP_TAIL,
    CONTEXT_SUMMARY_THRESHOLD,
    FILE_DELETE_TOOL,
    FILE_EDIT_TOOL,
    FILE_OVERWRITE_PARAM,
    FILE_WRITE_TOOL,
    GET_TOOL_DEFINITION_TOOL,
    LARGE_CONTEXT_WINDOW,
    MANIFEST_CHECKS_CAP,
    PLAN_MODE,
    POLL_TOOLS,
    SKIP_WARNING_CAP,
    SUMMARY_MIN_CHARS,
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
from .compaction import compact_tool_output, head_tail_trim
from .context import ContextManager, _adaptive_reserve, _get_model_context_window
from .llm_stream import StreamState, stream_completion
from .loop_detection import LoopDetector
from .prompts import build_plan_system_prompt, build_system_prompt
from .session_workspace import is_identical_replay, known_files, record_edit, record_write
from .validation import reflection_error_limit, schemas_to_openai_tools

_format_tool_result = format_tool_result
logger = logging.getLogger(__name__)


def _result_present(messages: list[dict], content: str) -> bool:
    return any(m.get("content") == content for m in messages)


def _call_signature(tool_name: str, params: dict) -> tuple[str, str]:
    return (
        tool_name,
        json.dumps(params, sort_keys=True, separators=(",", ":"), default=str),
    )


def _params_label(params: dict) -> str:
    if not params:
        return ""
    if "tool_name" in params:
        return str(params["tool_name"])
    for key in ("path", "pattern", "query", "url", "command", "task"):
        if params.get(key):
            value = params[key]
            if isinstance(value, str) and len(value) > 48:
                value = value[:48] + "…"
            return f"{key}={value}"
    if len(params) == 1:
        key, value = next(iter(params.items()))
        return f"{key}={value}"
    return ""


def _build_manifest(
    created_files: set[str],
    files_edited: list[str],
    task_completed: bool,
    stall_finalized: bool,
    last_text: str = "",
    workspace_root: str | None = None,
    verification: list[dict] | None = None,
) -> dict:
    created = sorted(created_files)
    modified = sorted(p for p in files_edited if p not in created_files)
    completed = bool(task_completed and not stall_finalized)
    remaining: list[str] = []
    if not completed:
        text = (last_text or "").strip()
        if text:
            remaining = [text]
        elif created_files:
            remaining = ["Files were written but no verification evidence was produced."]
        elif files_edited:
            remaining = ["Files were modified but no verification evidence was produced."]
        else:
            remaining = ["The turn ended without completing any work."]
    changed = bool(created_files or files_edited)
    payload: dict = {
        "created": created,
        "modified": modified,
        "remaining": remaining,
        "completed": completed,
        "stalled": bool(stall_finalized),
        "verified": True if not changed else _has_verification_evidence(verification or []),
        "checks": [
            {k: v for k, v in (c or {}).items() if k != "seq"} for c in (verification or [])
        ],
    }
    files: list[dict] = []
    if created_files:
        root = Path(workspace_root or ".")
        for p in created:
            resolved = root / p
            exists = resolved.exists()
            files.append(
                {
                    "path": p,
                    "exists": exists,
                    "size": resolved.stat().st_size if exists else 0,
                }
            )
    payload["files"] = files
    return payload


def _all_calls_repeat(valid_calls: list[dict], executed: set[tuple[str, str]]) -> bool:
    if not valid_calls or not executed:
        return False
    for tc in valid_calls:
        if tc["tool"] in POLL_TOOLS:
            return False
        sig = _call_signature(tc["tool"], normalize_file_params(tc.get("params", {}), tc["tool"]))
        if sig not in executed:
            return False
    return True


def _most_common_count(items: list[str]) -> int:
    if not items:
        return 0
    return Counter(items).most_common(1)[0][1]


def _has_verification_evidence(checks: list[dict], after_seq: int | None = None) -> bool:
    for check in checks or []:
        if (check.get("output_len") or 0) > 0:
            if after_seq is None or (check.get("seq") or 0) >= after_seq:
                return True
    return False


def _pending_background_completions() -> list:
    try:
        from server.toolkit.tools.background import get_background_manager

        return get_background_manager().pending_completions()
    except Exception:
        return []


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
        self._inject_session_state(messages, session_id)
        base_len = len(messages)
        logger.info(
            "Context built: %d messages, system_prompt=%d chars", len(messages), len(system_prompt)
        )
        if self.context_manager.should_summarize(messages, model, self.provider):
            _rebuild_holder: list[Any] = []
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
            yield r.warning("Request was cancelled before starting", session_id, code="CANCELLED")
            return
        messages = self._apply_prompt_caching(messages)
        logger.info(
            "=== PROMPT READY FOR LLM session=%s mode=%s messages=%d ===",
            session_id,
            mode,
            len(messages),
        )
        logger.info("=== SYSTEM PROMPT (%d chars) ===\n%s", len(system_prompt), system_prompt)
        for i, msg in enumerate(messages):
            role = msg.get("role", "?")
            content = str(msg.get("content", ""))
            preview = content[:160].replace("\n", "\\n") if role != "system" and content else ""
            logger.info("--- MSG [%d] role=%s (len=%d) ---", i, role, len(content))
            if preview:
                logger.info("    preview=%s", preview)
        iteration = 0
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
        stall_finalized = False
        written_paths: set[str] = set()
        path_write_attempts: list[str] = []
        warned_rejects: set[tuple[str, str]] = set()
        warned_skips: set[str] = set()
        pending_skips: list[str] = []
        post_write_checks: list[dict] = []
        change_seq = 0
        last_evidence_seq = 0
        prior_replay_blocks = 0
        _total_completion_chars = 0

        def _with_manifest(ev: Event) -> Event:
            if isinstance(ev.data, dict) and "manifest" not in ev.data:
                ev.data["manifest"] = _build_manifest(
                    created_files,
                    files_edited,
                    task_completed,
                    stall_finalized,
                    self._last_emitted_message or "",
                    self.config.workspace_root,
                    post_write_checks,
                )
            return ev

        try:
            safety_iterations = self._resolve_safety_iterations(model)
            while iteration < safety_iterations:
                if self.is_cancelled(sequence):
                    yield r.warning("Request cancelled", session_id, code="CANCELLED")
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
                        code="CONTEXT",
                        extra={
                            "tokenInfo": {
                                "used": token_info.used,
                                "remaining": token_info.remaining,
                                "total": token_info.total,
                                "percent": token_info.percent,
                            }
                        },
                    )
                    _rebuild_holder = []
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
                        yield _with_manifest(
                            r.error(
                                "Context window exhausted even after summarization",
                                session_id,
                                code="CONTEXT_EXHAUSTED",
                                action="retry",
                                hint="Start a new session to free up context.",
                            )
                        )
                        return
                for job in _pending_background_completions():
                    status = "completed" if job.exit_code == 0 else f"failed (exit code {job.exit_code})"
                    detail = f"Background job {job.id} {status}."
                    tail_source = (job.stderr or job.stdout or "").strip()
                    if tail_source:
                        detail += f"\nOutput (tail): {tail_source[-BG_OUTPUT_TAIL:]}"
                    messages.append({"role": "user", "content": detail})
                    yield r.warning(detail, session_id, code="BACKGROUND_COMPLETED")
                logger.info(
                    "Agent turn %d (dynamic stop) session=%s tokens=%.1f%%",
                    iteration,
                    session_id,
                    token_info.percent * 100,
                )
                stream_state = StreamState()
                finish_reason = FinishReason.STOP
                context_exceeded = False
                turn_tools = openai_tools
                turn_errored = False
                try:
                    _tool_choice = mode_config.tool_choice if mode_config else "auto"
                    async for event in stream_completion(
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
                        if event.kind == EventKind.ERROR:
                            turn_errored = True
                        yield event
                except ZenithError:
                    return
                if turn_errored:
                    consecutive_failures += 1
                    return
                if context_exceeded:
                    logger.info("Context exceeded at runtime — summarizing")
                    yield r.warning(
                        "Context window exceeded, summarizing and retrying...",
                        session_id,
                        code="CONTEXT",
                    )
                    _rebuild_holder = []
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
                        yield _with_manifest(
                            r.error(
                                "Context window exhausted even after summarization",
                                session_id,
                                code="CONTEXT_EXHAUSTED",
                                action="retry",
                                hint="Start a new session to free up context.",
                            )
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
                    if clean_response != self._last_emitted_message:
                        yield r.message_event(
                            clean_response, session_id, partial=False, iteration=iteration
                        )
                        self._last_emitted_message = clean_response
                if finish_reason == FinishReason.LENGTH:
                    logger.info("FinishReason=LENGTH on turn %d — continuing response", iteration)
                    if iteration >= safety_iterations * 2:
                        yield _with_manifest(
                            r.error(
                                "Response length limit exceeded repeatedly",
                                session_id,
                                code="LENGTH_EXCEEDED",
                                action="retry",
                                hint="Try a shorter prompt or a model with a larger output budget.",
                            )
                        )
                        return
                    continue
                if not tool_calls:
                    if not clean_response and (not stream_state.full_response) and not turn_errored:
                        yield _with_manifest(
                            r.error(
                                "Model returned empty response.",
                                session_id,
                                code="EMPTY_RESPONSE",
                                recoverable=True,
                                action="retry",
                                hint="The model produced no output. Retry this prompt.",
                            )
                        )
                        return
                    task_completed = True
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
                        prev_names = set(registered_tools)
                        registered_tools = set(new_active)
                        openai_tools = resolver.openai_tools(mode, allowed_mcp=allowed_mcp)
                        self.context_manager.set_aux_tokens(resolver.schema_tokens(model))
                        logger.info(
                            "Tool set changed mid-turn: added=%s removed=%s",
                            sorted(registered_tools - prev_names),
                            sorted(prev_names - registered_tools),
                        )
                valid_calls, invalid_calls = validate_tool_calls(tool_calls, registered_tools)
                invalid_names = [str(tc.get("tool") or tc) for tc in invalid_calls]
                if invalid_names:
                    yield r.warning(
                        f"Hallucinated tools ignored: {', '.join(invalid_names)}",
                        session_id,
                        code="INVALID_TOOLS",
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
                    _repeat_text = (clean_response or "").strip()
                    if (
                        _repeat_text
                        and len(_repeat_text) >= SUMMARY_MIN_CHARS
                        and (created_files or files_edited)
                    ):
                        task_completed = True
                        logger.info(
                            "Turn finalized at repeat-detection: summary + only repeated calls "
                            "after file work (%d file(s)).",
                            len(created_files),
                        )
                        break
                    logger.info(
                        "All requested calls already executed this turn; falling through so the "
                        "per-call loop can skip them and the stall handler can guide the model."
                    )
                if task_completed:
                    yield r.warning(
                        "Model emitted tool calls after signaling completion; finalizing the turn.",
                        session_id,
                        code="STALL",
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
                    blocked_write = False
                    if sig in executed_calls and tool_name not in POLL_TOOLS:
                        failed_flag = " [failed]" if sig in failed_calls else ""
                        skipped_calls.append(
                            f"{tool_name}({_params_label(tool_params)}){failed_flag}"
                        )
                        if stall_count == 0 and not newly_executed and replayed_results < 2:
                            stored = executed_results.get(sig)
                            if stored is not None and not _result_present(messages, stored):
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
                            path_write_attempts.append(target)
                            resolved = validate_path(target, ws)
                            if (
                                resolved is not None
                                and resolved.exists()
                                and is_identical_replay(
                                    session_id, target, tool_params.get("content", "")
                                )
                            ):
                                blocked_write = True
                                prior_replay_blocks += 1
                                reject_msg = (
                                    f"File re-write blocked: '{target}' was already written in "
                                    "an earlier turn of this session with identical content. It "
                                    "already exists with exactly this content, so no change is "
                                    "needed. If you need to modify it, read it first, then use "
                                    "file_edit."
                                )
                            elif resolved is not None and resolved.exists():
                                if not self.config.auto_overwrite:
                                    reject_msg = (
                                        f"File overwrite denied: '{target}' already exists. Pass "
                                        f"overwrite=true to replace it, or delete it first."
                                    )
                                else:
                                    tool_params[FILE_OVERWRITE_PARAM] = True
                            if target in written_paths:
                                blocked_write = True
                                reject_msg = (
                                    f"File rewrite blocked: '{target}' was already written this "
                                    f"turn. To modify it, read it first, then use file_edit; "
                                    f"do not re-write the same path."
                                )
                    if tool_name == FILE_DELETE_TOOL and (not reject_msg):
                        target = tool_params.get("path") or ""
                        if target:
                            resolved = validate_path(target, ws)
                            if resolved is not None and resolved.exists():
                                if not self.config.auto_risky:
                                    reject_msg = f"File delete denied: '{target}'."
                    if reject_msg:
                        reject_sig = _call_signature(tool_name, tool_params)
                        if reject_sig not in warned_rejects:
                            warned_rejects.add(reject_sig)
                            yield r.warning(
                                f"Tool '{tool_name}' rejected: {reject_msg}",
                                session_id,
                                code="REJECTED",
                            )
                        messages.append(
                            {"role": "user", "content": f"[Tool rejected] {reject_msg}"}
                        )
                        if blocked_write:
                            skipped_calls.append(
                                f"{tool_name}({_params_label(tool_params)}) [blocked]"
                            )
                            continue
                        consecutive_failures += 1
                        if consecutive_failures >= _reflimit:
                            yield _with_manifest(
                                r.error(
                                    f"Too many errors ({consecutive_failures}).",
                                    session_id,
                                    code="REFLECTION_LIMIT",
                                    recoverable=True,
                                )
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
                        metadata=build_tool_metadata(
                            tool_name, tool_params, result, duration_ms, ws
                        ),
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
                        if tool_name == FILE_EDIT_TOOL:
                            messages.append(
                                {
                                    "role": "user",
                                    "content": (
                                        "[Edit guidance] The edit did not apply because the "
                                        "target text does not match the file's current content. "
                                        "Read the file with file_read to get its exact current "
                                        "content, then re-apply the edit."
                                    ),
                                }
                            )
                        if consecutive_failures >= _reflimit:
                            yield _with_manifest(
                                r.error(
                                    f"Too many errors ({consecutive_failures}).",
                                    session_id,
                                    code="REFLECTION_LIMIT",
                                    recoverable=True,
                                )
                            )
                            return
                    else:
                        consecutive_failures = 0
                    _ti = self.context_manager.get_token_info(messages, model, self.provider)
                    _remaining = _ti.total - _ti.used
                    _threshold = 20000 if _ti.total >= LARGE_CONTEXT_WINDOW else int(_ti.total * 0.2)
                    if _remaining <= _threshold and _remaining > 0:
                        yield r.warning(
                            f"Context approaching limit ({_ti.percent * 100:.0f}%), summarizing...",
                            session_id,
                            code="CONTEXT",
                            extra={"tokenInfo": vars(_ti)},
                        )
                        _rebuild_holder = []
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
                            yield _with_manifest(
                                r.error(
                                    f"Too many errors ({consecutive_failures}).",
                                    session_id,
                                    code="REFLECTION_LIMIT",
                                    recoverable=True,
                                    action="retry",
                                    hint="Adjust the prompt and retry.",
                                )
                            )
                            return
                        yield r.warning("Context summarized, continuing", session_id, code="CONTEXT")
                    executed_calls.add(sig)
                    if not result.success:
                        failed_calls.add(sig)
                    if result.success:
                        p = tool_params.get("filepath") or tool_params.get("path") or ""
                        if p:
                            if tool_name == FILE_WRITE_TOOL:
                                created_files.add(p)
                                written_paths.add(p)
                                record_write(session_id, p, tool_params.get("content", ""))
                            elif tool_name == FILE_EDIT_TOOL:
                                record_edit(session_id, p)
                            if tool_name in (FILE_EDIT_TOOL, FILE_WRITE_TOOL):
                                files_edited.append(p)
                            change_seq += 1
                        if (
                            change_seq > 0
                            and tool_name not in (FILE_WRITE_TOOL, FILE_EDIT_TOOL)
                            and len(post_write_checks) < MANIFEST_CHECKS_CAP
                        ):
                            post_write_checks.append(
                                {
                                    "tool": tool_name,
                                    "output_len": len(result.output or ""),
                                    "exit_code": (result.metadata or {}).get("exit_code"),
                                    "seq": change_seq,
                                }
                            )
                            if (result.output or "") != "":
                                last_evidence_seq = change_seq
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
                    new_skips = [s for s in skipped_calls if s not in warned_skips]
                    if new_skips:
                        warned_skips.update(new_skips)
                        for s in new_skips:
                            if s not in pending_skips:
                                pending_skips.append(s)
                        failed_skips = [s for s in skipped_calls if " [failed]" in s]
                        skip_msg = (
                            "[System] Calls listed below were already completed earlier in this "
                            "turn with identical parameters (or were blocked) and were NOT "
                            "re-run: "
                            + ", ".join(skipped_calls[:SKIP_WARNING_CAP])
                            + ". Do not re-run them; continue with the next "
                            "unfinished step."
                        )
                        if failed_skips:
                            skip_msg += (
                                " The calls marked [failed] did not succeed; do not retry them "
                                "with identical parameters - use different parameters or a "
                                "different approach."
                            )
                        messages.append({"role": "user", "content": skip_msg})
                if skipped_calls and not newly_executed and not task_completed:
                    stall_count += 1
                    current_text = (clean_response or "").strip()
                    if (
                        current_text
                        and len(current_text) >= SUMMARY_MIN_CHARS
                        and (created_files or files_edited)
                        and _has_verification_evidence(post_write_checks, after_seq=change_seq)
                    ):
                        task_completed = True
                        logger.info(
                            "Turn finalized: model wrote a final summary after completing "
                            "file work (%d file(s) changed, verification evidence present).",
                            len(created_files) + len(files_edited),
                        )
                        break
                    if (
                        (created_files or files_edited)
                        and last_evidence_seq >= change_seq
                        and last_evidence_seq > 0
                    ):
                        task_completed = True
                        logger.info(
                            "Turn finalized: file changes implemented and re-verification "
                            "produced evidence; no outstanding work."
                        )
                        break
                    if stall_count == 1:
                        stall_msg = (
                            "[System] No new tool was executed this iteration; every call you "
                            "emitted was already attempted earlier with identical parameters "
                            "(or was blocked as a re-write). You are stuck repeating previous "
                            "work. If the task is complete, write your final summary now and "
                            "stop; otherwise take a different action than before."
                        )
                        if (created_files or files_edited) and not _has_verification_evidence(
                            post_write_checks
                        ):
                            stall_msg += (
                                "\nYou changed file(s) this turn but no successful tool ran after "
                                "those changes to verify them. Run the relevant tests or checks "
                                "now so the result is confirmed before you finish."
                            )
                        yield r.warning(stall_msg, session_id, code="STALL")
                        messages.append({"role": "user", "content": stall_msg})
                    else:
                        task_completed = True
                        stall_finalized = True
                        yield r.warning(
                            "No new tool work for several consecutive iterations; finalizing the turn.",
                            session_id,
                            code="STALL",
                        )
                        break
                elif newly_executed:
                    stall_count = 0
                if path_write_attempts and _most_common_count(path_write_attempts) >= 3:
                    task_completed = True
                    stall_finalized = True
                    yield r.warning(
                        f"The model kept re-writing '{path_write_attempts[0]}'; finalizing the turn.",
                        session_id,
                        code="STALL",
                    )
                    break
                if stop_turn:
                    logger.info("Stopping turn: tool requested stop_turn")
                    task_completed = True
                    break
                if self._loop_detector.is_loop_detected():
                    yield _with_manifest(
                        r.error(
                            "Loop detected: the same tool calls are repeating without progress.",
                            session_id,
                            code="LOOP_DETECTED",
                            recoverable=True,
                        )
                    )
                    return
                if files_edited:
                    auto_commit(ws, files_edited)
                    files_edited.clear()
            else:
                yield _with_manifest(
                    r.error(
                        f"Safety net exceeded ({safety_iterations} iterations)",
                        session_id,
                        code="MAX_ITERATIONS",
                    )
                )
                return
        finally:
            pass
        final_summary = (self._last_emitted_message or "").strip()
        legit_completion = task_completed and not stall_finalized
        quiet_completion = legit_completion and len(final_summary) >= SUMMARY_MIN_CHARS
        if pending_skips and not quiet_completion:
            shown = ", ".join(pending_skips[:SKIP_WARNING_CAP])
            omitted = len(pending_skips) - SKIP_WARNING_CAP
            if omitted > 0:
                shown += f", +{omitted} more"
            yield r.warning(
                "Skipped calls already completed with identical params this turn "
                "(or blocked as re-writes): " + shown,
                session_id,
                code="SKIPPED_CALLS",
            )
        token_info = self.context_manager.get_token_info(messages, model, self.provider)
        cum_usage: dict = getattr(self.provider, "_cumulative_usage", {})
        prompt_tokens = cum_usage.get("prompt_tokens") or token_info.used
        completion_tokens = cum_usage.get("completion_tokens") or max(
            1, _total_completion_chars // 4
        )
        is_estimated = cum_usage.get("total_tokens", 0) == 0
        if mode == BUILD_MODE and tools_used and (not created_files):
            yield r.warning(
                "Build completed but no files were created. The model output text instead of using file_write.",
                session_id,
                code="NO_FILES_CREATED",
            )
        success_message = "Request processed successfully"
        if stall_finalized:
            created = ", ".join(sorted(created_files)) or "none"
            success_message = (
                f"Stopped after {iteration} iterations: the model stopped making progress. "
                f"Files written: {created}."
            )
        if (created_files or files_edited) and not _has_verification_evidence(post_write_checks):
            success_message += (
                " Files changed but not verified: no successful tool produced output after "
                "the changes to confirm the result. Use file_read to inspect the files or "
                "run the app/tests to verify they work."
            )
        manifest = _build_manifest(
            created_files,
            files_edited,
            task_completed,
            stall_finalized,
            self._last_emitted_message or "",
            self.config.workspace_root,
            post_write_checks,
        )
        yield r.turn_manifest(manifest, session_id)
        yield _with_manifest(
            r.success(
                success_message,
                session_id,
                iteration,
                {
                    "used": token_info.used,
                    "remaining": token_info.remaining,
                    "total": token_info.total,
                    "percent": round(token_info.percent, 3),
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "cached_tokens": cum_usage.get("cached_tokens", 0),
                    "cache_creation_tokens": cum_usage.get("cache_creation_tokens", 0),
                    "estimated": is_estimated,
                    "mode": mode,
                },
            )
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
        yield r.warning("Context approaching limit, summarizing...", session_id, code="CONTEXT")
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
            yield r.warning("Context summarized", session_id, code="CONTEXT")
        except Exception as e:
            yield r.warning(f"Summarization failed: {e}", session_id, code="CONTEXT")

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
        if catalog.get("adapter") == "gemini":
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

    @staticmethod
    def _inject_session_state(messages: list[dict], session_id: str) -> None:
        existing = known_files(session_id)
        if not existing:
            return
        lines = [
            ("[Session state] Files you already created or modified earlier in this session "
            "(they exist on disk; do not re-create or re-write them unless you are changing "
            "them):")
        ]
        for path in sorted(existing):
            rec = existing[path]
            lines.append(f"- {path} ({rec.size} bytes, content hash {rec.content_hash[:10]})")
        lines.append(
            "If you need to modify one of these, read it first (file_read), then use "
            "file_edit for a targeted change."
        )
        state_msg = {"role": "system", "content": "\n".join(lines)}
        idx = 1
        while idx < len(messages) and messages[idx].get("role") == "system":
            idx += 1
        messages.insert(idx, state_msg)
