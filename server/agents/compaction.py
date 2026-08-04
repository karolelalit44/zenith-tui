"""Micro-compaction pipeline for tool results (HP-4).

Stages applied to raw tool output before it enters the LLM context:
1. ANSI strip — remove terminal escape sequences (colour codes, OSC
   hyperlinks, etc.) that carry no information.
2. Head/tail trim — for oversized output keep the head and tail and drop the
   middle. This is fact-preserving: errors and summaries usually land at the
   tail, while status/headers live at the head.
3. Result drop is fact-preserving — the compacted form still carries the
   tool name, status, and output tail so downstream reasoning keeps its facts.

Stats are returned so callers can emit a CONTEXT_COMPACTED event with counts.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ANSI escape sequences: CSI, OSC (hyperlinks), DCS/APC/PM/SOS, charset select.
ANSI_RE = re.compile(
    r"\x1b\[[0-9;?]*[A-Za-z]"  # CSI
    r"|\x1b\][^\x07]*(?:\x07|\x1b\\)"  # OSC (terminated by BEL or ST)
    r"|\x1b[PXQ^_][^\x1b]*\x1b\\"  # DCS/APC/PM/SOS (terminated by ST)
    r"|\x1b[()][A-Za-z0-9]"  # charset selection
)

# Rough char -> token conversion used for the tokensSaved figure.
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
    """Remove ANSI escape sequences; returns (clean_text, sequences_removed)."""
    cleaned, n = ANSI_RE.subn("", text)
    return cleaned, n


def head_tail_trim(text: str, max_chars: int) -> tuple[str, int]:
    """Keep the head (2/3) and tail (1/3) of oversized text, dropping the middle.

    Returns (trimmed_text, chars_omitted). The marker line preserves the count
    so the model knows content was dropped rather than missing.
    """
    if len(text) <= max_chars:
        return text, 0
    head = max_chars * 2 // 3
    tail = max_chars - head
    omitted = len(text) - head - tail
    marker = f"\n... (truncated: {omitted} chars omitted from middle) ...\n"
    return text[:head] + marker + text[-tail:], omitted


def compact_tool_output(
    output: str,
    max_output: int = 10000,
) -> tuple[str, CompactionStats]:
    """Run the micro-compaction pipeline over raw tool output.

    Returns (compacted_text, stats). Idempotent and side-effect free.
    """
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
