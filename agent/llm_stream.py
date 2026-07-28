"""LLM streaming — streaming LLM responses with retry logic."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import AsyncIterator

from core.errors import ZenithError, RateLimitError, ProviderError
from core.events import Event
from providers import responder as r
from providers.base import BaseProvider

logger = logging.getLogger(__name__)

MAX_STREAM_RETRIES = 2


@dataclass
class StreamState:
    """Mutable state shared between caller and stream_with_retries."""
    full_response: str = ""
    response_text: str = ""


async def stream_with_retries(
    provider: BaseProvider,
    messages: list[dict],
    tools: list[dict],
    session_id: str,
    iteration: int,
    state: StreamState | None = None,
) -> AsyncIterator[Event]:
    """Stream LLM response with retry on recoverable errors.

    Yields thinking and message events. Updates state.full_response with
    the complete accumulated text. state.response_text holds the text from
    the last successful stream attempt (for tool call parsing).
    """
    if state is None:
        state = StreamState()
    state.response_text = ""

    for attempt in range(MAX_STREAM_RETRIES + 1):
        reasoning_buffer = ""
        stream_chunk_count = 0
        logger.info("LLM stream start: attempt=%d/%d, tools=%d, messages=%d",
                     attempt + 1, MAX_STREAM_RETRIES + 1, len(tools), len(messages))
        try:
            async for content, reasoning in provider.stream(messages, tools=tools):
                stream_chunk_count += 1
                if reasoning:
                    reasoning_buffer += reasoning
                    logger.info("  Stream chunk #%d: REASONING len=%d total_reasoning=%d",
                                stream_chunk_count, len(reasoning), len(reasoning_buffer))
                if content:
                    if reasoning_buffer:
                        yield r.thinking(reasoning_buffer, session_id)
                        reasoning_buffer = ""
                    state.response_text += content
                    logger.info("  Stream chunk #%d: CONTENT len=%d total_content=%d preview=%r",
                                stream_chunk_count, len(content), len(state.response_text), content[:100])
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
            if attempt == MAX_STREAM_RETRIES or not e.recoverable:
                yield r.error(str(e), session_id, code=e.code, recoverable=False)
                return
            logger.warning("Stream retry %d/%d after rate limit: %s", attempt + 1, MAX_STREAM_RETRIES, e)
            if state.response_text:
                yield r.message_event(state.response_text, session_id, partial=False)
                state.full_response += state.response_text
                state.response_text = ""
            yield r.thinking(f"Rate limited, retrying in {int(e.retry_after or 2)}s...", session_id)
            await asyncio.sleep(e.retry_after or (2 ** attempt))
        except ProviderError as e:
            if not e.recoverable or attempt == MAX_STREAM_RETRIES:
                yield r.error(str(e), session_id, code=e.code, recoverable=e.recoverable)
                return
            logger.warning("Stream retry %d/%d after provider error: %s", attempt + 1, MAX_STREAM_RETRIES, e)
            if state.response_text:
                yield r.message_event(state.response_text, session_id, partial=False)
                state.full_response += state.response_text
                state.response_text = ""
            yield r.thinking("Retrying after provider error...", session_id)
            await asyncio.sleep(2 ** attempt)
        except Exception as e:
            logger.error("LLM stream error on turn %d: %s", iteration, e, exc_info=True)
            yield r.error(str(e), session_id)
            return

    yield r.error("Stream failed after all retries", session_id, code="STREAM_EXHAUSTED", recoverable=True)
