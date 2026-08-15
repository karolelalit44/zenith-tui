from __future__ import annotations

import logging
from dataclasses import dataclass

from server.config.constants import ANSI_RE, CHARS_PER_TOKEN, MAX_TOOL_OUTPUT_BASELINE

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
