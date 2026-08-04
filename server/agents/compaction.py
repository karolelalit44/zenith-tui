
from __future__ import annotations
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]" r"|\x1b\][^\x07]*(?:\x07|\x1b\\)" r"|\x1b[PXQ^_][^\x1b]*\x1b\\" r"|\x1b[()][A-Za-z0-9]")

CHARS_PER_TOKEN = 4


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
    return cleaned, n


def head_tail_trim(text: str, max_chars: int) -> tuple[str, int]:
    if len(text) <= max_chars:
        return text, 0
    head = max_chars * 2 // 3
    tail = max_chars - head
    omitted = len(text) - head - tail
    marker = f"\n... (truncated: {omitted} chars omitted from middle) ...\n"
    return text[:head] + marker + text[-tail:], omitted


def compact_tool_output(output: str, max_output: int = 10000) -> tuple[str, CompactionStats]:
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
    return compacted, stats
