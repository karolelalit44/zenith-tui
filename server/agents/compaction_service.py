"""Canonical compaction service.

Automatic (loop threshold) and manual (``context.compact`` RPC) compaction are
ONE operation with two triggers. The service owns the complete pipeline:

    context → budget → prune (candidate) → cut → summarize → validate →
    persist atomically → apply → events

Invariants:

- No authoritative state is mutated before summarization succeeds: pruning is
  applied to a candidate copy and applied back only on success.
- The summary and the prefix truncation are persisted in one transaction
  (``MessageRepository.compact_history``). Only the messages represented by the
  summary are removed; the recent tail always survives.
- A compaction result may only be applied to the conversation state from which
  it was derived: per-session monotonic generations guard stale application,
  and a superseded compaction never persists.
- At most one compaction runs per session at a time; a second trigger while one
  is in flight returns ``CompactionStatus.SKIPPED`` without emitting events.
- Token accounting uses the deterministic composed-context count, never
  cumulative provider usage, so metrics reflect the actual before/after states.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from server.agents.compaction import (
    _find_compaction_cut_budgeted,
    head_tail_trim,
)
from server.agents.context import ContextManager, _adaptive_reserve, _get_model_context_window
from server.agents.summarizer import ConversationSummarizer
from server.config.constants import (
    CHARS_PER_TOKEN,
    COMPACTION_KEEP_BUDGET_RATIO,
    COMPACTION_KEEP_MAX_TOKENS,
    COMPACTION_KEEP_MIN_TOKENS,
)
from server.domain.events import CompactionStatus, CompactionTrigger, Event
from server.providers import responder as r

if TYPE_CHECKING:
    from server.config.settings import AppSettings
    from server.domain.message import Message
    from server.providers.base import BaseProvider
    from server.storage.session_store import FileMessageRepository, FileSessionRepository

logger = logging.getLogger(__name__)

# Tool-result preview budgets for compaction-time pruning (algorithmic
# invariants of the compaction pass, not per-model policy).
TOOL_PREVIEW_MAX_CHARS = 2000
TAIL_TRIM_MAX_CHARS = 1000

EmittingFn = Callable[[Event], Awaitable[None]]


async def _noop_emit(_event: Event) -> None:
    return None


# Per-session registries shared across every service instance (the loop and the
# RPC handler use separate instances but must agree on ordering).
# _generations is bumped at the START of each compaction attempt; a result may
# only be persisted/applied while its generation is still current (re-checked
# immediately before the DB commit and again before the in-memory apply), so a
# slow, superseded compaction can never clobber newer session state.
_generations: dict[str, int] = {}
_in_progress: dict[str, bool] = {}
# Serialize summarizer LLM calls so they never interleave with a streaming turn
# on the shared provider.
_summarize_lock = asyncio.Lock()


def _next_generation(session_id: str) -> int:
    generation = _generations.get(session_id, 0) + 1
    _generations[session_id] = generation
    return generation


def generation_for(session_id: str) -> int:
    return _generations.get(session_id, 0)


def _compaction_keep_tokens(budget: int) -> int:
    """Recent-tail token budget for the compaction cut.

    Derived from the input budget (context window minus output reserve); the
    band and ratio are named constants and the result is clamped to the budget
    so small windows never request more than the context can hold.
    """
    if budget <= 0:
        return 0
    keep = max(COMPACTION_KEEP_MIN_TOKENS, int(budget * COMPACTION_KEEP_BUDGET_RATIO))
    return min(keep, COMPACTION_KEEP_MAX_TOKENS, budget)


def prune_tool_outputs(
    messages: list[dict],
    keep_turns: int = 2,
    max_output: int = TOOL_PREVIEW_MAX_CHARS,
    force_intraturn: bool = False,
) -> dict:
    """Compress old tool-result messages in a message list (in place).

    Keeps the most recent turns/tool results intact and replaces older ones
    with their digest (when present) or a head-tail trimmed preview. Idempotent:
    already-compacted messages are skipped.
    """
    stats: dict = {"count": 0, "chars_removed": 0, "tokens_saved": 0}
    if not messages:
        return stats
    boundary = 0
    if not force_intraturn:
        turns = 0
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                turns += 1
                if turns > keep_turns:
                    boundary = i + 1
                    break
    else:
        tool_msg_indices = [
            idx
            for idx, m in enumerate(messages)
            if isinstance(m.get("content", ""), str)
            and m.get("content", "").startswith("[Tool:")
        ]
        boundary = tool_msg_indices[-2] if len(tool_msg_indices) > 2 else 0

    for msg in messages[:boundary]:
        content = msg.get("content", "")
        if not isinstance(content, str) or not content.startswith("[Tool:"):
            continue
        if msg.get("time") == "compacted":
            continue
        orig_len = len(content)
        if "digest" in msg:
            msg["content"] = msg["digest"]
            msg["time"] = "compacted"
            msg["is_digested"] = True
            chars_diff = max(0, orig_len - len(msg["content"]))
            stats["count"] += 1
            stats["chars_removed"] += chars_diff
            stats["tokens_saved"] += chars_diff // CHARS_PER_TOKEN
        else:
            lines = content.split("\n", 1)
            head = lines[0]
            rest = lines[1] if len(lines) > 1 else ""
            if len(rest) > max_output:
                compacted_rest, _ = head_tail_trim(rest, max_output)
                msg["content"] = head + "\n" + compacted_rest if rest else head
                msg["time"] = "compacted"
                chars_diff = max(0, orig_len - len(msg["content"]))
                stats["count"] += 1
                stats["chars_removed"] += chars_diff
                stats["tokens_saved"] += chars_diff // CHARS_PER_TOKEN
    return stats


def compact_live_tail(messages: list[dict]) -> None:
    """Compress the live turn tail in place before replay after compaction."""
    for msg in messages:
        content = msg.get("content", "")
        if (
            msg.get("role") == "user"
            and isinstance(content, str)
            and content.startswith("[Tool:")
        ):
            if "digest" in msg:
                msg["content"] = msg["digest"]
                msg["time"] = "compacted"
            elif len(content) > TAIL_TRIM_MAX_CHARS:
                lines = content.split("\n", 1)
                head = lines[0]
                rest = lines[1] if len(lines) > 1 else ""
                trimmed_rest, _ = head_tail_trim(rest, TAIL_TRIM_MAX_CHARS)
                msg["content"] = head + "\n" + trimmed_rest if rest else head
                msg["time"] = "compacted"


def _cache_prefix_for(messages: list[dict]) -> list[dict]:
    """Longest cache-stable prefix of a composed message array.

    Returns the messages up to and including the last ``cache_control``
    breakpoint marker (end of the deepest cached tier). When the array has no
    markers (e.g. non-caching provider or a bare history list) an empty prefix is
    returned so callers fall back to the plain summarizer request.
    """
    if not messages:
        return []
    last_marker = -1
    for i, m in enumerate(messages):
        if isinstance(m, dict) and m.get("cache_control"):
            last_marker = i
    if last_marker < 0:
        return []
    return [dict(m) for m in messages[: last_marker + 1]]


@dataclass
class CompactionOutcome:
    """Structured result of one compaction operation."""

    trigger: CompactionTrigger
    status: CompactionStatus
    generation: int
    started_at: float
    completed_at: float | None = None
    used_before: int = 0
    used_after: int = 0
    total: int = 0
    tokens_saved: int = 0
    summary: str = ""
    summary_chars: int = 0
    cut: int = 0
    kept_tail: int = 0
    pruned: dict = field(default_factory=dict)
    deleted: int = 0
    error: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return self.status == CompactionStatus.FAILED

    @property
    def skipped(self) -> bool:
        return self.status == CompactionStatus.SKIPPED

    @property
    def has_warnings(self) -> bool:
        return bool(self.warnings)


class CompactionService:
    """Canonical compaction operation shared by automatic and manual triggers."""

    def __init__(
        self,
        config: AppSettings,
        provider: BaseProvider,
        context_manager: ContextManager | None = None,
        session_repo: FileSessionRepository | None = None,
        message_repo: FileMessageRepository | None = None,
    ) -> None:
        self._config = config
        self._provider = provider
        self._context_manager = context_manager or ContextManager(config)
        self._session_repo = session_repo
        self._message_repo = message_repo

    def _count(self, message: Message) -> int:
        return self._context_manager.count_tokens(
            getattr(message, "content", str(message)), self._provider.model
        )

    def _count_memoized(
        self, history: list[Message], memo: dict[int, int]
    ) -> Callable[[Message], int]:
        """Counting function with a per-compaction-call cache.

        The same messages are counted repeatedly across the cut search,
        prefix totals and post-apply breakdowns; tokenization dominates
        compaction latency on large histories.
        """

        def _count(message: Message) -> int:
            key = id(message)
            cached = memo.get(key)
            if cached is None:
                cached = self._count(message)
                memo[key] = cached
            return cached

        return _count

    def _context_window(self, model: str) -> int:
        return min(_get_model_context_window(model), self._config.max_context_tokens)

    async def compact(
        self,
        *,
        session_id: str,
        history: list[Message],
        messages: list[dict] | None = None,
        trigger: CompactionTrigger = CompactionTrigger.AUTOMATIC,
        reason: str = "automatic",
        previous_summary: str | None = None,
        emit: EmittingFn | None = None,
        focus: str | None = None,
    ) -> CompactionOutcome:
        emit = emit or _noop_emit
        model = self._provider.model
        if _in_progress.get(session_id):
            logger.info("Compaction already in progress for session %s — skipping", session_id)
            return CompactionOutcome(
                trigger=trigger,
                status=CompactionStatus.SKIPPED,
                generation=generation_for(session_id),
                started_at=time.time(),
            )
        _in_progress[session_id] = True
        generation = _next_generation(session_id)
        started_at = time.time()
        outcome = CompactionOutcome(
            trigger=trigger,
            status=CompactionStatus.STARTED,
            generation=generation,
            started_at=started_at,
        )
        try:
            token_info = (
                self._context_manager.get_token_info(messages or [], model)
                if messages
                else None
            )
            memo: dict[int, int] = {}
            count = self._count_memoized(history, memo)
            used = token_info.used if token_info else sum(count(m) for m in history)
            total = (
                token_info.total if token_info else self._context_window(model)
            )
            before_tiers = (
                self._context_manager.token_breakdown(messages or []).to_dict()
                if messages
                else None
            )
            outcome.used_before = used
            outcome.total = total
            await emit(
                r.context_compaction_started(
                    session_id, reason, used, total, tokens=before_tiers, trigger=trigger.value
                )
            )
            await emit(
                r.context_compaction_phase(
                    session_id,
                    "preserving",
                    "Preserving active working state & recent files...",
                    trigger=trigger.value,
                )
            )
            pruned: dict = {"count": 0, "chars_removed": 0, "tokens_saved": 0}
            candidate: list[dict] | None = None
            if messages:
                # Derive a candidate compacted state; the authoritative list is
                # only replaced after summarization and persistence succeed.
                candidate = [dict(m) for m in messages]
                pruned = prune_tool_outputs(candidate, force_intraturn=True)
                if pruned["count"]:
                    await emit(
                        r.context_compacted(
                            "context",
                            pruned["chars_removed"],
                            pruned["tokens_saved"],
                            f"pruned {pruned['count']} old tool result(s)",
                            session_id,
                        )
                    )
            outcome.pruned = pruned
            await emit(
                r.context_compaction_phase(
                    session_id,
                    "compacting",
                    "Compacting intermediate tool outputs & history...",
                    trigger=trigger.value,
                )
            )
            ctx = self._context_window(model)
            reserve = _adaptive_reserve(model, ctx)
            keep_tokens = _compaction_keep_tokens(max(0, ctx - reserve))
            cut = _find_compaction_cut_budgeted(
                history, keep_tokens, count
            )
            outcome.cut = cut
            outcome.kept_tail = max(0, len(history) - cut)
            prefix = history[:cut]
            if not prefix and not pruned.get("count", 0):
                # Nothing can be safely summarized AND tool-output pruning found
                # nothing to shrink: the operation would be a no-op. Report a
                # skip instead of fabricating a summary or truncating anything.
                # (A prune-only pass -- cut==0 but pruned["count"]>0 -- still
                # falls through and completes, applying the shrunken candidate.)
                logger.info(
                    "Compaction skipped for %s: no summarizable prefix "
                    "(cut=0, history=%d)",
                    session_id,
                    len(history),
                )
                outcome.status = CompactionStatus.SKIPPED
                outcome.completed_at = time.time()
                await emit(
                    r.context_compaction_ended(
                        session_id,
                        reason,
                        used,
                        total,
                        tokens_saved=0,
                        summary_chars=0,
                        summary="",
                        tokens_before=before_tiers,
                        tokens_after=None,
                        trigger=trigger.value,
                        status=outcome.status.value,
                    )
                )
                return outcome
            if prefix:
                async with _summarize_lock:
                    summary = await ConversationSummarizer(
                        self._config, self._provider
                    ).summarize(
                        prefix,
                        model,
                        session_id=session_id,
                        previous_summary=previous_summary,
                        prefix=_cache_prefix_for(messages or []),
                        focus=focus,
                    )
                if not summary:
                    raise RuntimeError("summarization produced an empty result")
                outcome.summary = summary
                outcome.summary_chars = len(summary)
                prefix_tokens = sum(count(m) for m in prefix)
                summary_tokens = self._context_manager.count_tokens(summary, model)
                outcome.tokens_saved = max(0, prefix_tokens - summary_tokens) + pruned[
                    "tokens_saved"
                ]
                outcome.used_after = max(0, used - outcome.tokens_saved)
                # Persist atomically only if still the latest generation for this
                # session (a compaction result may only be applied to the state
                # from which it was derived).
                if (
                    self._message_repo is not None
                    and self._session_repo is not None
                    and _generations.get(session_id) == generation
                ):
                    session = await self._session_repo.get(session_id)
                    if session is None:
                        raise RuntimeError(f"session {session_id} not found")
                    metadata = dict(session.metadata or {})
                    metadata["summary"] = summary
                    delete_ids = [m.id for m in prefix if getattr(m, "id", None)]
                    outcome.deleted = await self._message_repo.compact_history(
                        session_id, metadata, delete_ids
                    )
                    logger.info(
                        "Compaction persisted for %s: summary=%d chars, truncated=%d "
                        "message(s), tail=%d",
                        session_id,
                        len(summary),
                        outcome.deleted,
                        outcome.kept_tail,
                    )
            # Durable state is committed above this line. Failures in the
            # remaining steps (in-memory apply, telemetry emission) must NOT
            # downgrade the outcome to FAILED: the DB already holds the new
            # summary plus the truncated history, so reporting failure would
            # leave a live session on its full context while a resumed one
            # sees the compacted form. Such problems are recorded as warnings
            # on a COMPLETED outcome instead. Persistence failures themselves
            # propagate to the outer handler and surface as FAILED.
            try:
                if messages and candidate is not None:
                    if _generations.get(session_id) == generation:
                        messages[:] = candidate
                    else:
                        outcome.warnings.append(
                            "generation advanced before apply; in-memory context left unchanged"
                        )
                after_tiers = (
                    self._context_manager.token_breakdown(messages or []).to_dict()
                    if messages
                    else None
                )
                await emit(
                    r.context_compaction_phase(
                        session_id,
                        "verifying",
                        "Verifying token savings & rebuilt context...",
                        before_tokens=used,
                        after_tokens=outcome.used_after,
                        tokens_before=before_tiers,
                        tokens_after=after_tiers,
                        trigger=trigger.value,
                    )
                )
            except Exception as apply_err:
                logger.warning(
                    "Post-persist compaction step failed for %s: %s", session_id, apply_err
                )
                outcome.warnings.append(f"post-persist step failed: {apply_err}")
                after_tiers = None
            outcome.status = CompactionStatus.COMPLETED
            outcome.completed_at = time.time()
            try:
                await emit(
                    r.context_compaction_ended(
                        session_id,
                        reason,
                        used,
                        total,
                        tokens_saved=outcome.tokens_saved,
                        summary_chars=outcome.summary_chars,
                        summary=outcome.summary,
                        tokens_before=before_tiers,
                        tokens_after=after_tiers,
                        trigger=trigger.value,
                        status=outcome.status.value,
                    )
                )
            except Exception as emit_err:
                logger.warning(
                    "Compaction end-event delivery failed for %s: %s", session_id, emit_err
                )
                outcome.warnings.append(f"end-event delivery failed: {emit_err}")
            return outcome
        except Exception as e:
            logger.warning("Compaction failed for session %s: %s", session_id, e)
            outcome.status = CompactionStatus.FAILED
            outcome.completed_at = time.time()
            outcome.error = str(e)
            await emit(
                r.context_compaction_ended(
                    session_id,
                    reason,
                    outcome.used_before,
                    outcome.total,
                    failed=True,
                    error=str(e),
                    trigger=trigger.value,
                    status=outcome.status.value,
                )
            )
            return outcome
        finally:
            _in_progress[session_id] = False