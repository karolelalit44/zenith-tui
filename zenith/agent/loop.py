"""Agent loop — multi-step prompt → LLM → tool calls → response."""

from __future__ import annotations

import json
import logging
import time as _time
from typing import AsyncIterator

from zenith.config.settings import AppSettings
from zenith.core.errors import ZenithError, MaxIterationsError
from zenith.core.events import Event, EventKind
from zenith.core.message import Message
from zenith.providers.base import BaseProvider
from zenith.providers.parser import UnifiedResponseFormatter
from zenith.providers import responder as r
from zenith.tools.base import ToolResult
from zenith.tools.registry import ToolRegistry
from .context import ContextManager
from .prompts import build_system_prompt
from zenith.session.history import HistoryManager

logger = logging.getLogger(__name__)

FILE_MODIFY_TOOLS = {"file_write", "file_edit", "file_delete"}


from zenith.tools.param_normalizer import normalize_file_params


def _format_tool_result(tool_name: str, result: ToolResult, max_output: int = 10000) -> str:
    """Format a tool result for LLM consumption."""
    status = "SUCCESS" if result.success else "FAILED"
    lines = [f"[Tool: {tool_name} | Status: {status}]"]

    if result.output:
        output = result.output
        if len(output) > max_output:
            output = output[:max_output] + f"\n... (truncated, {len(result.output)} total chars)"
        lines.append(output)

    if result.error:
        lines.append(f"Error: {result.error}")

    if result.metadata:
        meta_str = json.dumps(result.metadata)
        if len(meta_str) < 200:
            lines.append(f"Metadata: {meta_str}")

    return "\n".join(lines)


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
    ) -> AsyncIterator[Event]:
        """Process a user prompt through multi-step LLM + tool loop."""
        system_prompt = build_system_prompt(
            self.config.workspace_root, mode, self._get_tool_names(),
            skills_section=skills_section,
        )
        model = self.provider.model
        workspace_root = self.config.workspace_root

        logger.info(
            "PROMPT START session=%s mode=%s model=%s provider=%s workspace=%s",
            session_id, mode, model, self.provider.name, workspace_root,
        )
        logger.info("PROMPT prompt_len=%d, history_len=%d", len(prompt), len(history))
        logger.info("PROMPT system_prompt_len=%d, tools=%s", len(system_prompt), self._get_tool_names())

        messages = self.context_manager.build_messages(
            history, system_prompt, prompt, model, summary=self._summary
        )
        logger.info("PROMPT context_messages=%d, total_chars=%d", len(messages), sum(len(m.get("content", "") or "") for m in messages))

        yield r.thinking(f"Processing your request in {mode} mode...", session_id)

        # Check if summarization is needed
        if self.context_manager.should_summarize(messages, model):
            logger.info("SUMMARIZE starting for session=%s", session_id)
            yield r.summary("summarize", "Context approaching limit, summarizing...", session_id)
            try:
                history_mgr = HistoryManager(self.config, self.provider)
                self._summary = await history_mgr.summarize(history, model)
                logger.info("SUMMARIZE complete for session=%s (summary_len=%d)", session_id, len(self._summary or ""))
                messages = self.context_manager.build_messages(
                    history, system_prompt, prompt, model, summary=self._summary
                )
                yield r.summary("complete", "Context summarized", session_id)
            except Exception as e:
                logger.warning("SUMMARIZE failed for session=%s: %s", session_id, e)
                yield r.warning(f"Summarization failed: {e}", session_id)

        # Multi-step tool loop
        iteration = 0
        max_iterations = self.config.tools.max_iterations
        full_response = ""

        while iteration < max_iterations:
            iteration += 1
            logger.info("Agent turn %d/%d for session %s (model=%s, provider=%s)", iteration, max_iterations, session_id, model, self.provider.name)

            # Stream LLM response tokens as partial message events (buffering tool blocks)
            response_text = ""
            suppress_stream = False
            try:
                async for evt in r.stream_tokens(self.provider.stream(messages), session_id):
                    if evt.kind == EventKind.THINKING:
                        yield evt
                        continue

                    if evt.kind == EventKind.MESSAGE and evt.data.get("partial"):
                        token = evt.data.get("text", "")
                        response_text += token
                        lowered = response_text.lower()
                        if "```tool" in lowered or "```json" in lowered or '{"tool":' in lowered:
                            suppress_stream = True

                    if not suppress_stream:
                        yield evt
            except ZenithError:
                raise
            except Exception as e:
                logger.error("LLM stream error on turn %d: %s", iteration, e, exc_info=True)
                yield r.error(str(e), session_id)
                return

            full_response += response_text

            # Finalize visible message text and extract tool calls using UnifiedResponseFormatter
            clean_response, tool_calls = UnifiedResponseFormatter.process_response(response_text)
            if clean_response:
                yield r.message_event(clean_response, session_id, partial=False)

            logger.info("LLM turn %d response clean_len=%d, tool_calls_count=%d", iteration, len(clean_response), len(tool_calls))

            if not tool_calls:
                if not clean_response and not full_response:
                    logger.warning("LLM returned empty response on turn %d", iteration)
                    yield r.error(
                        "Model returned empty response. Please try another model or retry.",
                        session_id, code="EMPTY_RESPONSE", recoverable=True,
                    )
                break

            # Execute tools
            if self.tool_registry is None:
                logger.error("Tool calls detected but no tool registry available")
                yield r.error("Tool calls detected but no tool registry available", session_id)
                break

            # Emit progress
            yield r.progress(
                int((iteration / max_iterations) * 100),
                f"Executing {len(tool_calls)} tool(s)...",
                session_id, iteration,
            )

            # Add assistant message (with tool calls) to context
            messages.append({"role": "assistant", "content": response_text})

            for tc in tool_calls:
                tool_name = tc["tool"]
                tool_params = normalize_file_params(tc.get("params", {}))
                if tool_name == "file_write" and "overwrite" not in tool_params:
                    tool_params["overwrite"] = True
                logger.info("Executing tool '%s' with params: %s", tool_name, json.dumps(tool_params))

                # Emit analysis summary event only for non-file and non-terminal tools
                if tool_name not in FILE_MODIFY_TOOLS and tool_name not in ("bash", "terminal"):
                    yield r.analysis(tool_name, session_id, tool_params)

                start_ts = _time.monotonic()
                result = await self.tool_registry.execute(
                    tool_name, tool_params, workspace_root, mode
                )
                duration_ms = int((_time.monotonic() - start_ts) * 1000)

                logger.info("Tool '%s' completed: success=%s, output_len=%d, error=%s", tool_name, result.success, len(result.output or ""), result.error)

                if result.success:
                    # Emit terminal event for shell command execution
                    if tool_name in ("bash", "terminal"):
                        cmd = str(tool_params.get("command") or "")
                        out_lines = result.output.split("\n") if result.output else []
                        yield r.terminal_event(cmd, out_lines, duration_ms, session_id)

                    # Emit file change events for file-modifying tools
                    elif tool_name in FILE_MODIFY_TOOLS:
                        file_kind = {
                            "file_write": EventKind.FILE_CREATE,
                            "file_edit": EventKind.FILE_EDIT,
                            "file_delete": EventKind.FILE_DELETE,
                        }.get(tool_name, EventKind.FILE_EDIT)

                        target_path = tool_params.get("filepath") or tool_params.get("path") or tool_params.get("file_path") or ""
                        file_content = tool_params.get("content", "")

                        yield r.file_event(file_kind, target_path, file_content, session_id)

                    else:
                        yield r.tool_result(tool_name, True, session_id, result.output or "", "")
                else:
                    # Emit structured error event for tool failure
                    err_msg = result.error or f"Tool '{tool_name}' execution failed"
                    yield r.error(err_msg, session_id, code=f"TOOL_ERROR_{tool_name.upper()}", recoverable=True)
                    yield r.warning(
                        f"Tool '{tool_name}' failed. Consider trying a different approach or parameters.",
                        session_id,
                    )

                # Add tool result to messages
                tool_result_text = _format_tool_result(tool_name, result, self.config.tools.max_tool_output)
                messages.append({"role": "user", "content": tool_result_text})

        else:
            # Max iterations exceeded
            yield r.error(f"Max iterations ({max_iterations}) exceeded", session_id, code="MAX_ITERATIONS")
            return

        # Token info
        token_info = self.context_manager.get_token_info(messages, model)
        logger.info(
            "PROMPT END session=%s iterations=%d response_chars=%d tokens_used=%d tokens_total=%d",
            session_id, iteration, len(full_response), token_info.used, token_info.total,
        )

        yield r.success("Request processed successfully", session_id, iteration, {
            "used": token_info.used,
            "remaining": token_info.remaining,
            "total": token_info.total,
            "percent": round(token_info.percent, 3),
        })

    def _get_tool_names(self) -> list[str]:
        """Get list of available tool names."""
        if self.tool_registry:
            return self.tool_registry.list_tools()
        return []
