"""Agent loop — multi-step prompt → LLM → tool calls → response."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time as _time
from typing import AsyncIterator, Awaitable, Callable

from zenith.config.settings import AppSettings
from zenith.core.errors import ZenithError, MaxIterationsError, RateLimitError, ProviderError
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


def _schemas_to_openai_tools(schemas: list[dict]) -> list[dict]:
    """Convert internal tool schemas to OpenAI tools format for native function calling."""
    tools = []
    for s in schemas:
        schema = s.get("schema", {})
        tools.append({
            "type": "function",
            "function": {
                "name": s["name"],
                "description": s.get("description", ""),
                "parameters": schema,
            }
        })
    return tools

# Patterns that indicate the model used placeholder content instead of real content
_PLACEHOLDER_PATTERNS_RAW = [
    (r"\[[\w\s]*(?:CONTENT|FILE|CODE|PASTE|INSERT|TODO|DESIRED|UPDATED|REPLACE|YOUR)[\w\s]*\]", "placeholder pattern"),
    (r"\bYOUR_[\w_]+_HERE\b", "YOUR_..._HERE placeholder"),
    (r"\b(?:PLACEHOLDER|TODO|FIXME|XXX|TBD)\b", "TODO/placeholder marker"),
    (r"\[HTML\]", "HTML placeholder"),
    (r"\[ACTUAL_", "ACTUAL_ placeholder"),
    (r"\[Current ", "Current... placeholder"),
    (r"\[UPDATED_", "UPDATED_ placeholder"),
]
_PLACEHOLDER_RE = re.compile("|".join(p for p, _ in _PLACEHOLDER_PATTERNS_RAW), re.IGNORECASE)

# Reflection loop: errors feed back to LLM via conversation context.
# The LLM sees tool errors and retries with different approaches.
# Max iterations is the only hard limit (set via config).
REFLECTION_ERROR_LIMIT = 6

# Patterns indicating interactive commands that will fail in non-interactive bash
_INTERACTIVE_CMD_PATTERNS = re.compile(
    r"\binput\s*\(|"
    r"python\s+-[im]|"
    r"\bpdb\b|"
    r"\bgetpass\b|"
    r"\bread\s+-[srp]\b",
    re.IGNORECASE,
)


def _detect_placeholders(params: dict) -> str | None:
    """Check if tool params contain placeholder content. Returns description of issue or None."""
    for key in ("content", "old_content", "new_content"):
        val = params.get(key, "")
        if isinstance(val, str) and val:
            m = _PLACEHOLDER_RE.search(val)
            if m:
                return f"Parameter '{key}' contains placeholder content ({m.group(0)}). Provide the actual content."
    return None


# Patterns indicating the model has completed the task and is summarizing
_COMPLETION_SIGNALS = re.compile(
    r"(?:task\s+(?:is\s+)?(?:complete|done|finished)|"
    r"everything\s+is\s+(?:set|ready|done|complete)|"
    r"all\s+(?:steps?\s+)?(?:are\s+)?(?:complete|done|finished)|"
    r"summary\s*:|here(?:'s|\s+is)\s+(?:a\s+)?(?:summary|what\s+i\s+did)|"
    r"in\s+summary|to\s+sum(?:marize|mary)|"
    r"the\s+(?:code|file|script)\s+has\s+been|"
    r"(?:created|written|generated|implemented)\s+(?:successfully|complete))",
    re.IGNORECASE,
)

# Python file extension for syntax checking
_PYTHON_EXT_RE = re.compile(r"\.py$")


from zenith.tools.param_normalizer import normalize_file_params


def _check_python_syntax(command: str, workspace_root: str) -> str | None:
    """Pre-check: if command runs a .py file, verify syntax first. Returns error message or None."""
    # Match: python <file.py>, python3 <file.py>, py <file.py>
    m = re.match(r"^(?:python3?|py)\s+([\w./\\-]+\.py)\s*(.*)", command.strip(), re.IGNORECASE)
    if not m:
        return None
    filepath = m.group(1)
    # Resolve relative to workspace
    from pathlib import Path
    full = Path(workspace_root) / filepath
    if not full.exists():
        return None  # File doesn't exist yet — let bash handle the error
    try:
        import py_compile
        py_compile.compile(str(full), doraise=True)
    except py_compile.PyCompileError as e:
        return (
            f"Python syntax error in {filepath}: {e}. "
            f"Fix the syntax before running. Use file_read to check the file, then file_edit to fix it."
        )
    return None


def _detect_interactive_command(command: str) -> str | None:
    """Detect commands that use input() or other interactive features. Returns warning or None."""
    if _INTERACTIVE_CMD_PATTERNS.search(command):
        return (
            "This command uses interactive input (input(), pdb, etc.) which will fail "
            "in non-interactive bash. Use echo 'value' | python script.py or rewrite "
            "the script to accept command-line arguments instead."
        )
    return None


# Patterns for stripping cd prefixes (workspace_root is already the cwd)
_CD_PREFIX_RE = re.compile(
    r"^(?:cd\s+[\"']?[^\"';|&]+[\"']?\s*(?:&&\s*|;\s*|)\s*)",
    re.IGNORECASE,
)


def _strip_cd_prefix(command: str) -> str:
    """Strip 'cd /some/path && ' or 'cd /some/path; ' prefix from commands.
    
    The workspace_root is already set as the working directory for subprocesses,
    so cd is redundant and often wrong (e.g. Linux 'cd /d' on Windows).
    """
    m = _CD_PREFIX_RE.match(command.strip())
    if m:
        stripped = command.strip()[m.end():].strip()
        if stripped:
            return stripped
    return command


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


def _build_tool_metadata(tool_name: str, tool_params: dict, result: ToolResult, duration_ms: int) -> dict:
    """Build tool-specific metadata for tool_result events."""
    if tool_name in ("bash", "terminal"):
        cmd = str(tool_params.get("command") or "")
        out_lines = result.output.split("\n") if result.output else []
        exit_code = result.metadata.get("exit_code", 0) if result.metadata else 0
        return {
            "command": cmd,
            "output_lines": out_lines,
            "duration_ms": duration_ms,
            "exit_code": exit_code,
        }
    elif tool_name == "file_write":
        return {
            "path": tool_params.get("filepath") or tool_params.get("path") or "",
            "content": tool_params.get("content", ""),
            "match": "exact",
        }
    elif tool_name == "file_edit":
        return {
            "path": tool_params.get("filepath") or tool_params.get("path") or "",
            "old_content": tool_params.get("old_content", ""),
            "new_content": tool_params.get("new_content", ""),
            "match": "exact",
        }
    elif tool_name == "file_delete":
        return {
            "path": tool_params.get("filepath") or tool_params.get("path") or "",
        }
    elif tool_name == "file_read":
        return {
            "path": tool_params.get("filepath") or tool_params.get("path") or "",
        }
    else:
        return {}


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
        confirm_callback: Callable[[str, str, str], Awaitable[bool]] | None = None,
    ) -> AsyncIterator[Event]:
        """Process a user prompt through multi-step LLM + tool loop.

        Args:
            confirm_callback: Async function(tool_name, reason, risk_level) -> bool.
                Returns True if user approves, False if denied. None means auto-approve.
        """
        system_prompt = build_system_prompt(
            self.config.workspace_root, mode, self._get_tool_schemas(),
            skills_section=skills_section,
            max_context_tokens=self.config.max_context_tokens,
        )
        model = self.provider.model
        workspace_root = self.config.workspace_root
        registered_tools = set(self.tool_registry.list_tools()) if self.tool_registry else set()

        # Build OpenAI tools format for native function calling (models that support it)
        openai_tools = _schemas_to_openai_tools(self._get_tool_schemas())

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
            yield r.warning("Context approaching limit, summarizing...", session_id)
            try:
                history_mgr = HistoryManager(self.config, self.provider)
                self._summary = await history_mgr.summarize(history, model)
                logger.info("SUMMARIZE complete for session=%s (summary_len=%d)", session_id, len(self._summary or ""))
                messages = self.context_manager.build_messages(
                    history, system_prompt, prompt, model, summary=self._summary
                )
                yield r.warning("Context summarized", session_id)
            except Exception as e:
                logger.warning("SUMMARIZE failed for session=%s: %s", session_id, e)
                yield r.warning(f"Summarization failed: {e}", session_id)

        # Multi-step tool loop
        iteration = 0
        max_iterations = self.config.tools.max_iterations
        full_response = ""
        reflection_errors = 0
        recovery_hint_shown = False
        created_files: set[str] = set()  # Track files created this session for self-delete protection
        task_completed = False  # Track if model has signaled task completion
        post_completion_iterations = 0  # Limit iterations after task completion signal
        POST_COMPLETION_LIMIT = 2  # Max extra iterations after completion signal

        try:
            while iteration < max_iterations:
                # Stop if task completed and post-completion limit reached
                if task_completed and post_completion_iterations >= POST_COMPLETION_LIMIT:
                    logger.info("POST-COMPLETION LIMIT reached after %d extra iterations, stopping", post_completion_iterations)
                    break

                iteration += 1
                if task_completed:
                    post_completion_iterations += 1
                recovery_hint_shown = False  # Reset per iteration
                logger.info("Agent turn %d/%d for session %s (model=%s, provider=%s)", iteration, max_iterations, session_id, model, self.provider.name)

                # Stream LLM response tokens as partial message events
                # On retryable errors, finalize the current partial message and retry
                response_text = ""
                full_response_before_stream = full_response
                max_stream_retries = 2
                stream_succeeded = False

                for stream_attempt in range(max_stream_retries + 1):
                    reasoning_buffer = ""
                    try:
                        async for content, reasoning in self.provider.stream(messages, tools=openai_tools):
                            if reasoning:
                                reasoning_buffer += reasoning
                            if content:
                                if reasoning_buffer:
                                    yield r.thinking(reasoning_buffer, session_id)
                                    reasoning_buffer = ""
                                response_text += content
                                yield r.message_event(content, session_id, partial=True)
                        if reasoning_buffer:
                            yield r.thinking(reasoning_buffer, session_id)
                        stream_succeeded = True
                        break  # Stream completed successfully

                    except ZenithError:
                        raise
                    except asyncio.CancelledError:
                        raise
                    except RateLimitError as e:
                        if stream_attempt == max_stream_retries or not e.recoverable:
                            logger.error("Stream rate limit (no more retries): %s", e)
                            yield r.error(str(e), session_id, code=e.code, recoverable=False)
                            return
                        logger.warning("Stream retry %d/%d after rate limit: %s", stream_attempt + 1, max_stream_retries, e)
                        # Finalize partial message before retry so frontend doesn't concatenate
                        if response_text:
                            yield r.message_event(response_text, session_id, partial=False)
                            full_response += response_text
                            response_text = ""
                        yield r.thinking(f"Rate limited, retrying in {int(e.retry_after or 2)}s...", session_id)
                        await asyncio.sleep(e.retry_after or (2 ** stream_attempt))
                    except ProviderError as e:
                        if not e.recoverable:
                            logger.error("Stream provider error (non-recoverable): %s", e)
                            yield r.error(str(e), session_id, code=e.code, recoverable=False)
                            return
                        if stream_attempt == max_stream_retries:
                            logger.error("Stream provider error (exhausted retries): %s", e)
                            yield r.error(str(e), session_id, code=e.code, recoverable=True)
                            return
                        logger.warning("Stream retry %d/%d after provider error: %s", stream_attempt + 1, max_stream_retries, e)
                        if response_text:
                            yield r.message_event(response_text, session_id, partial=False)
                            full_response += response_text
                            response_text = ""
                        yield r.thinking("Retrying after provider error...", session_id)
                        await asyncio.sleep(2 ** stream_attempt)
                    except Exception as e:
                        logger.error("LLM stream error on turn %d: %s", iteration, e, exc_info=True)
                        yield r.error(str(e), session_id)
                        return

                if not stream_succeeded:
                    return

                full_response += response_text

                # Finalize visible message text and extract tool calls using UnifiedResponseFormatter
                # Include native tool_calls from OpenAI function calling if available
                native_tool_calls = getattr(self.provider, '_last_native_tool_calls', [])
                clean_response, tool_calls = UnifiedResponseFormatter.process_response(response_text, native_tool_calls or None)
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

                # Validate tool names and filter out hallucinated ones
                valid_calls = []
                invalid_names = []
                for tc in tool_calls:
                    tool_name = tc.get("tool", "")
                    if tool_name in registered_tools:
                        valid_calls.append(tc)
                    else:
                        invalid_names.append(tool_name)

                if invalid_names:
                    warning_msg = f"Hallucinated tools ignored: {', '.join(invalid_names)}. Available tools: {', '.join(sorted(registered_tools))}"
                    logger.warning("TOOL VALIDATION: %s", warning_msg)
                    yield r.warning(warning_msg, session_id)

                if not valid_calls:
                    feedback = (
                        f"Your response contained tool calls for non-existent tools: {', '.join(invalid_names)}. "
                        f"The ONLY available tools are: {', '.join(sorted(registered_tools))}. "
                        f"Please use only the tools listed above. Try again."
                    )
                    messages.append({"role": "assistant", "content": response_text})
                    messages.append({"role": "user", "content": feedback})
                    yield r.warning(feedback, session_id)
                    continue

                # Emit progress only for multi-step operations (3+ iterations)
                if max_iterations >= 3:
                    yield r.progress(
                        int((iteration / max_iterations) * 100),
                        f"Executing {len(valid_calls)} tool(s)...",
                        session_id, iteration,
                    )

                # Add assistant message (with tool calls) to context
                messages.append({"role": "assistant", "content": response_text})

                for tc in valid_calls:
                    tool_name = tc["tool"]
                    tool_params = normalize_file_params(tc.get("params", {}))

                    # Validate for placeholder content before execution
                    placeholder_issue = _detect_placeholders(tool_params)
                    if placeholder_issue:
                        yield r.warning(f"Tool '{tool_name}' rejected: {placeholder_issue}", session_id)
                        messages.append({"role": "user", "content": f"[Tool rejected] {placeholder_issue} Please provide the actual content, not a placeholder."})
                        reflection_errors += 1
                        if reflection_errors >= REFLECTION_ERROR_LIMIT:
                            yield r.error(
                                f"Too many errors ({reflection_errors}). The model appears stuck.",
                                session_id, code="REFLECTION_LIMIT", recoverable=True,
                            )
                            return
                        continue

                    # Validate file_edit has non-empty old_content
                    if tool_name == "file_edit" and not tool_params.get("old_content"):
                        yield r.warning(f"Tool 'file_edit' rejected: old_content cannot be empty. Use file_read first to get the current content.", session_id)
                        messages.append({"role": "user", "content": "[Tool rejected] old_content is empty. You MUST use file_read first to get the exact content of the file, then use file_edit with the actual old_content you want to replace."})
                        reflection_errors += 1
                        if reflection_errors >= REFLECTION_ERROR_LIMIT:
                            yield r.error(
                                f"Too many errors ({reflection_errors}). The model appears stuck.",
                                session_id, code="REFLECTION_LIMIT", recoverable=True,
                            )
                            return
                        continue

                    # Check command safety before execution (#13)
                    if tool_name in ("bash", "terminal") and confirm_callback:
                        from zenith.tools.command_safety import assess_command
                        command = tool_params.get("command", "")
                        assessment = assess_command(command)
                        if assessment.is_risky:
                            logger.info("RISKY COMMAND: '%s' reason=%s level=%s", command, assessment.reason, assessment.risk_level)
                            try:
                                approved = await confirm_callback(tool_name, assessment.reason, assessment.risk_level)
                            except Exception:
                                approved = False
                            if not approved:
                                yield r.warning(
                                    f"Command denied by user: {command} ({assessment.reason})",
                                    session_id,
                                )
                                # Add denial to context so model knows
                                messages.append({"role": "user", "content": f"[Permission denied] Command was denied by user: {command}. Reason: {assessment.reason}. Please try a safer alternative."})
                                continue

                    # Pre-check: Python syntax validation before running scripts
                    if tool_name in ("bash", "terminal"):
                        command = tool_params.get("command", "")
                        # Auto-strip cd prefixes — workspace_root is already set as cwd
                        command = _strip_cd_prefix(command)
                        if command != tool_params.get("command", ""):
                            tool_params["command"] = command
                            logger.info("Stripped cd prefix, command now: %s", command)
                        syntax_err = _check_python_syntax(command, workspace_root)
                        if syntax_err:
                            yield r.warning(syntax_err, session_id)
                            messages.append({"role": "user", "content": f"[Syntax error detected] {syntax_err}"})
                            reflection_errors += 1
                            continue

                    # Pre-check: Detect interactive commands that will fail
                    if tool_name in ("bash", "terminal"):
                        command = tool_params.get("command", "")
                        interactive_err = _detect_interactive_command(command)
                        if interactive_err:
                            yield r.warning(interactive_err, session_id)
                            messages.append({"role": "user", "content": f"[Interactive command detected] {interactive_err}"})
                            reflection_errors += 1
                            continue

                    # Self-delete protection: warn if model tries to delete a file it just created
                    if tool_name == "file_delete":
                        target = tool_params.get("filepath") or tool_params.get("path") or ""
                        if target in created_files:
                            yield r.warning(
                                f"Refusing to delete '{target}' — this file was created in the current session. "
                                f"Only delete files that existed before this session.",
                                session_id,
                            )
                            messages.append({
                                "role": "user",
                                "content": f"[Tool rejected] Cannot delete '{target}' — it was created during this session. "
                                           f"You just created this file. Deleting your own work is not allowed.",
                            })
                            reflection_errors += 1
                            continue

                    logger.info("Executing tool '%s' with params: %s", tool_name, json.dumps(tool_params))

                    # Emit tool_call event before execution
                    yield r.tool_call(tool_name, tool_params, session_id)

                    start_ts = _time.monotonic()
                    result = await self.tool_registry.execute(
                        tool_name, tool_params, workspace_root, mode
                    )
                    duration_ms = int((_time.monotonic() - start_ts) * 1000)

                    # Auto-retry file_write with overwrite=True if file already exists
                    if (tool_name == "file_write" and not result.success
                            and "already exists" in (result.error or "")
                            and not tool_params.get("overwrite")):
                        tool_params["overwrite"] = True
                        logger.info("Auto-retrying file_write with overwrite=True")
                        start_ts = _time.monotonic()
                        result = await self.tool_registry.execute(
                            tool_name, tool_params, workspace_root, mode
                        )
                        duration_ms = int((_time.monotonic() - start_ts) * 1000)

                    logger.info("Tool '%s' completed: success=%s, output_len=%d, error=%s", tool_name, result.success, len(result.output or ""), result.error)

                    # Build metadata and emit tool_result event
                    metadata = _build_tool_metadata(tool_name, tool_params, result, duration_ms)
                    yield r.tool_result(
                        tool_name, result.success, session_id,
                        output=result.output or "",
                        error=result.error or "",
                        metadata=metadata,
                    )

                    if not result.success:
                        reflection_errors += 1
                        err_msg = result.error or f"Tool '{tool_name}' execution failed"

                        # Emit error event for tool failure
                        yield r.error(err_msg, session_id, code=f"TOOL_ERROR_{tool_name.upper()}", recoverable=True)

                        # Reflection: feed error back to LLM so it can try a different approach
                        messages.append({
                            "role": "user",
                            "content": f"[Tool error] {tool_name} failed: {err_msg}. Analyze what went wrong and try a different approach.",
                        })

                        if tool_name == "file_edit" and "old_content cannot be empty" in (result.error or ""):
                            yield r.warning(
                                "file_edit requires old_content. Use file_read first to get the current content of the file.",
                                session_id,
                            )

                        # Hard limit on reflection errors
                        if reflection_errors >= REFLECTION_ERROR_LIMIT:
                            yield r.error(
                                f"Too many errors ({reflection_errors}). The model appears stuck.",
                                session_id, code="REFLECTION_LIMIT", recoverable=True,
                            )
                            return

                    # Track created files for self-delete protection
                    if tool_name == "file_write" and result.success:
                        target_path = tool_params.get("filepath") or tool_params.get("path") or ""
                        if target_path:
                            created_files.add(target_path)
                            logger.info("TRACKING file created: %s (total tracked: %d)", target_path, len(created_files))

                    # Add tool result to messages
                    tool_result_text = _format_tool_result(tool_name, result, self.config.tools.max_tool_output)
                    messages.append({"role": "user", "content": tool_result_text})

                # Post-completion stop: if model has signaled task completion and
                # all tools in this turn succeeded, stop instead of letting model keep going
                if not task_completed and clean_response and _COMPLETION_SIGNALS.search(clean_response):
                    task_completed = True
                    logger.info("COMPLETION SIGNAL detected in turn %d response, will stop after this iteration", iteration)
                    # Don't break yet — let the model's summary be the final message
                    # (it will have no tool calls on next iteration, which triggers the normal break)

            else:
                # Max iterations exceeded
                yield r.error(f"Max iterations ({max_iterations}) exceeded", session_id, code="MAX_ITERATIONS")
                return

        finally:
            # Tools handle their own subprocess cleanup on cancellation
            pass

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

    def _get_tool_schemas(self) -> list[dict]:
        """Get full schema info for all registered tools."""
        if self.tool_registry:
            return self.tool_registry.get_schemas()
        return []

    def _get_tool_names(self) -> list[str]:
        """Get list of available tool names."""
        if self.tool_registry:
            return self.tool_registry.list_tools()
        return []
