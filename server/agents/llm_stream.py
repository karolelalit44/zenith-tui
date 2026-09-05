from __future__ import annotations

import asyncio
import logging
import time as _time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import Enum

from server.domain.errors import ProviderError, RateLimitError
from server.domain.events import Event
from server.providers import responder as r
from server.providers.base import BaseProvider

logger = logging.getLogger(__name__)

# Minimum repeated-block size (chars) before deduplication kicks in.
# Blocks shorter than this are likely legitimate repetition (e.g. echoing a
# variable name) rather than the model looping on a reasoning chain.
_DEDUP_MIN_BLOCK_CHARS = 200
# Internal emission threshold for the additive reasoning-part fold.
_REASONING_EMIT_THRESHOLD = 200


def _deduplicate_reasoning(text: str, min_block: int = _DEDUP_MIN_BLOCK_CHARS) -> str:
    """Strip consecutive repeated blocks from reasoning text.

    Some models emit the same reasoning paragraph multiple times before
    producing a final answer.  This detects the pattern by checking whether
    the tail of the text repeats an earlier segment of comparable length and
    removes the duplicate(s), keeping only the first occurrence.
    """
    if len(text) < min_block * 2:
        return text
    # Iteratively peel off repeated suffixes until stable.
    prev_len = len(text) + 1
    while len(text) < prev_len:
        prev_len = len(text)
        half = len(text) // 2
        for block_size in range(min_block, half + 1, 50):
            tail = text[-block_size:]
            search_end = len(text) - block_size
            if search_end < block_size:
                continue
            idx = text.rfind(tail, 0, search_end)
            if idx >= 0:
                text = text[: idx + block_size]
                break
    return text


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


class ReasoningEffort(str, Enum):
    """Reasoning-effort config knob (codex ``ReasoningEffort``)."""

    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class ReasoningPart:
    """First-class reasoning part, delta-merged in place.

    ``kind`` walks ``start -> delta* -> end``. Each ``merge`` appends text and
    marks the part ``delta``; the resulting snapshot is the current merged
    state, matching opencode's "updated in place" reasoning-delta and codex's
    ``ReasoningContentDelta``.
    """

    kind: str = "start"
    text: str = ""
    duration_ms: int | None = None

    def merge(self, delta: str) -> None:
        self.text += delta
        self.kind = "delta"

    def finish(self, duration_ms: int | None = None) -> None:
        self.kind = "end"
        self.duration_ms = duration_ms

    def snapshot(self) -> dict:
        return {"kind": self.kind, "text": self.text, "durationMs": self.duration_ms}


async def accumulate_reasoning_parts(
    reasoning_iterator: AsyncIterator[str],
) -> AsyncIterator[dict]:
    """Fold a stream of reasoning deltas into reasoning Part snapshots.

    Yields a ``delta`` part (the current merged state) whenever at least
    ``_REASONING_EMIT_THRESHOLD`` new chars have accumulated, and a final
    ``end`` part when the iterator is exhausted. The first emission carries
    ``kind="start"`` if it is also the final (single-delta) emission.

    Standalone helper for callers that already have an isolated reasoning-only
    stream; ``stream_completion`` below reuses the same ``ReasoningPart``
    merge/threshold semantics inline since it consumes a combined
    content+reasoning stream instead.
    """
    part = ReasoningPart(kind="start", text="")
    pending = 0
    started = _time.monotonic()
    emitted = False
    async for delta in reasoning_iterator:
        part.merge(delta)
        pending += len(delta)
        if pending >= _REASONING_EMIT_THRESHOLD:
            pending = 0
            yield part.snapshot()
            emitted = True
    if part.text:
        part.finish(int((_time.monotonic() - started) * 1000))
        # If nothing was emitted during streaming, this single emission is the
        # complete part; start-duplicated only otherwise.
        if not emitted:
            part.kind = "start"
        yield part.snapshot()


@dataclass
class StreamState:
    full_response: str = ""
    response_text: str = ""
    reasoning_text: str = ""
    finish_reason: str = ""
    _dedup_prefix_len: int = 0  # tracks deduplication boundary


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
        started_at = _time.monotonic()
        reasoning_part = ReasoningPart()
        pending_reasoning_chars = 0
        reasoning_closed = False
        async for content, reasoning in provider.stream(
            messages, tools=tools, tool_choice=tool_choice, response_format=response_format
        ):
            stream_chunk_count += 1
            if reasoning:
                state.reasoning_text += reasoning
                reasoning_part.merge(reasoning)
                pending_reasoning_chars += len(reasoning)
                # Live thinking block (codex ReasoningContentDelta parity): stream
                # the running reasoning text as it arrives instead of batching
                # the whole thought to the end of the turn, so the "thinking"
                # block renders while the model is still reasoning, not after.
                if pending_reasoning_chars >= _REASONING_EMIT_THRESHOLD:
                    pending_reasoning_chars = 0
                    yield r.thinking(reasoning_part.text, session_id, partial=True)
            if content:
                # Close the thinking block IMMEDIATELY when reasoning completes
                # and content begins, so the user timeline preserves chronological
                # fidelity (thinking -> message) rather than emitting thinking
                # after the message.
                if not reasoning_closed and state.reasoning_text.strip():
                    duration_ms = int((_time.monotonic() - started_at) * 1000)
                    deduplicated = _deduplicate_reasoning(state.reasoning_text)
                    if len(deduplicated) < len(state.reasoning_text):
                        logger.info(
                            "Thinking deduplication: %d -> %d chars (%.0f%% reduction)",
                            len(state.reasoning_text),
                            len(deduplicated),
                            (1 - len(deduplicated) / max(len(state.reasoning_text), 1)) * 100,
                        )
                        state.reasoning_text = deduplicated
                    yield r.thinking(state.reasoning_text.strip(), session_id, duration_ms=duration_ms)
                    reasoning_closed = True
                state.response_text += content
                yield r.message_event(content, session_id, partial=True)
        # Reasoning is model-internal chain-of-thought. It is never folded into
        # the assistant message, even when the model produced little or no
        # content (a "reasoning-only" turn): exposing it as prose leaks private
        # chain-of-thought into the user-visible transcript. A reasoning-only
        # turn is surfaced as a separate `thinking` event (kept collapsed in the
        # UI) and, with no real content, the loop reports an empty response.
        if not reasoning_closed and state.reasoning_text.strip():
            duration_ms = int((_time.monotonic() - started_at) * 1000)
            deduplicated = _deduplicate_reasoning(state.reasoning_text)
            if len(deduplicated) < len(state.reasoning_text):
                logger.info(
                    "Thinking deduplication: %d -> %d chars (%.0f%% reduction)",
                    len(state.reasoning_text),
                    len(deduplicated),
                    (1 - len(deduplicated) / max(len(state.reasoning_text), 1)) * 100,
                )
                state.reasoning_text = deduplicated
            # Final, non-partial emission closes the live thinking block with
            # the deduplicated text and the total thinking duration.
            yield r.thinking(state.reasoning_text.strip(), session_id, duration_ms=duration_ms)
            reasoning_closed = True
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
