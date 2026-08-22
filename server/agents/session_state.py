"""Session-state rendering service (todo 3.10-3.12).

Turns the in-process session write-registry (``server.agents.session_workspace``)
into a lazy, compressed, bounded ``<session_state>`` block that is injected near
the front of the system prompt on every compose.

The block is rendered on demand (never cached), so it always reflects the latest
``known_files`` state. It is bounded to ``SESSION_STATE_MAX_TOKENS`` heuristic
tokens and, when it would exceed that budget, drops the *earliest* entries first:
the most recently touched files are the ones the model is most likely to act on
next. Each file is rendered as a single-line digest that reuses the same
compaction pipeline ``format_tool_result`` applies to tool output (ANSI
stripping + head/tail trim).
"""

from __future__ import annotations

from server.agents.compaction import compact_tool_output
from server.agents.session_workspace import SessionFileRecord, known_files
from server.config.constants import (
    CHARS_PER_TOKEN,
    SESSION_STATE_ENTRY_MAX_CHARS,
    SESSION_STATE_HASH_PREFIX_LEN,
    SESSION_STATE_INTRO,
    SESSION_STATE_MARKER,
    SESSION_STATE_MAX_TOKENS,
    SESSION_STATE_OUTRO,
)


def render_file_digest_line(rec: SessionFileRecord) -> str:
    """Render one file as a single-line digest (path, bytes, hash prefix)."""
    raw = (
        f"{rec.path} ({rec.size} bytes, content hash "
        f"{rec.content_hash[:SESSION_STATE_HASH_PREFIX_LEN]})"
    )
    compacted, _stats = compact_tool_output(raw, max_output=SESSION_STATE_ENTRY_MAX_CHARS)
    # compact_tool_output may inject a truncation marker containing newlines;
    # collapse whitespace so the entry stays a single line.
    compacted = " ".join(compacted.split())
    return f"- {compacted}"


def render_session_state(session_id: str, max_tokens: int = SESSION_STATE_MAX_TOKENS) -> str | None:
    """Render the bounded ``<session_state>`` block for ``session_id`` on demand.

    Returns ``None`` when the session has no known files, so callers can skip
    injection entirely. The block is capped at ``max_tokens`` heuristic tokens
    (chars / ``CHARS_PER_TOKEN``); entries that would exceed the budget are
    dropped oldest-first so the most recent writes are always kept.
    """
    existing = known_files(session_id)
    if not existing:
        return None

    budget_chars = max_tokens * CHARS_PER_TOKEN
    intro = f"{SESSION_STATE_MARKER} {SESSION_STATE_INTRO}"
    outro = SESSION_STATE_OUTRO
    overhead = len(intro) + 1
    if len(outro) + 1 <= budget_chars - overhead:
        overhead += len(outro) + 1
    entries = [
        render_file_digest_line(rec) for _path, rec in existing.items()
    ]  # dict preserves insertion order: earliest first
    kept: list[str] = []
    used = overhead
    for entry in reversed(entries):  # newest first: keep the most recent writes
        if used + len(entry) + 1 > budget_chars:
            continue  # drop the earliest entries when over budget
        kept.append(entry)
        used += len(entry) + 1
    kept.reverse()  # restore earliest-first display order
    return "\n".join([intro, *kept, outro])
