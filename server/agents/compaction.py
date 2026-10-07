from __future__ import annotations

import logging
from dataclasses import dataclass

from server.config.constants import (
    ANSI_RE,
    CHARS_PER_TOKEN,
    COMPACTION_KEEP_TAIL,
    MAX_TOOL_OUTPUT_BASELINE,
)

logger = logging.getLogger(__name__)

# Tool results whose payload is the *content* of the task rather than a
# bookkeeping summary. Compaction may trim these but must never replace them with
# a one-line digest: a file's text and the task state are the two things the
# model cannot reconstruct. Membership is decided from the structured
# ``tool_name`` tag the agent loop stamps on every tool message — never from the
# human-readable ``[Tool: ...]`` prefix, which is display text and may be
# reworded at any time.
PRESERVE_ON_COMPACT: frozenset[str] = frozenset({"file_read", "todo"})


def _message_tool_name(msg: dict) -> str:
    """The tool that produced *msg*, from its structured tag.

    Falls back to the display prefix only for messages written before the tag
    existed (restored sessions, hand-built test fixtures). New messages always
    carry ``tool_name``.
    """
    tagged = msg.get("tool_name")
    if isinstance(tagged, str) and tagged:
        return tagged
    content = msg.get("content")
    if isinstance(content, str) and content.startswith("[Tool:"):
        head = content[len("[Tool:") :].strip()
        return head.split(" ", 1)[0].split("|", 1)[0].strip()
    return ""


def is_tool_message(msg: dict) -> bool:
    """True when *msg* carries a tool result."""
    if _message_tool_name(msg):
        return True
    content = msg.get("content")
    return isinstance(content, str) and content.startswith("[Tool:")


@dataclass
class CompactionStats:
    original_chars: int = 0
    ansi_sequences_removed: int = 0
    ansi_stripped_chars: int = 0
    trimmed: bool = False
    compacted_chars: int = 0
    chars_removed: int = 0
    tokens_saved: int = 0
    reason: str = ""


def strip_ansi(text: str) -> tuple[str, int]:
    cleaned, n = ANSI_RE.subn("", text)
    return (cleaned, n)


def head_tail_trim(text: str, max_chars: int) -> tuple[str, int]:
    if len(text) <= max_chars:
        return (text, 0)
    head = max_chars * 2 // 3
    tail = max_chars - head
    omitted = len(text) - head - tail
    marker = f"\n... (truncated: {omitted} chars omitted from middle) ...\n"
    return (text[:head] + marker + text[-tail:], omitted)


def bound_tool_message(msg: dict, max_output: int) -> int:
    """Bound one tool-result message's payload to ``max_output``, in place.

    THE single implementation of the digest-or-trim rule. Every compaction pass
    (in-flight pruning, historical pruning, live-tail compaction) routes through
    this so the three passes cannot drift again - they previously each carried
    their own copy and had already diverged.

    Returns the number of characters removed (0 when nothing was compacted), and
    leaves the message untouched when it is already within budget.

    ``PRESERVE_ON_COMPACT`` tools are never reduced to a digest: a file's text and
    the task state are the two things the model cannot reconstruct, so they are
    only ever trimmed.
    """
    content = msg.get("content")
    if not isinstance(content, str):
        return 0
    if "digest" in msg and _message_tool_name(msg) not in PRESERVE_ON_COMPACT:
        msg["content"] = str(msg["digest"])
        msg["time"] = "compacted"
        return max(0, len(content) - len(msg["content"]))
    head, _, rest = content.partition("\n")
    if not rest:
        return 0
    trimmed, _ = head_tail_trim(rest, max_output)
    if trimmed == rest:
        return 0
    msg["content"] = f"{head}\n{trimmed}"
    msg["time"] = "compacted"
    return max(0, len(content) - len(msg["content"]))


def compact_tool_output(
    output: str, max_output: int = MAX_TOOL_OUTPUT_BASELINE, strip_ansi_codes: bool = True
) -> tuple[str, CompactionStats]:
    """Bound a tool result for the model, optionally stripping terminal escapes.

    ``strip_ansi_codes`` must be False for any tool that returns file content.
    The escape sequences are legitimate bytes there: a source file containing a
    literal ESC, or a document with real terminal formatting, must reach the
    model exactly as it sits on disk. Stripping it produces a model copy that
    differs from the file, and the next edit then writes the divergence back.
    It is only safe to strip for genuine terminal capture, where the escapes are
    an artefact of the transport rather than the payload.
    """
    stats = CompactionStats(original_chars=len(output))
    if strip_ansi_codes:
        compacted, n_ansi = strip_ansi(output)
    else:
        compacted, n_ansi = output, 0
    stats.ansi_sequences_removed = n_ansi
    stats.ansi_stripped_chars = len(output) - len(compacted)
    if len(compacted) > max_output:
        compacted, omitted = head_tail_trim(compacted, max_output)
        stats.trimmed = True
        stats.reason = f"head/tail trimmed (compacted, {omitted} chars omitted)"
    elif n_ansi:
        stats.reason = "ansi codes stripped"
    stats.compacted_chars = len(compacted)
    stats.chars_removed = max(0, stats.original_chars - len(compacted))
    stats.tokens_saved = stats.chars_removed // CHARS_PER_TOKEN
    return (compacted, stats)


def _group_start(history, i: int) -> int:
    """Start index of the tool-result exchange ending just before ``history[i]``."""
    j = i - 1
    if history[j].role == "tool":
        while j > 0 and history[j - 1].role == "tool":
            j -= 1
        if j > 0 and history[j - 1].role == "assistant":
            j -= 1
    return j


def _find_compaction_cut(history, keep_tail: int = COMPACTION_KEEP_TAIL) -> int:
    """Oldest message index to keep when compacting, never splitting a tool exchange."""
    if len(history) <= keep_tail:
        return 0
    cut = len(history) - keep_tail
    while cut > 0 and history[cut - 1].role == "assistant":
        cut -= 1
    return cut


def _find_compaction_cut_budgeted(history, keep_tokens: int, count_fn) -> int:
    """Oldest message index to keep so the recent tail fits ``keep_tokens``.

    Walks backwards in whole tool-result exchanges (assistant + tool + reply
    groups stay intact) until the accumulated tail would exceed the budget;
    returns the index of the first kept message. ``0`` means the entire history
    is summarized.
    """
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


def prune_inflight_messages(
    messages: list[dict],
    keep_latest_tools: int,
    max_output: int = 1000,
) -> tuple[list[dict], CompactionStats]:
    """Prune in-flight tool results in active conversation memory.

    Replaces older tool results with structured digests or head-tail trimmed previews,
    protecting the latest ``keep_latest_tools`` results in full detail.

    ``keep_latest_tools`` is required rather than defaulted: a default here
    silently drifted from the value the agent loop actually passes, so the
    signature looked configurable while the call site was fixed. Pass
    ``COMPACTION_KEEP_LATEST_TOOLS``.
    """
    stats = CompactionStats()
    if not messages:
        return ([], stats)

    # Find indices of all tool output messages
    tool_indices: list[int] = []
    for i, msg in enumerate(messages):
        if is_tool_message(msg):
            tool_indices.append(i)

    # Protect the latest `keep_latest_tools`. The `[:-keep]` slice collapses to
    # empty when keep == 0, which would protect every result rather than none, so
    # 0 is special-cased: it means "prune them all".
    to_prune_indices = (
        set(tool_indices[: len(tool_indices) - keep_latest_tools])
        if keep_latest_tools
        else set(tool_indices)
    )

    pruned_messages: list[dict] = []
    for i, msg in enumerate(messages):
        m = dict(msg)
        content = m.get("content", "")
        if i in to_prune_indices and isinstance(content, str):
            stats.original_chars += len(content)
            chars_diff = bound_tool_message(m, max_output)
            stats.chars_removed += chars_diff
            stats.tokens_saved += chars_diff // CHARS_PER_TOKEN
            stats.compacted_chars += len(m["content"])
            stats.trimmed = True
        else:
            if isinstance(content, str):
                stats.original_chars += len(content)
                stats.compacted_chars += len(content)

        pruned_messages.append(m)

    return (pruned_messages, stats)
