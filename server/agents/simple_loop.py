from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator

from server.config.constants import (
    BUILD_MODE,
    MAX_STEPS_DEFAULT,
    MAX_STEPS_PROMPT,
)
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
from .context import ContextManager
from .llm_stream import StreamState, stream_completion
from .prompts import compose_system_context, default_template_sections
from .session_workspace import is_identical_replay, record_read

logger = logging.getLogger(__name__)


class SimpleLoop:
    """A minimal, emergent-termination turn loop.
    """

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
        self._last_emitted_message: str | None = None
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
        mode: str = BUILD_MODE,
        plan_context: str = "",
        model_override: str | None = None,
        repo_map: str | None = None,
    ) -> AsyncIterator[Event]:
        sequence = self.accept()
        self._last_emitted_message = None
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
    ) -> AsyncIterator[Event]:
        model = self.provider.model
        mode_config = AGENT_MODES.get(mode)
        allowed_tools = mode_config.allowed_tools if mode_config else None
        tool_choice = mode_config.tool_choice if mode_config else "auto"

        system_prompt = "\n\n".join(
            compose_system_context(
                default_template_sections(
                    mode=mode,
                    workspace_root=self.config.workspace_root,
                    max_context_tokens=self.config.max_context_tokens,
                )
            )
        )

        resolver = SchemaResolver(self.tool_registry, seed=build_mode_tool_seed(allowed_tools))
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
        any_tool_succeeded = False
        doom_run = 0
        last_doom_sig: tuple[str, str] | None = None
        max_steps = int(getattr(self.config, "agent_max_steps", 0) or MAX_STEPS_DEFAULT)

        while iteration < max_steps:
            if self.is_cancelled(sequence):
                yield r.warning("Request cancelled", session_id, code="CANCELLED")
                return
            if iteration > 0 and iteration % max(1, max_steps // 20) == 0:
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
            async for event in stream_completion(
                self.provider,
                messages,
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
            response_text = stream_state.response_text
            native_tool_calls = getattr(self.provider, "_last_native_tool_calls", [])
            clean_response, tool_calls = UnifiedResponseFormatter.process_response(
                response_text, native_tool_calls or None
            )

            if clean_response:
                yield r.message_event(
                    clean_response, session_id, partial=False, iteration=iteration
                )
                self._last_emitted_message = clean_response

            if finish_reason == FinishReason.LENGTH:
                continue
            if not tool_calls:
                break  # emergent stop

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
                continue

            messages.append({"role": "assistant", "content": response_text or ""})

            doomed = False
            for tc in valid_calls:
                tool_name = tc.get("tool")
                if not tool_name:
                    continue
                tool_params = normalize_file_params(tc.get("params", {}), tool_name)
                sig = (tool_name, _json_sig(tool_params))

                if sig == last_doom_sig:
                    doom_run += 1
                else:
                    doom_run = 1
                    last_doom_sig = sig
                if doom_run >= self._doom_threshold():
                    yield r.warning(
                        f"The same tool call (same name and input) has repeated {doom_run} "
                        "times in a row. The turn is stopping so a human can approve or end it.",
                        session_id,
                        code="DOOM_LOOP",
                    )
                    doomed = True
                    break

                if sig in executed_calls:
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"Duplicate call blocked: this exact {tool_name} call already "
                                "ran this turn with identical parameters. Do not re-run it."
                            ),
                        }
                    )
                    continue

                reject_msg = validate_tool_rejection(
                    tool_name, tool_params, created_files, self.config.workspace_root
                )
                if reject_msg:
                    yield r.warning(
                        f"Tool '{tool_name}' rejected: {reject_msg}",
                        session_id,
                        code="REJECTED",
                    )
                    messages.append({"role": "user", "content": f"[Tool rejected] {reject_msg}"})
                    continue

                if tool_name == "file_write" and self._replay_write(session_id, tool_params):
                    target = tool_params.get("filepath") or tool_params.get("path") or ""
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"File rewrite blocked: '{target}' was already written this "
                                "session with identical content. Read it first, then use file_edit."
                            ),
                        }
                    )
                    continue

                yield r.tool_call(tool_name, tool_params, session_id)
                result, duration_ms = await execute_tool(
                    self.tool_registry,
                    tool_name,
                    tool_params,
                    self.config.workspace_root,
                    mode,
                )
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
                executed_calls.add(sig)
                if result.success:
                    any_tool_succeeded = True
                    p = tool_params.get("filepath") or tool_params.get("path") or ""
                    if tool_name == "file_write" and p:
                        created_files.add(p)
                    if tool_name in ("file_write", "file_edit") and p:
                        files_edited.append(p)
                    if tool_name == "file_read" and p:
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
                messages.append(
                    {
                        "role": "user",
                        "content": content,
                        "digest": f"{tool_name}: {'ok' if result.success else 'error'}",
                    }
                )
            if doomed:
                break

        token_info = self.context_manager.get_token_info(messages, model)
        # A successful tool call (e.g. bash creating files) is real work even
        # when it isn't a tracked file_write/file_edit — never report "Turn
        # finished" (implying nothing happened) when a tool actually succeeded.
        has_file_work = bool(created_files or files_edited or any_tool_succeeded)
        completed = bool(has_file_work or iteration > 0 or self._last_emitted_message)
        message = "Request processed successfully" if has_file_work else "Turn finished"
        elapsed_ms = max(1000, int((time.time() - start_time) * 1000))
        cum_usage: dict = getattr(self.provider, "_cumulative_usage", {})
        prompt_tokens = cum_usage.get("prompt_tokens") or token_info.used
        completion_tokens = cum_usage.get("completion_tokens") or max(
            0, token_info.used - prompt_tokens
        )
        is_estimated = cum_usage.get("total_tokens", 0) == 0
        run_total = cum_usage.get("total_tokens", 0) or token_info.used

        yield r.turn_manifest(
            {
                "completed": completed,
                "created": sorted(created_files),
                "modified": files_edited,
                "any_tool_succeeded": any_tool_succeeded,
                "summary": self._last_emitted_message or "",
            },
            session_id,
        )
        yield r.success(
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
            content = params.get("content", "")
            return bool(is_identical_replay(session_id, target, content))
        except Exception:
            return False

    async def _compact(self, session_id, history, messages) -> AsyncIterator[Event]:
        try:
            from .compaction_service import CompactionService, CompactionTrigger

            service = CompactionService(self.config, self.provider, self.context_manager)
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
