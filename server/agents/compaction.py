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


def compact_tool_output(
    output: str, max_output: int = MAX_TOOL_OUTPUT_BASELINE
) -> tuple[str, CompactionStats]:
    stats = CompactionStats(original_chars=len(output))
    compacted, n_ansi = strip_ansi(output)
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
    keep_latest_tools: int = 2,
    max_output: int = 1000,
) -> tuple[list[dict], CompactionStats]:
    """Prune in-flight tool results in active conversation memory.

    Replaces older tool results with structured digests or head-tail trimmed previews,
    protecting the latest ``keep_latest_tools`` results in full detail.
    """
    stats = CompactionStats()
    if not messages:
        return ([], stats)

    # Find indices of all tool output messages
    tool_indices: list[int] = []
    for i, msg in enumerate(messages):
        content = msg.get("content", "")
        if isinstance(content, str) and content.startswith("[Tool:"):
            tool_indices.append(i)

    # Protect the latest `keep_latest_tools`
    to_prune_indices = (
        set(tool_indices[:-keep_latest_tools]) if len(tool_indices) > keep_latest_tools else set()
    )

    pruned_messages: list[dict] = []
    for i, msg in enumerate(messages):
        m = dict(msg)
        content = m.get("content", "")
        if i in to_prune_indices and isinstance(content, str):
            orig_len = len(content)
            stats.original_chars += orig_len

            if "digest" in m:
                m["content"] = m["digest"]
                m["time"] = "compacted"
                m["is_digested"] = True
            else:
                lines = content.split("\n", 1)
                head = lines[0]
                rest = lines[1] if len(lines) > 1 else ""
                trimmed_rest, _ = head_tail_trim(rest, max_output)
                m["content"] = head + "\n" + trimmed_rest if rest else head
                m["time"] = "compacted"

            compacted_len = len(m["content"])
            chars_diff = max(0, orig_len - compacted_len)
            stats.chars_removed += chars_diff
            stats.tokens_saved += chars_diff // CHARS_PER_TOKEN
            stats.compacted_chars += compacted_len
            stats.trimmed = True
        else:
            if isinstance(content, str):
                stats.original_chars += len(content)
                stats.compacted_chars += len(content)

        pruned_messages.append(m)

    return (pruned_messages, stats)
