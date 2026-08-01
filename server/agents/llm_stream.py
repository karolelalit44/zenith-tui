"""LLM streaming — streaming LLM responses with retry logic.

Time-based retry (Aider-style): retries for up to RETRY_TIMEOUT seconds
instead of a fixed number of attempts. This handles slow free-tier models
and long rate-limit windows much better than count-based retries.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

from core.errors import ProviderError, RateLimitError
from core.events import Event
from providers import responder as r
from providers.base import BaseProvider

logger = logging.getLogger(__name__)

# Time-based retry window (Aider-style): retry for up to 60s
RETRY_TIMEOUT = 60.0


@dataclass
class StreamState:
    """Mutable state shared between caller and stream_with_retries."""
    full_response: str = ""
    response_text: str = ""
    finish_reason: str = ""


async def stream_with_retries(
    provider: BaseProvider,
    messages: list[dict],
    tools: list[dict],
    session_id: str,
    iteration: int,
    state: StreamState | None = None,
    tool_choice: str | None = None,
    response_format: dict | None = None,
) -> AsyncIterator[Event]:
    """Stream LLM response with time-based retry on recoverable errors.

    Retries for up to RETRY_TIMEOUT seconds (instead of a fixed number of
    attempts). Uses exponential backoff with jitter.

    Yields thinking and message events. Updates state.full_response with
    the complete accumulated text. state.response_text holds the text from
    the last successful stream attempt (for tool call parsing).
    """
    if state is None:
        state = StreamState()
    state.response_text = ""

    deadline = time.monotonic() + RETRY_TIMEOUT
    attempt = 0

    while True:
        attempt += 1
        reasoning_buffer = ""
        stream_chunk_count = 0
        remaining = max(0, deadline - time.monotonic())
        logger.info("LLM stream start: attempt=%d, tools=%d, messages=%d, remaining=%.1fs",
                     attempt, len(tools), len(messages), remaining)
        try:
            async for content, reasoning in provider.stream(messages, tools=tools, tool_choice=tool_choice, response_format=response_format):
                stream_chunk_count += 1
                if reasoning:
                    reasoning_buffer += reasoning
                if content:
                    if reasoning_buffer:
                        yield r.thinking(reasoning_buffer, session_id)
                        reasoning_buffer = ""
                    state.response_text += content
                    yield r.message_event(content, session_id, partial=True)
            if reasoning_buffer:
                yield r.thinking(reasoning_buffer, session_id)
            # Stream completed — finalize the message
            if state.response_text:
                state.full_response += state.response_text
                logger.info("LLM stream complete: chunks=%d content_len=%d full_response_len=%d",
                            stream_chunk_count, len(state.response_text), len(state.full_response))
            return

        except asyncio.CancelledError:
            raise
        except RateLimitError as e:
            if time.monotonic() >= deadline or not e.recoverable:
                yield r.error(str(e), session_id, code=e.code, recoverable=False)
                return
            delay = min(e.retry_after or min(2 ** attempt, 30), deadline - time.monotonic())
            if delay <= 0:
                yield r.error(str(e), session_id, code=e.code, recoverable=False)
                return
            logger.warning("Stream retry %d after rate limit (%.1fs): %s", attempt, delay, e)
            if state.response_text:
                yield r.message_event(state.response_text, session_id, partial=False)
                state.full_response += state.response_text
                state.response_text = ""
            yield r.thinking(f"Rate limited, retrying in {int(delay)}s...", session_id)
            await asyncio.sleep(delay)
        except ProviderError as e:
            if e.code == "CONTEXT_EXCEEDED":
                yield r.warning("Context window exceeded — summarizing and retrying...", session_id, extra={"context_exceeded": True})
                return
            if time.monotonic() >= deadline or not e.recoverable:
                yield r.error(str(e), session_id, code=e.code, recoverable=e.recoverable)
                return
            delay = min(2 ** attempt, deadline - time.monotonic())
            if delay <= 0:
                yield r.error(str(e), session_id, code=e.code, recoverable=e.recoverable)
                return
            logger.warning("Stream retry %d after provider error (%.1fs): %s", attempt, delay, e)
            if state.response_text:
                yield r.message_event(state.response_text, session_id, partial=False)
                state.full_response += state.response_text
                state.response_text = ""
            yield r.thinking("Retrying after provider error...", session_id)
            await asyncio.sleep(delay)
        except Exception as e:
            error_str = str(e).lower()
            if tool_choice == "required" and ("tool_choice" in error_str or "unsupported" in error_str or "invalid parameter" in error_str):
                logger.warning("tool_choice=required rejected by model (%.100s), falling back to auto", error_str)
                tool_choice = "auto"
                if state.response_text:
                    yield r.message_event(state.response_text, session_id, partial=False)
                    state.full_response += state.response_text
                    state.response_text = ""
                yield r.thinking("Model doesn't support forced tool calls, switching to auto...", session_id)
                continue
            logger.error("LLM stream error on turn %d: %s", iteration, e, exc_info=True)
            yield r.error(str(e), session_id)
            return

        if time.monotonic() >= deadline:
            break

    yield r.error("Stream failed after timeout", session_id, code="STREAM_EXHAUSTED", recoverable=True)
