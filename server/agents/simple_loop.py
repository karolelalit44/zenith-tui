from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from server.config.constants import (
    BUILD_MODE,
    DEFAULT_FILE_READ_LINES,
    MAX_ACTIVE_TOOLS_PER_TURN,
    MAX_STEPS_DEFAULT,
    MAX_STEPS_PROMPT,
    MAX_TOOL_OUTPUT_BASELINE,
    PLAN_MODE,
    SALVAGE_DIGEST_MAX_ITEMS,
    SALVAGE_INSTRUCTION,
    SUMMARY_MIN_CHARS,
)
from server.config.environment import ZENITH_SALVAGE_TIMEOUT
from server.config.settings import AGENT_MODES, AppSettings
from server.domain.enums import FinishReason
from server.domain.events import Event, EventKind
from server.domain.message import Message
from server.providers import responder as r
from server.providers.base import BaseProvider
from server.providers.parser import UnifiedResponseFormatter
from server.toolkit.param_normalizer import normalize_file_params
from server.toolkit.registry import ToolRegistry
from server.toolkit.resolver import SchemaResolver, build_mode_tool_seed

from ..toolkit.executor import (
    build_tool_metadata,
    execute_tool,
    format_tool_result,
    post_execution_hooks,
    validate_tool_calls,
    validate_tool_rejection,
)
from ..toolkit.base import ToolResult
from .compaction import compact_tool_output, prune_inflight_messages
from .context import ContextManager
from .llm_stream import StreamState, stream_completion
from .prompts import compose_system_context, default_template_sections
from .run_state import _activity_label
from .session_workspace import (
    evict_file_cache,
    get_cached_read,
    get_read_history,
    is_identical_replay,
    is_range_covered,
    record_read,
    record_write,
    slice_served_count,
)

logger = logging.getLogger(__name__)

_DEGENERATE_TOKENS = {
    "[tool calls]",
    "[thinking]",
    "[no output]",
    "...",  # sanitized placeholder for empty assistant turn (see prune_inflight_messages)
}


def _is_degenerate_message(text: str | None) -> bool:
    if not text or not str(text).strip():
        return True
    return str(text).strip().lower() in _DEGENERATE_TOKENS


def _merge_continuation(prefix: str, continuation: str) -> str:
    """Merge a continuation string into a prefix, trimming any overlapping boundary repetition."""
    if not prefix:
        return continuation
    if not continuation:
        return prefix
    max_k = min(len(prefix), len(continuation), 200)
    for k in range(max_k, 15, -1):
        if prefix.endswith(continuation[:k]):
            return prefix + continuation[k:]
    return prefix + continuation


class SimpleLoop:
    """A minimal, emergent-termination turn loop.
    """

    def __init__(
        self,
        config: AppSettings,
        provider: BaseProvider,
        context_manager: ContextManager | None = None,
        tool_registry: ToolRegistry | None = None,
        compaction_service: Any = None,
        **kwargs: Any,
    ) -> None:
        self.config = config
        self.provider = provider
        self.context_manager = context_manager or ContextManager(config)
        self.tool_registry = tool_registry
        self.compaction_service = compaction_service
        self._summary: str | None = None
        self._last_emitted_message: str | None = None
        self._accept_sequence: int = 0
        self._cancel_sequence: int = -1
        self._salvage_instruction: str = getattr(config, "salvage_instruction", SALVAGE_INSTRUCTION) or SALVAGE_INSTRUCTION
        self._heavy_tools_summarized: int = 0


    @property
    def last_error(self) -> str | None:
        return None

    @staticmethod
    def _salvage_digest(messages: list[dict]) -> str:
        digs = [
            str(m.get("salvage_digest") or m.get("digest"))
            for m in messages
            if isinstance(m, dict) and (m.get("salvage_digest") or m.get("digest"))
        ]
        if not digs:
            return ""
        shown = digs[-SALVAGE_DIGEST_MAX_ITEMS:]
        omitted = len(digs) - len(shown)
        lines = [
            "The turn ended before a final answer could be produced. Tool activity this turn:",
        ]
        lines.extend(f"- {d}" for d in shown)
        if omitted > 0:
            lines.append(f"(+{omitted} earlier steps omitted)")
        return "\n".join(lines)

    async def _salvage_final_answer(
        self,
        *,
        session_id: str,
        messages: list[dict],
        reason: str,
        iteration: int,
    ) -> AsyncIterator[Event]:
        import asyncio

        yield r.warning(
            f"Wrapping up without further tool use ({reason})...",
            session_id,
            code="SALVAGE",
        )
        instruction = self._salvage_instruction or SALVAGE_INSTRUCTION
        payload = list(messages) + [{"role": "user", "content": instruction}]
        text = ""
        try:
            result = await asyncio.wait_for(
                self.provider.complete(payload),
                timeout=ZENITH_SALVAGE_TIMEOUT,
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("Salvage completion failed (%s); using deterministic digest", e)
        else:
            raw = (result or "").strip()
            clean, attempted_calls = UnifiedResponseFormatter.process_response(raw)
            if attempted_calls:
                logger.info(
                    "Salvage reply contained %d tool call(s); discarding.", len(attempted_calls)
                )
            text = "" if _is_degenerate_message(clean) else clean.strip()
        if not text:
            text = self._salvage_digest(messages)
        if not text:
            return
        logger.info(
            "SALVAGE: reason=%s iteration=%d produced %d chars", reason, iteration, len(text)
        )
        yield r.message_event(text, session_id, partial=False, iteration=max(1, iteration))
        self._last_emitted_message = text

    async def _maybe_summarize_heavy_output(
        self, session_id: str, tool_name: str, result: Any
    ) -> str | None:
        return None

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
        mode: str = BUILD_MODE,
        plan_context: str = "",
        model_override: str | None = None,
        repo_map: str | None = None,
        skills_section: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[Event]:
        sequence = self.accept()
        self._last_emitted_message = None
        if hasattr(self.provider, "_reset_cumulative_usage"):
            self.provider._reset_cumulative_usage()
        _original_model = self.provider.model
        if model_override and model_override != self.provider.model:
            self.provider.model = model_override
        try:
            async for ev in self._run(
                prompt,
                session_id,
                history,
                mode,
                plan_context,
                sequence,
                repo_map,
                skills_section=skills_section,
            ):
                yield ev
        finally:
            if model_override and model_override != _original_model:
                self.provider.model = _original_model

    async def _run(
        self,
        prompt: str,
        session_id: str,
        history: list[Message],
        mode: str,
        plan_context: str,
        sequence: int,
        repo_map: str | None,
        skills_section: str | None = None,
    ) -> AsyncIterator[Event]:
        model = self.provider.model
        mode_config = AGENT_MODES.get(mode)
        allowed_tools = mode_config.allowed_tools if mode_config else None
        tool_choice = mode_config.tool_choice if mode_config else "auto"

        sections = default_template_sections(
            mode=mode,
            workspace_root=self.config.workspace_root,
            max_context_tokens=self.config.max_context_tokens,
        )
        if skills_section:
            sections.append(skills_section)
        system_prompt = "\n\n".join(compose_system_context(sections))

        resolver = SchemaResolver(self.tool_registry, seed=build_mode_tool_seed(allowed_tools))
        if self.tool_registry and prompt:
            for tool_name in self.tool_registry.list_tools_for_mode(mode):
                if len(resolver.active_names()) >= MAX_ACTIVE_TOOLS_PER_TURN:
                    break
                if re.search(r"\b" + re.escape(tool_name) + r"\b", prompt, re.IGNORECASE):
                    resolver.request_tool(tool_name)
        registered_tools = set(resolver.active_names())
        openai_tools = resolver.openai_tools(mode)

        messages = self.context_manager.build_messages(
            history,
            system_prompt,
            prompt,
            model,
            summary=self._summary,
            plan_block=plan_context,
            use_system_prompt=True,
            repo_map=repo_map,
            session_id=session_id,
            mode=mode,
        )

        if self.context_manager.should_summarize(messages, model):
            async for ev in self._compact(session_id, history, messages):
                yield ev
            messages = self._rebuild(
                history, system_prompt, prompt, model, plan_context, session_id, mode, repo_map
            )
        if self.context_manager.is_context_exhausted(messages, model):
            yield r.turn_manifest(
                {
                    "completed": False,
                    "stalled": False,
                    "remaining": [],
                    "answered": False,
                    "created": [],
                    "modified": [],
                    "any_tool_succeeded": False,
                    "summary": "[Context exhausted]",
                },
                session_id,
            )
            yield r.error(
                "Context window exhausted",
                session_id,
                code="CONTEXT_EXHAUSTED",
                action="retry",
                hint="Start a new session to free up context.",
            )
            return

        start_time = time.time()
        iteration = 0
        created_files: set[str] = set()
        files_edited: list[str] = []
        executed_calls: set[tuple[str, str]] = set()
        executed_call_status: dict[tuple[str, str], bool] = {}
        read_files: set[str] = set()
        any_tool_succeeded = False
        stall_count = 0
        stalled = False
        doomed = False
        doom_run = 0
        last_doom_sig: tuple[str, str] | None = None
        consecutive_failures = 0
        reflimit = int(getattr(self.config, "agent_reflection_limit", 0) or 4)
        progress_steps: list[dict] = []
        max_steps = int(getattr(self.config, "agent_max_steps", 0) or MAX_STEPS_DEFAULT)
        nudges = 0
        length_continuations = 0
        silent_continuations = 0
        pending_continuation_text = ""
        length_truncated = False
        last_finish_reason: FinishReason = FinishReason.STOP

        def _param_detail(params: dict) -> str:
            if not isinstance(params, dict):
                return ""
            for key in ("command", "path", "filepath", "pattern", "query", "name", "url"):
                val = params.get(key)
                if isinstance(val, str) and val.strip():
                    flat = " ".join(val.strip().split())
                    return flat[:48] + ("\u2026" if len(flat) > 48 else "")
            return ""

        def _emit_progress(tool_name: str, success: bool, detail: str = "") -> Event:
            label = _activity_label(tool_name, len(progress_steps) + 1, detail)
            if progress_steps and progress_steps[-1].get("status") == "active":
                progress_steps[-1] = {
                    "label": label,
                    "status": "done" if success else "error",
                    "tool": tool_name,
                }
            else:
                progress_steps.append(
                    {
                        "label": label,
                        "status": "done" if success else "error",
                        "tool": tool_name,
                    }
                )
            done = sum(1 for s in progress_steps if s["status"] == "done")
            percent = round(done * 100 / max(1, len(progress_steps)))
            return r.progress(
                percent, label, session_id, iteration=iteration, steps=list(progress_steps)
            )

        def _emit_progress_running(tool_name: str, detail: str = "") -> Event:
            label = _activity_label(tool_name, len(progress_steps) + 1, detail)
            progress_steps.append({"label": label, "status": "active", "tool": tool_name})
            done = sum(1 for s in progress_steps if s["status"] == "done")
            percent = round(done * 100 / max(1, len(progress_steps)))
            return r.progress(
                percent, label, session_id, iteration=iteration, steps=list(progress_steps)
            )

        while iteration < max_steps:
            if self.is_cancelled(sequence):
                yield r.turn_manifest(
                    {
                        "completed": False,
                        "stalled": False,
                        "remaining": [],
                        "answered": False,
                        "created": sorted(created_files),
                        "modified": files_edited,
                        "any_tool_succeeded": any_tool_succeeded,
                        "summary": "[Cancelled by user]",
                    },
                    session_id,
                )
                yield r.warning("Request cancelled", session_id, code="CANCELLED")
                return
            nudge_step = max_steps - 5 if max_steps > 5 else max_steps - 1
            if iteration > 0 and iteration == nudge_step:
                messages.append({"role": "user", "content": MAX_STEPS_PROMPT})
                yield r.warning(MAX_STEPS_PROMPT, session_id, code="MAX_STEPS")

            token_info = self.context_manager.get_token_info(messages, model)
            if token_info.percent >= self.config.context_compaction_threshold:
                async for ev in self._compact(session_id, history, messages):
                    yield ev
                messages = self._rebuild(
                    history, system_prompt, prompt, model, plan_context, session_id, mode, repo_map
                )
                if self.context_manager.is_context_exhausted(messages, model):
                    yield r.error(
                        "Context exhausted even after summarization",
                        session_id,
                        code="CONTEXT_EXHAUSTED",
                        action="retry",
                        hint="Start a new session to free up context.",
                    )
                    return

            iteration += 1
            stream_state = StreamState()
            context_exceeded = False
            turn_errored = False
            dispatch_messages, _ = prune_inflight_messages(messages, keep_latest_tools=6)
            # Sanitize assistant messages that have empty content and no tool_calls.
            # Providers (OpenRouter, OpenAI) reject requests containing such turns
            # with "model output must contain either output text or tool calls".
            # These arise from reasoning-only turns, rate-limit retry truncations,
            # or iterations where the assistant turn was dup-skipped. Replace with
            # a minimal placeholder that preserves the conversation structure.
            sanitized_dispatch = []
            for _msg in dispatch_messages:
                if (
                    _msg.get("role") == "assistant"
                    and not (_msg.get("content") or "").strip()
                    and not _msg.get("tool_calls")
                ):
                    m_copy = dict(_msg)
                    m_copy["content"] = "..."
                    sanitized_dispatch.append(m_copy)
                else:
                    sanitized_dispatch.append(_msg)
            dispatch_messages = sanitized_dispatch
            # G5: pre-scan the dispatch history for native tool_calls that
            # reference a registered-but-not-yet-active tool and escalate those
            # BEFORE the provider call. Strict providers validate the request
            # against the offered function list, so a history that calls an
            # unseeded tool (e.g. file_delete from a prior session) would be
            # rejected before our post-parse escalation could ever run.
            if self.tool_registry and resolver:
                mode_available = set(self.tool_registry.list_tools_for_mode(mode))
                history_hits: list[str] = []
                for _msg in dispatch_messages:
                    for _tc in _msg.get("tool_calls") or []:
                        # Live native calls use OpenAI's {function:{name}}
                        # shape; persisted history uses the domain ToolCall
                        # {name} shape. Accept both.
                        if isinstance(_tc, dict):
                            _fname = (_tc.get("function") or {}).get("name") or _tc.get("name")
                        else:
                            _fname = getattr(_tc, "function", {}).get("name")
                        if _fname and _fname in mode_available:
                            history_hits.append(_fname)
                if history_hits:
                    promoted = resolver.request_tools(history_hits)
                    if promoted:
                        openai_tools = resolver.openai_tools(mode)
            async for event in stream_completion(
                self.provider,
                dispatch_messages,
                openai_tools,
                session_id,
                iteration,
                stream_state,
                tool_choice=tool_choice,
            ):
                if event.kind == EventKind.WARNING and event.data.get("context_exceeded"):
                    context_exceeded = True
                if event.kind == EventKind.ERROR:
                    turn_errored = True
                yield event
            if turn_errored:
                yield r.turn_manifest(
                    {
                        "completed": False,
                        "stalled": False,
                        "remaining": [],
                        "answered": False,
                        "created": sorted(created_files),
                        "modified": files_edited,
                        "any_tool_succeeded": any_tool_succeeded,
                        "summary": "[Turn ended with an error]",
                    },
                    session_id,
                )
                return
            if context_exceeded:
                yield r.warning(
                    "Context window exceeded, summarizing and retrying...",
                    session_id,
                    code="CONTEXT",
                )
                async for ev in self._compact(session_id, history, messages):
                    yield ev
                messages = self._rebuild(
                    history, system_prompt, prompt, model, plan_context, session_id, mode, repo_map
                )
                continue

            finish_reason = getattr(self.provider, "_last_finish_reason", FinishReason.STOP)
            last_finish_reason = finish_reason
            response_text = stream_state.response_text
            native_tool_calls = getattr(self.provider, "_last_native_tool_calls", [])
            clean_response, tool_calls = UnifiedResponseFormatter.process_response(
                response_text, native_tool_calls or None
            )

            if finish_reason == FinishReason.LENGTH:
                has_partial_tool = bool(
                    (native_tool_calls and len(native_tool_calls) > 0)
                    or (
                        not tool_calls
                        and response_text
                        and any(
                            marker in response_text
                            for marker in ("```tool", '{"tool"', "<tool_call>")
                        )
                    )
                )
                # Complete text-parsed tool calls are not partial — execute them
                # normally instead of discarding and re-prompting.
                if tool_calls and not has_partial_tool:
                    pass
                elif length_continuations < 5:
                    length_continuations += 1
                    logger.info(
                        "LLM output truncated (finish_reason=LENGTH) on iteration %d; continuing emission (continuation %d/5)",
                        iteration,
                        length_continuations,
                    )
                    if has_partial_tool:
                        content_to_append = (
                            response_text.strip()
                            if (response_text and response_text.strip())
                            else "[tool call truncated]"
                        )
                        messages.append({"role": "assistant", "content": content_to_append})
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "Your response was cut off before the tool call was complete. "
                                    "Please emit the tool call now."
                                ),
                            }
                        )
                    else:
                        pending_continuation_text = _merge_continuation(
                            pending_continuation_text, clean_response or response_text or ""
                        )
                        content_to_append = (
                            response_text.strip()
                            if (response_text and response_text.strip())
                            else "[response truncated]"
                        )
                        messages.append({"role": "assistant", "content": content_to_append})
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "Your response reached the token limit and was cut off. "
                                    "Please continue directly from where you left off without repeating any prior text."
                                ),
                            }
                        )
                    await asyncio.sleep(0)
                    continue
                else:
                    logger.warning(
                        "Reached maximum length continuations (%d) on iteration %d",
                        length_continuations,
                        iteration,
                    )
                    length_truncated = True
                    yield r.warning(
                        "Response reached output token limit and continuation cap was reached.",
                        session_id,
                        code="LENGTH_LIMIT",
                    )

            if pending_continuation_text:
                clean_response = _merge_continuation(pending_continuation_text, clean_response or "")
                pending_continuation_text = ""
                if finish_reason == FinishReason.STOP:
                    length_continuations = 0

            current_turn_emitted = False
            if (
                clean_response
                and not _is_degenerate_message(clean_response)
                and clean_response != self._last_emitted_message
            ):
                yield r.message_event(
                    clean_response, session_id, partial=False, iteration=iteration
                )
                self._last_emitted_message = clean_response
                current_turn_emitted = True
            if not tool_calls:
                # When the provider explicitly signals tool_calls as the stop
                # reason but the parser extracted nothing (e.g. streaming race,
                # malformed argument JSON, or a placeholder tool name), the model
                # intended to use a tool. Stopping here would silently swallow the
                # intent and produce a half-answer. Instead, append what we have
                # and continue so the model gets another chance to emit the call.
                if finish_reason == FinishReason.TOOL_CALLS:
                    logger.warning(
                        "finish_reason=tool_calls but no tool calls parsed for session %s "
                        "(iteration %d); continuing to let model retry",
                        session_id,
                        iteration,
                    )
                    content_to_append = (
                        response_text.strip()
                        if (response_text and response_text.strip())
                        else "[response truncated]"
                    )
                    messages.append({"role": "assistant", "content": content_to_append})
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Your response was cut off before the tool call was complete. "
                                "Please emit the tool call now."
                            ),
                        }
                    )
                    continue

                from server.agents.todo_state import get_todo_state

                todo = get_todo_state(session_id)
                has_active_todos = bool(
                    todo and any(e.status in ("pending", "in_progress") for e in todo.list())
                )

                if (
                    has_active_todos
                    and nudges < 2
                    and iteration < max_steps - 1
                ):
                    nudges += 1
                    active_tasks = (
                        [e for e in todo.list() if e.status in ("pending", "in_progress")]
                        if todo
                        else []
                    )
                    if active_tasks:
                        active_summary = ", ".join(f"{t.id}: {t.title}" for t in active_tasks[:3])
                        nudge_content = (
                            f"Please proceed with the task checklist (active: {active_summary}). "
                            "Execute the next step using the available tools."
                        )
                    else:
                        nudge_content = "Please proceed with the next step or task."
                    messages.append({"role": "assistant", "content": response_text or ""})
                    messages.append({"role": "user", "content": nudge_content})
                    continue

                # Silent no-tool turn: the model ended with no tool call AND
                # produced no message text (e.g. a reasoning-only trailer from
                # a reason-then-act model). That is NOT a final answer — the
                # user would receive nothing. Bounded continuation lets the
                # model emit its actual answer or next tool call.
                if (
                    not current_turn_emitted
                    and not self._last_emitted_message
                    and silent_continuations < 2
                ):
                    silent_continuations += 1
                    logger.info(
                        "No tool call and no emitted text on iteration %d; "
                        "continuing to let the model produce its answer (silent continuation %d/2)",
                        iteration,
                        silent_continuations,
                    )
                    messages.append({"role": "assistant", "content": response_text or ""})
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Your last turn ended without any response text or tool call. "
                                "Continue and provide your final answer to the user's request "
                                "now, or emit the next tool call."
                            ),
                        }
                    )
                    continue

                break  # emergent stop — purely model-dependent: no tool_calls => final answer (Pi Codex OpenCode invariant)

            mode_available: set[str] = set()
            blocked: list[str] = []
            if self.tool_registry:
                mode_available = set(self.tool_registry.list_tools_for_mode(mode))
                escalate: list[str] = []
                kept_calls: list[dict] = []
                for tc in tool_calls:
                    t_name = tc.get("tool")
                    if not t_name:
                        continue
                    if t_name not in mode_available:
                        if self.tool_registry.get(t_name) is not None:
                            # Registered, but not usable in the current mode.
                            # Surface it instead of silently promoting a schema
                            # that can never execute.
                            blocked.append(t_name)
                            continue
                    kept_calls.append(tc)
                    escalate.append(t_name)
                    if t_name == "get_tool_definition":
                        requested = (tc.get("params") or {}).get("tool_name")
                        # Only auto-promote tools the current mode actually
                        # permits; a mode-restricted schema would be filtered out
                        # of the delivered schemas anyway (G2).
                        if requested and requested in mode_available:
                            escalate.append(requested)
                tool_calls = kept_calls
                if blocked:
                    yield r.warning(
                        f"Tools not available in '{mode}' mode: {', '.join(sorted(set(blocked)))} "
                        "(registered but mode-restricted; call omitted).",
                        session_id,
                        code="MODE_RESTRICTED",
                    )
                if not tool_calls:
                    # Every call this turn was mode-blocked (or empty): record
                    # the assistant content, feed the rejection notice back so
                    # the model knows why nothing ran, then continue.
                    messages.append({"role": "assistant", "content": response_text or ""})
                    if blocked:
                        messages.append({"role": "user", "content": (
                            f"[Tool rejected] {', '.join(sorted(set(blocked)))} is not available in "
                            f"'{mode}' mode. Available tools for {mode}: "
                            f"{', '.join(sorted(mode_available))}."
                        )})
                    stall_count += 1
                    if stall_count >= 2:
                        stalled = True
                        break
                    continue
                # Batch-escalate every legitimate call at once so FIFO eviction
                # can never strand one tool of a multi-call turn (G3).
                resolver.request_tools(escalate)
            registered_tools = set(resolver.active_names())
            openai_tools = resolver.openai_tools(mode)

            valid_calls, invalid_calls = validate_tool_calls(tool_calls, registered_tools)
            if invalid_calls:
                yield r.warning(
                    f"Hallucinated tools ignored: {', '.join(str(tc.get('tool') or tc) for tc in invalid_calls)}",
                    session_id,
                    code="INVALID_TOOLS",
                )
            if not valid_calls:
                messages.append({"role": "assistant", "content": response_text or ""})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Tool calls for non-existent tools: "
                            f"{', '.join(str(tc.get('tool') or tc) for tc in invalid_calls)}. "
                            f"Available: {', '.join(sorted(registered_tools))}."
                        ),
                    }
                )
                stall_count += 1
                if stall_count >= 2:
                    stalled = True
                    break
                continue

            messages.append({"role": "assistant", "content": response_text or ""})
            # Surface mode-restricted calls now that the assistant content has
            # been recorded, preserving assistant -> user ordering.
            if blocked:
                available = (
                    ', '.join(sorted(mode_available))
                    if mode_available
                    else 'none (tool registry unavailable)'
                )
                messages.append({"role": "user", "content": (
                    f"[Tool rejected] {', '.join(sorted(set(blocked)))} is not available in "
                    f"'{mode}' mode. Available tools for {mode}: {available}."
                )})

            executed_any_call_this_turn = False
            has_rejected_call_this_turn = False
            turn_had_success = False
            skipped_dup_calls: list[str] = []
            for tc in valid_calls:
                tool_name = tc.get("tool")
                if not tool_name:
                    continue
                tool_params = normalize_file_params(tc.get("params", {}), tool_name)
                sig = (tool_name, _json_sig(tool_params))

                is_dup = sig in executed_calls
                has_substantive_answer = bool(
                    current_turn_emitted
                    and len((clean_response or "").strip()) >= SUMMARY_MIN_CHARS
                )

                if is_dup and has_substantive_answer:
                    from .loop import _params_label

                    label = _params_label(tool_params, tool_name)
                    tag = f"{tool_name}({label})" if label else tool_name
                    skipped_dup_calls.append(tag)
                    continue

                if sig == last_doom_sig:
                    doom_run += 1
                else:
                    doom_run = 1
                    last_doom_sig = sig
                if doom_run >= self._doom_threshold():
                    yield r.warning(
                        f"No new tool work for several consecutive iterations: the same tool call "
                        f"(same name and input) has repeated {doom_run} times in a row. "
                        "The turn is stopping so a human can approve or end it.",
                        session_id,
                        code="DOOM_LOOP",
                    )
                    doomed = True
                    break

                # file_read dedup runs BEFORE the silent is_dup-continue. A read
                # whose range is already covered this session (exact duplicate or
                # overlapping) is served straight from the read cache. Transparent
                # to the user (a normal tool_result fires) — only the LLM sees a
                # compact notice. This is what keeps the turn alive: an exact-duplicate
                # re-read of an unchanged file no longer terminates the turn early via
                # the "is_dup and has_substantive_answer" silent-skip path below.
                if tool_name == "file_read":
                    read_path = tool_params.get("path", "")
                    read_offset = max(0, int(tool_params.get("offset", 0) or 0))
                    read_limit = int(
                        tool_params.get("limit", DEFAULT_FILE_READ_LINES) or DEFAULT_FILE_READ_LINES
                    )
                    if read_path:
                        try:
                            abs_file = (Path(self.config.workspace_root) / read_path).resolve()
                            stat = abs_file.stat()
                        except OSError:
                            stat = None
                            abs_file = None
                        abs_path = str(abs_file) if abs_file is not None else ""
                        if abs_path and stat is not None and is_range_covered(
                            session_id, abs_path, read_offset, read_limit,
                            mtime_ns=stat.st_mtime_ns, size=stat.st_size,
                        ):
                            already_read = slice_served_count(
                                session_id,
                                abs_path,
                                read_offset,
                                read_limit,
                                stat.st_mtime_ns,
                                stat.st_size,
                            ) > 0
                            cached = get_cached_read(
                                session_id,
                                abs_path,
                                read_offset,
                                read_limit,
                                stat.st_mtime_ns,
                                stat.st_size,
                            )
                            if cached is not None:
                                detail = _param_detail(tool_params)
                                yield _emit_progress_running(tool_name, detail)
                                yield r.tool_call(tool_name, tool_params, session_id)
                                metadata = build_tool_metadata(
                                    tool_name, tool_params, ToolResult(success=True, output=cached), 0, self.config.workspace_root
                                )
                                yield r.tool_result(
                                    tool_name,
                                    True,
                                    session_id,
                                    output=cached,
                                    metadata=metadata,
                                )
                                yield _emit_progress(tool_name, True, detail)
                                executed_calls.add(sig)
                                executed_call_status[sig] = True
                                executed_any_call_this_turn = True
                                stall_count = 0
                                consecutive_failures = 0
                                turn_had_success = True
                                any_tool_succeeded = True
                                read_files.add(read_path)
                                record_read(session_id, read_path)
                                cached_result = ToolResult(
                                    success=True, output=cached, metadata=metadata
                                )
                                transcript_result = cached_result
                                content = format_tool_result(tool_name, transcript_result)
                                messages.append(
                                    {
                                        "role": "user",
                                        "content": content,
                                        "salvage_digest": "file_read: ok",
                                    }
                                )
                                continue
                        if stat is not None:
                            # Cache miss or stale: the file may have changed since the last
                            # read. Force execution even if is_dup is set — the LLM must be
                            # able to read files it just edited.
                            is_dup = False

                if is_dup:
                    from .loop import _params_label

                    prev_success = executed_call_status.get(sig, True)
                    label = _params_label(tool_params, tool_name)
                    tag = f"{tool_name}({label}) [failed]" if not prev_success else (f"{tool_name}({label})" if label else tool_name)
                    warn_msg = f"Tool '{tag}' already completed with identical params this turn; skipping."
                    yield r.warning(warn_msg, session_id, code="DUPLICATE_CALL")
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"Duplicate call blocked: this exact {tool_name} call already "
                                "ran this turn with identical parameters. Do not re-run it."
                            ),
                        }
                    )
                    has_rejected_call_this_turn = True
                    continue

                reject_msg = validate_tool_rejection(
                    tool_name, tool_params, created_files, self.config.workspace_root
                )
                if reject_msg:
                    has_rejected_call_this_turn = True
                    yield r.warning(
                        f"Tool '{tool_name}' rejected: {reject_msg}",
                        session_id,
                        code="REJECTED",
                    )
                    messages.append({"role": "user", "content": f"[Tool rejected] {reject_msg}"})
                    continue

                target = tool_params.get("filepath") or tool_params.get("path") or ""

                # Normalize both the check target and created_files keys to
                # resolved absolute paths so "./src/foo.py" and "src/foo.py"
                # cannot bypass the in-turn rewrite block.
                if target:
                    target_abs = str((Path(self.config.workspace_root) / target).resolve())
                else:
                    target_abs = target
                if tool_name == "file_write" and target and (target_abs in created_files or target in created_files or self._replay_write(session_id, tool_params)):
                    warn_msg = f"File rewrite blocked: '{target}' was already written this turn. Read it first, then use file_edit."
                    yield r.warning(warn_msg, session_id, code="REWRITE_BLOCKED")
                    messages.append({"role": "user", "content": warn_msg})
                    has_rejected_call_this_turn = True
                    continue

                if not getattr(self.config, "auto_overwrite", True) and tool_name == "file_write" and target:
                    resolved_p = (Path(self.config.workspace_root) / target).resolve()
                    if resolved_p.is_file() and not tool_params.get("overwrite"):
                        warn_msg = f"Tool 'file_write' overwrite denied: '{target}' already exists and auto_overwrite is disabled. To overwrite, specify overwrite=true."
                        yield r.warning(warn_msg, session_id, code="OVERWRITE_DENIED")
                        messages.append({"role": "user", "content": f"[Tool rejected] {warn_msg}"})
                        has_rejected_call_this_turn = True
                        continue
                elif getattr(self.config, "auto_overwrite", True) and tool_name == "file_write":
                    tool_params.setdefault("overwrite", True)

                if not getattr(self.config, "auto_risky", True) and tool_name == "file_delete" and target:
                    warn_msg = f"Tool 'file_delete' delete denied: '{target}' was not deleted because auto_risky is disabled."
                    yield r.warning(warn_msg, session_id, code="DELETE_DENIED")
                    messages.append({"role": "user", "content": f"[Tool rejected] {warn_msg}"})
                    has_rejected_call_this_turn = True
                    continue

                detail = _param_detail(tool_params)
                yield _emit_progress_running(tool_name, detail)
                yield r.tool_call(tool_name, tool_params, session_id)
                result, duration_ms = await execute_tool(
                    self.tool_registry,
                    tool_name,
                    tool_params,
                    self.config.workspace_root,
                    mode,
                    session_id=session_id,
                )
                if result.output and len(result.output) > MAX_TOOL_OUTPUT_BASELINE:
                    compacted_out, stats = compact_tool_output(result.output)
                    result.output = compacted_out
                    if stats.trimmed:
                        if not result.metadata:
                            result.metadata = {}
                        result.metadata["trim"] = {
                            "charsRemoved": stats.chars_removed,
                            "tokensSaved": stats.tokens_saved,
                            "reason": stats.reason,
                        }
                metadata = build_tool_metadata(
                    tool_name, tool_params, result, duration_ms, self.config.workspace_root
                )
                yield r.tool_result(
                    tool_name,
                    result.success,
                    session_id,
                    output=result.output or "",
                    error=result.error or "",
                    metadata=metadata,
                )
                yield _emit_progress(tool_name, result.success, detail)
                executed_calls.add(sig)
                executed_call_status[sig] = result.success
                executed_any_call_this_turn = True
                stall_count = 0
                if result.success:
                    turn_had_success = True
                    any_tool_succeeded = True
                    p = tool_params.get("filepath") or tool_params.get("path") or ""
                    if tool_name == "file_write" and p:
                        created_files.add(str((Path(self.config.workspace_root) / p).resolve()))
                        created_files.add(p)
                    if tool_name in ("file_write", "file_edit", "file_delete", "apply_patch"):
                        if p:
                            files_edited.append(p)
                            abs_p = str((Path(self.config.workspace_root) / p).resolve())
                            evict_file_cache(session_id, abs_p)
                            evict_file_cache(session_id, p)
                        if tool_name == "apply_patch" and result.metadata and "files" in result.metadata:
                            for f in result.metadata["files"]:
                                files_edited.append(f)
                                abs_f = str((Path(self.config.workspace_root) / f).resolve())
                                evict_file_cache(session_id, abs_f)
                                evict_file_cache(session_id, f)
                        executed_calls = {
                            s for s in executed_calls
                            if s[0] not in ("glob", "grep", "dir_list", "list_dir", "bash")
                        }
                    if tool_name == "file_read" and p:
                        read_files.add(p)
                        record_read(session_id, p)

                for ev in await post_execution_hooks(
                    tool_name, tool_params, result, self.config.workspace_root, session_id
                ):
                    yield ev

                content = format_tool_result(tool_name, result)
                if not result.success:
                    content += (
                        f"\nThe {tool_name} call failed - respond to the error above "
                        "rather than repeating the same call."
                    )
                if result.success and tool_name == "file_read" and p and session_id:
                    abs_p = str((Path(self.config.workspace_root) / p).resolve())
                    read_ranges = get_read_history(session_id, abs_p)
                    total = result.metadata.get("total_lines", "?")
                    if read_ranges:
                        ranges = ", ".join(
                            f"{o + 1}-{o + length}" for o, length in sorted(read_ranges)
                        )
                        content += (
                            f"\n[read receipt: '{p}' lines in context: {ranges}"
                            f" / {total} total. Re-read only unlisted ranges.]"
                        )
                msg_entry: dict[str, Any] = {
                    "role": "user",
                    "content": content,
                    "salvage_digest": f"{tool_name}: {'ok' if result.success else 'error'}",
                }
                if tool_name in ("glob", "grep") and result.success:
                    from server.toolkit.digest import format_tool_digest

                    msg_entry["digest"] = format_tool_digest(tool_name, tool_params, result)
                messages.append(msg_entry)
            if executed_any_call_this_turn or has_rejected_call_this_turn:
                if turn_had_success:
                    consecutive_failures = 0
                    nudges = 0
                else:
                    consecutive_failures += 1
                    if consecutive_failures >= reflimit:
                        yield r.error(
                            f"Too many errors ({consecutive_failures}).",
                            session_id,
                            code="REFLECTION_LIMIT",
                            recoverable=True,
                        )
                        return
            if doomed:
                break
            if not executed_any_call_this_turn:
                if has_rejected_call_this_turn:
                    continue
                # When the provider signals finish_reason=TOOL_CALLS, valid calls
                # were parsed, but every one was silently skipped as a duplicate,
                # the model is stuck re-deriving work already in the history. A
                # short transitional message ("I'll investigate…") must not be
                # treated as a final answer in this case — count it as a stall and
                # let the model try again with a reminder.
                # Note: this does NOT apply when finish_reason=STOP (text-parsed
                # tool calls), which is the AC-1 case where a real answer + a stray
                # dup should still produce a clean emergent stop.
                if finish_reason == FinishReason.TOOL_CALLS and valid_calls:
                    logger.info(
                        "All %d valid tool call(s) silently dup-skipped with "
                        "finish_reason=TOOL_CALLS for session %s (iteration %d); "
                        "counting as stall to prevent false emergent stop",
                        len(valid_calls),
                        session_id,
                        iteration,
                    )
                    stall_count += 1
                    if stall_count >= 2:
                        yield r.warning(
                            "No new tool work for several consecutive iterations; finalizing turn.",
                            session_id,
                            code="STALL",
                        )
                        stalled = True
                        break
                    dup_desc = (
                        f"the tool call(s): {', '.join(skipped_dup_calls)}"
                        if skipped_dup_calls
                        else "those tool calls"
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"Those actions ({dup_desc}) are already complete. "
                                "Do not repeat them. Synthesize and provide your final answer now "
                                "based on the information gathered."
                            ),
                        }
                    )
                    continue
                has_substantive_answer = bool(
                    current_turn_emitted
                    and len((clean_response or "").strip()) >= SUMMARY_MIN_CHARS
                )
                if has_substantive_answer:
                    from server.agents.todo_state import get_todo_state

                    todo = get_todo_state(session_id)
                    has_active_todos = bool(
                        mode != PLAN_MODE
                        and todo
                        and any(e.status in ("pending", "in_progress") for e in todo.list())
                    )
                    if (
                        has_active_todos
                        and nudges < 2
                        and iteration < max_steps - 1
                    ):
                        nudges += 1
                        active_tasks = (
                            [e for e in todo.list() if e.status in ("pending", "in_progress")]
                            if todo
                            else []
                        )
                        if active_tasks:
                            active_summary = ", ".join(f"{t.id}: {t.title}" for t in active_tasks[:3])
                            nudge_content = (
                                f"Please proceed with the task checklist (active: {active_summary}). "
                                "Execute the next step using the available tools."
                            )
                        else:
                            nudge_content = "Please proceed with the next step or task."
                        messages.append({"role": "user", "content": nudge_content})
                        continue
                    break
                stall_count += 1
                if stall_count >= 2:
                    yield r.warning(
                        "No new tool work for several consecutive iterations; finalizing turn.",
                        session_id,
                        code="STALL",
                    )
                    stalled = True
                    break

        if pending_continuation_text:
            if not self._last_emitted_message or len(pending_continuation_text) > len(self._last_emitted_message):
                self._last_emitted_message = pending_continuation_text
            pending_continuation_text = ""

        token_info = self.context_manager.get_token_info(messages, model)
        from server.agents.todo_state import get_todo_state

        todo = get_todo_state(session_id)
        has_pending_todos = bool(
            mode != PLAN_MODE
            and todo
            and any(e.status in ("pending", "in_progress", "blocked") for e in todo.list())
        )
        has_mutation = bool(created_files or files_edited)
        has_file_work = has_mutation
        # Purely model-dependent completion: no hard-coded length/mutation/citation
        # checks — harness is thin deterministic executor around emergent model signal
        # (Pi Codex OpenCode invariant: continue iff tool_calls present).
        substantive_answer = bool(
            self._last_emitted_message
            and len(self._last_emitted_message.strip()) >= SUMMARY_MIN_CHARS
        )
        # Salvage only for deterministic guards (stall/doom/length), not for
        # incomplete research — that is handled by the emergent nudge above.
        salvaged = False
        if (stalled or doomed or iteration >= max_steps) and len(
            (self._last_emitted_message or "").strip()
        ) < SUMMARY_MIN_CHARS:
            salvage_reason = "no recent progress" if stalled else "repetition limit"
            async for ev in self._salvage_final_answer(
                session_id=session_id,
                messages=messages,
                reason=salvage_reason,
                iteration=iteration,
            ):
                yield ev
            salvaged = True

        is_stalled = bool(stalled or doomed)
        is_length_truncated = bool(last_finish_reason == FinishReason.LENGTH or length_truncated)
        is_step_limited = bool(iteration >= max_steps)

        # Honest turn completion — purely model-dependent, thin harness:
        # Completed iff model finished without deterministic guard violation.
        # No hard-coded has_mutation/has_todo_success/substantive length check.
        if is_length_truncated or is_stalled or has_pending_todos or is_step_limited:
            completed = False
        else:
            completed = True

        if is_length_truncated:
            message = "Response truncated by token limit (finish_reason=length)"
        elif salvaged:
            message = "Request processed with best-effort summary"
        elif has_pending_todos:
            message = "Turn finished with active tasks remaining"
        elif is_stalled:
            message = "Turn stalled without progress"
        elif is_step_limited and not completed:
            message = "Turn reached maximum step limit"
        elif has_file_work:
            message = "Request processed successfully"
        else:
            message = "Turn finished"

        _scan = None
        if mode == PLAN_MODE:
            root = Path(self.config.workspace_root or ".")
            plan_exists = (root / "plan.md").is_file()
            todo_exists = (root / "todo.md").is_file()
            missing = []
            if not plan_exists:
                missing.append("plan.md")
            if not todo_exists:
                missing.append("todo.md")
            _scan = {
                "present": [p for p in ("plan.md", "todo.md") if (root / p).is_file()],
                "missing": missing,
                "plan_md": plan_exists,
                "todo_md": todo_exists,
            }
            if "plan.md" in missing and not (stalled or doomed):
                message += (
                    "\n[Not implemented] Plan artifact not written: plan.md. "
                    "The plan output above is a proposal only; run in plan mode "
                    "again to write plan.md."
                )

        elapsed_ms = max(1000, int((time.time() - start_time) * 1000))
        cum_usage: dict = getattr(self.provider, "_cumulative_usage", {})
        prompt_tokens = cum_usage.get("prompt_tokens") or token_info.used
        completion_tokens = cum_usage.get("completion_tokens") or max(
            0, token_info.used - prompt_tokens
        )
        is_estimated = cum_usage.get("total_tokens", 0) == 0
        run_total = cum_usage.get("total_tokens", 0) or token_info.used

        written = set(created_files) | set(files_edited)
        verified = bool(written and any(f in read_files for f in written))

        remaining_reasons = []
        if _scan and "plan.md" in _scan.get("missing", []):
            remaining_reasons.append("Plan artifacts not written: " + ", ".join(_scan["missing"]) + ".")
        if is_length_truncated:
            remaining_reasons.append("Response truncated by token limit.")
        if has_pending_todos:
            remaining_reasons.append("Active tasks remain on checklist.")

        manifest_data = {
            "completed": completed,
            "stalled": is_stalled,
            "remaining": remaining_reasons,
            "answered": substantive_answer or salvaged,
            "created": sorted(created_files),
            "modified": files_edited,
            "verified": verified,
            "any_tool_succeeded": any_tool_succeeded,
            "summary": self._last_emitted_message or "",
            "finish_reason": (
                last_finish_reason.value if hasattr(last_finish_reason, "value") else str(last_finish_reason)
            ),
        }
        if _scan:
            manifest_data["plan_artifacts"] = _scan

        yield r.turn_manifest(
            manifest_data,
            session_id,
        )
        success_event = r.success(
            message,
            session_id,
            iteration,
            {
                "used": token_info.used,
                "remaining": token_info.remaining,
                "total": token_info.total,
                "percent": round(token_info.percent, 3),
                "runTotal": run_total,
                "runPrompt": cum_usage.get("prompt_tokens", 0),
                "runCompletion": cum_usage.get("completion_tokens", 0),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "cached_tokens": cum_usage.get("cached_tokens", 0),
                "cache_creation_tokens": cum_usage.get("cache_creation_tokens", 0),
                "estimated": is_estimated,
                "windowEstimated": bool(
                    getattr(self.context_manager, "context_window_estimated", False)
                ),
            },
            elapsed_ms=elapsed_ms,
        )
        success_event.data["manifest"] = manifest_data
        success_event.data["completed"] = completed
        success_event.data["finish_reason"] = (
            last_finish_reason.value if hasattr(last_finish_reason, "value") else str(last_finish_reason)
        )
        success_event.data["truncated"] = is_length_truncated
        yield success_event

    def _doom_threshold(self) -> int:
        try:
            from server.config.constants import DOOM_LOOP_THRESHOLD

            return DOOM_LOOP_THRESHOLD
        except Exception:
            return 3

    def _replay_write(self, session_id: str, params: dict) -> bool:
        target = params.get("filepath") or params.get("path") or ""
        if not target:
            return False
        try:
            resolved_p = (Path(self.config.workspace_root) / target).resolve()
            if not resolved_p.is_file():
                return False
            content = params.get("content", "")
            raw = resolved_p.read_text(encoding="utf-8", errors="replace")
            if raw != content:
                return False
            return bool(is_identical_replay(session_id, target, content))
        except Exception:
            return False

    async def _maybe_summarize(
        self,
        history: list[Message],
        session_id: str,
        messages: list[dict],
        **kwargs: Any,
    ) -> AsyncIterator[Event]:
        async for ev in self._compact(session_id, history, messages):
            yield ev

    def _rebuild_messages(
        self,
        messages: list[dict],
        base_len: int,
        history: list[Message],
        system_prompt: str,
        prompt: str,
        model: str,
        plan_context: str = "",
        use_system_prompt: bool = True,
        repo_map: str | None = None,
        session_id: str = "",
        mode: str = BUILD_MODE,
        **kwargs: Any,
    ) -> list[dict]:
        from .compaction_service import compact_live_tail

        tail = [dict(m) for m in messages[base_len:]] if base_len < len(messages) else []
        compact_live_tail(tail)
        base = self.context_manager.build_messages(
            history,
            system_prompt,
            prompt,
            model,
            summary=self._summary,
            plan_block=plan_context,
            use_system_prompt=use_system_prompt,
            repo_map=repo_map,
            session_id=session_id,
            mode=mode,
        )
        return list(base) + tail

    async def _compact(self, session_id, history, messages) -> AsyncIterator[Event]:
        try:
            from .compaction_service import CompactionService, CompactionTrigger

            service = (
                self.compaction_service
                if self.compaction_service is not None
                else CompactionService(self.config, self.provider, self.context_manager)
            )
            emitted: list[Event] = []

            async def _emit(ev: Event) -> None:
                emitted.append(ev)

            outcome = await service.compact(
                session_id=session_id,
                history=history,
                messages=messages,
                trigger=CompactionTrigger.AUTOMATIC,
                reason="automatic",
                previous_summary=self._summary,
                emit=_emit,
            )
            if not outcome.failed and not outcome.skipped:
                self._summary = outcome.summary or self._summary
            for ev in emitted:
                yield ev
        except Exception as exc:
            logger.warning("Compaction failed: %s", exc)

    def _rebuild(
        self,
        history,
        system_prompt,
        prompt,
        model,
        plan_context,
        session_id,
        mode,
        repo_map,
    ) -> list[dict]:
        rebuilt = self.context_manager.build_messages(
            history,
            system_prompt,
            prompt,
            model,
            summary=self._summary,
            plan_block=plan_context,
            use_system_prompt=True,
            repo_map=repo_map,
            session_id=session_id,
            mode=mode,
        )
        rebuilt.append(
            {
                "role": "user",
                "content": "Continue if you have next steps, or stop and ask for clarification for how to proceed.",
            }
        )
        return [m for m in rebuilt if isinstance(m, dict)]


def _json_sig(params: dict) -> str:
    try:
        return json.dumps(params, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return str(params)
