from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

from server.domain.errors import ProviderError, RateLimitError
from server.domain.events import Event
from server.providers import responder as r
from server.providers.base import BaseProvider

logger = logging.getLogger(__name__)


def _friendly_rate_limit_text(e: RateLimitError) -> str:
    """Human-readable, actionable copy for a rate-limit error.

    Per-minute throttles (recoverable=True) tell the user to wait and retry;
    daily/billing exhaustion (recoverable=False) tells them to switch
    model/provider instead of dumping the raw provider JSON at them.
    """
    provider = e.provider or "provider"
    if not e.recoverable:
        return (
            f"Rate limit reached ({provider}): the free-tier or daily quota is "
            "exhausted. Switch model/provider or try again later."
        )
    if e.retry_after:
        return (
            f"Rate limit reached ({provider}). Wait about {round(e.retry_after)}s "
            "for the limit to reset, then retry — this request was not completed."
        )
    return (
        f"Rate limit reached ({provider}). Wait for the limit to reset, then "
        "retry — this request was not completed."
    )


def _error_action_hint(e: ProviderError | RateLimitError) -> tuple[str, str]:
    """Map a provider error to UI affordance metadata (``action``/``hint``).

    ``action`` drives which button the frontend offers; ``hint`` is the
    actionable copy shown under the message. Both keep the UI free of
    string-matching on the error text.
    """
    if isinstance(e, RateLimitError):
        if e.recoverable:
            return "retry", "Wait for the rate limit to reset, then retry this prompt."
        return "change_model", "Switch model/provider or try again later."
    if e.recoverable:
        return "retry", "The provider reported a transient error; you can retry this prompt."
    return "", ""


@dataclass
class StreamState:
    full_response: str = ""
    response_text: str = ""
    reasoning_text: str = ""
    finish_reason: str = ""


async def stream_completion(
    provider: BaseProvider,
    messages: list[dict],
    tools: list[dict],
    session_id: str,
    iteration: int,
    state: StreamState | None = None,
    tool_choice: str | None = None,
    response_format: dict | None = None,
) -> AsyncIterator[Event]:
    """Stream exactly one LLM completion.

    No silent retries or backoff. If the provider errors (rate limit, quota,
    transient failure, unsupported parameter) the request fails explicitly: a
    single error event is emitted carrying the code and recoverability flag,
    and the decision to retry is left to the caller (or the user).
    """
    if state is None:
        state = StreamState()
    state.response_text = ""
    state.reasoning_text = ""
    logger.info(
        "LLM stream start: tools=%d, messages=%d",
        len(tools),
        len(messages),
    )
    try:
        stream_chunk_count = 0
        async for content, reasoning in provider.stream(
            messages, tools=tools, tool_choice=tool_choice, response_format=response_format
        ):
            stream_chunk_count += 1
            if reasoning:
                state.reasoning_text += reasoning
            if content:
                state.response_text += content
                yield r.message_event(content, session_id, partial=True)
        # Reasoning is folded into the message only when the model produced
        # no real content (a "reasoning-only" turn). Emitting it BOTH as a
        # thinking block and as the message duplicates the text in the UI.
        if len(state.response_text.strip()) < 30 and len(state.reasoning_text.strip()) > 100:
            logger.info(
                "Reasoning model content payload was tiny (%d chars) while reasoning was %d chars — using reasoning text as response content",
                len(state.response_text.strip()),
                len(state.reasoning_text.strip()),
            )
            # Fold reasoning into the content so the loop emits it once as the
            # assistant message; do NOT also emit a thinking block for it.
            state.response_text = state.reasoning_text.strip()
        elif state.reasoning_text.strip():
            yield r.thinking(state.reasoning_text.strip(), session_id)
        if state.response_text:
            state.full_response += state.response_text
            logger.info(
                "LLM stream complete: chunks=%d content_len=%d reasoning_len=%d full_response_len=%d",
                stream_chunk_count,
                len(state.response_text),
                len(state.reasoning_text),
                len(state.full_response),
            )
    except asyncio.CancelledError:
        raise
    except RateLimitError as e:
        action, hint = _error_action_hint(e)
        yield r.error(
            _friendly_rate_limit_text(e),
            session_id,
            code=e.code,
            recoverable=e.recoverable,
            provider=e.provider,
            action=action,
            hint=hint,
        )
        return
    except ProviderError as e:
        if e.code == "CONTEXT_EXCEEDED":
            yield r.warning(
                "Context window exceeded — summarizing to make room.",
                session_id,
                extra={"context_exceeded": True},
            )
            return
        action, hint = _error_action_hint(e)
        yield r.error(
            str(e),
            session_id,
            code=e.code,
            recoverable=e.recoverable,
            provider=e.provider,
            action=action,
            hint=hint,
        )
        return
    except Exception as e:
        logger.exception("LLM stream error on turn %d", iteration)
        yield r.error(str(e), session_id)
        return
