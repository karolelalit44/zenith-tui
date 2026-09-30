from __future__ import annotations

import logging
import re
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

# ---------------------------------------------------------------------------
# Failure detection
# ---------------------------------------------------------------------------

# The vocabulary a failed run prints, grouped by where it comes from. This is a
# catalogue of the *fail markers* the common toolchains emit, not a list of
# scenarios: every entry is a token the ecosystem emits verbatim, so a project on
# a toolchain not listed degrades to the ordinary lane rather than misbehaving.
# Extend by appending to the tuple rather than by branching on tool identity.
FAILURE_LINE_RE: re.Pattern[str] = re.compile(
    # Python
    r"Traceback \(most recent call last\)"
    r"|\b(?:AssertionError|SyntaxError|IndentationError|NameError|TypeError"
    r"|ValueError|KeyError|IndexError|AttributeError|RuntimeError"
    r"|ImportError|ModuleNotFoundError|ZeroDivisionError|RecursionError)\b"
    # JS / TS
    r"|\berror TS\d{4}\b"
    r"|\b(?:TypeError|ReferenceError|SyntaxError|RangeError):\s"
    # Go
    r"|\bpanic:\s"
    r"|^--- FAIL:\s"
    # Rust
    r"|^error\[E\d{4}\]"
    r"|panicked at "
    # Generic test / build failure markers
    r"|^\s*=*\s*(?:FAILURES|ERRORS?|SHORT TEST SUMMARY|ERROR SUMMARY)\b"
    r"|^\s*_{3,}\s*\S.*_{3,}\s*$"  # pytest names the failing test in an underscore banner
    r"|^\s*(?:FAILED|FAIL|ERROR|error):"
    r"|\bFAILED\b"
    # Runners pad their summary line with '=' on both sides, so the count is not
    # at the start of the line: "===== 1 failed, 399 passed in 4.21s =====".
    r"|^\s*=*\s*\d+ (?:failed|failing|errors?)\b"
    r"|\b(?:npm|pnpm|yarn) ERR!"
    r"|\b(?:make|cmake)\[?\d*\]?: \*\*\*"
    # Shell / process exit
    r"|\bexit(?:\s+status|\s+code|ed with (?:code|status))\s*[:=]?\s*[1-9]\d*\b"
    r"|\bSegmentation fault\b"
    # Visual markers used by runners and CI reporters
    r"|\bFAILED\b|✗|✘|❌|●\s",
    re.MULTILINE,
)

# A failure report is worth a budget of its own. The ordinary lane exists to
# keep the common case small; the failure lane exists so a diagnostic the model
# needs in order to fix something is not trimmed to the point of being useless.
# A failing 5 000-line log costs more to keep than a passing one saves, so the
# budget stays a bound rather than a promise.
FAILURE_MIN_CHARS = 4_000

# How many failure lines to preserve verbatim when a report has to be cut. Errors
# cluster at the two ends of a transcript — the command that ran at the top, the
# traceback at the bottom — so the ends are what get kept when the middle does
# not fit.
FAILURE_LINE_BUDGET = 40


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


def is_failed_result(msg: dict) -> bool:
    """True when the tool itself reported failure.

    Decided from the structured ``tool_status`` stamp the loop attaches, so this
    never depends on the model-visible header wording. Falls back to the header
    only for messages written before the stamp existed.
    """
    status = msg.get("tool_status")
    if isinstance(status, str) and status:
        return status != "ok"
    content = msg.get("content")
    if isinstance(content, str) and content.startswith("[Tool:"):
        return "Status: FAILED" in content.split("\n", 1)[0]
    return False


def failure_lines(text: str, limit: int = FAILURE_LINE_BUDGET) -> list[str]:
    """Lines of *text* that report a failure, in document order."""
    if not text:
        return []
    hits = [line for line in text.splitlines() if FAILURE_LINE_RE.search(line)]
    return hits[:limit]


def has_failure_report(content: str, tool_name: str) -> bool:
    """True when *content* is a transcript that reports a failure.

    Only meaningful for capture tools. The payload of ``file_read`` or
    ``grep`` legitimately contains the word "error" — it is source code or a
    match — and scanning it would mark ordinary reads as failures and exempt
    them from compaction forever. Whether a tool *emits diagnostics* is a
    property of the tool, so it is decided by the tool, not by the text.

    ``TERMINAL_OUTPUT_TOOLS`` is imported lazily: this module is loaded by the
    compaction path, which sits above the toolkit in the import graph, and a
    top-level import would close that cycle.
    """
    if not content:
        return False
    from server.toolkit.executor import TERMINAL_OUTPUT_TOOLS

    if tool_name not in TERMINAL_OUTPUT_TOOLS:
        return False
    return bool(FAILURE_LINE_RE.search(content))


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


def _split_result_header(content: str) -> tuple[str, str]:
    """Split a formatted tool result into its status header and its body.

    The first line is the ``[Tool: name | Status: …]`` banner and is part of the
    contract the model reads; trimming into it produces output whose first line
    no longer says what produced it.
    """
    head, sep, rest = content.partition("\n")
    return (head, rest) if sep else (content, "")


def bound_failure_result(content: str, max_chars: int) -> str:
    """Bound a result that reports a failure, preserving the diagnosis.

    The head/tail trim used for ordinary output is the wrong shape here: it
    keeps the first and last lines of a transcript, which for a failing run is
    the command echo and the summary — precisely the two parts that do not say
    what went wrong. This keeps the lines that do.

    A result already within budget is returned untouched, so the common case of
    a short failure costs nothing.
    """
    if len(content) <= max_chars:
        return content
    header, body = _split_result_header(content)
    lines = failure_lines(body)
    if not lines:
        # Unreachable when has_failure_report() gated the call, but the
        # function has to be total: a caller that reaches it with no failure
        # lines has no basis for choosing a better cut than the generic one.
        return _bound_ordinary_result(content, max_chars)
    budget = max(0, max_chars - len(header) - 1)
    kept = "\n".join(lines)
    if len(kept) > budget:
        kept = "\n".join(_fit_lines_to_budget(lines, budget))
    return f"{header}\n{kept}"


def _fit_lines_to_budget(lines: list[str], budget: int) -> list[str]:
    """Take lines from both ends of *lines* until *budget* characters are used.

    Split on characters, not on a line count. Two failure lines can differ by
    three orders of magnitude in length — one exception, one stack frame — so a
    split expressed in lines silently overshoots a small budget and underspends
    a large one.

    The head is weighted heavier because a transcript's opening carries the
    command and its options while the tail is usually a summary count.
    """
    head_budget = budget * 2 // 3
    tail_budget = budget - head_budget

    def _take(seq: list[str], allowance: int, from_end: bool) -> tuple[list[str], int]:
        picked: list[str] = []
        used = 0
        source = reversed(seq) if from_end else seq
        for line in source:
            cost = len(line) + 1
            if used + cost > allowance:
                break
            picked.append(line)
            used += cost
        if from_end:
            picked.reverse()
        return picked, used

    head, _ = _take(lines, head_budget, from_end=False)
    tail, _ = _take(lines, tail_budget, from_end=True)
    omitted = len(lines) - len(head) - len(tail)
    if omitted <= 0:
        return lines
    marker = [f"... [{omitted} failure lines omitted] ..."]
    return [*head, *marker, *tail]


def _bound_ordinary_result(content: str, max_chars: int) -> str:
    header, body = _split_result_header(content)
    if not body or len(body) <= max_chars:
        return content
    trimmed, _ = head_tail_trim(body, max_chars)
    return f"{header}\n{trimmed}"


def bound_tool_message(msg: dict, max_chars: int) -> CompactionStats:
    """Bound one tool-result message in place. The single bounding rule.

    Three call sites used to each carry their own copy of "digest it if it has a
    digest, otherwise trim the middle", and they had drifted: one compared the
    trimmed span against the limit, another compared the whole message, and only
    two of them counted the saving. One rule, one threshold meaning, one set of
    statistics — a caller chooses *which* messages are in scope and this decides
    what happens to them.

    Lanes, most protective first:

    * already bounded — no-op, which is what makes repeated passes cheap;
    * failure — see :func:`bound_failure_result`;
    * digest available and the tool is not content-bearing — collapse to it;
    * otherwise — keep the status header, trim the middle of the body.
    """
    stats = CompactionStats()
    content = msg.get("content")
    if not isinstance(content, str) or not content:
        return stats
    stats.original_chars = len(content)
    stats.compacted_chars = stats.original_chars
    if msg.get("time") == "compacted":
        return stats

    tool_name = _message_tool_name(msg)
    failure = is_failed_result(msg) or has_failure_report(content, tool_name)

    if failure:
        bounded = bound_failure_result(content, max(max_chars, FAILURE_MIN_CHARS))
    elif "digest" in msg and tool_name not in PRESERVE_ON_COMPACT:
        bounded = str(msg["digest"])
    else:
        bounded = _bound_ordinary_result(content, max_chars)
    if bounded == content:
        return stats
    msg["content"] = bounded
    msg["time"] = "compacted"
    stats.trimmed = True
    stats.compacted_chars = len(bounded)
    stats.chars_removed = max(0, stats.original_chars - stats.compacted_chars)
    stats.tokens_saved = stats.chars_removed // CHARS_PER_TOKEN
    stats.reason = "failure detail retained" if failure else "bounded"
    return stats


def merge_compaction_stats(target: CompactionStats, source: CompactionStats) -> CompactionStats:
    """Accumulate one message's bounding result into a caller's total."""
    target.original_chars += source.original_chars
    target.ansi_sequences_removed += source.ansi_sequences_removed
    target.ansi_stripped_chars += source.ansi_stripped_chars
    target.compacted_chars += source.compacted_chars
    target.chars_removed += source.chars_removed
    target.tokens_saved += source.tokens_saved
    target.trimmed = target.trimmed or source.trimmed
    if source.reason and not target.reason:
        target.reason = source.reason
    return target


def prune_inflight_messages(
    messages: list[dict],
    keep_latest_tools: int,
    max_output: int = 1000,
) -> tuple[list[dict], CompactionStats]:
    """Bound in-flight tool results in active conversation memory.

    The newest ``keep_latest_tools`` results are left alone: the model is
    currently reasoning over them. Older ones go through
    :func:`bound_tool_message`, which decides between the failure, digest and
    trim lanes.

    ``keep_latest_tools`` is required rather than defaulted: a default here
    silently drifted from the value the agent loop actually passes, so the
    signature looked configurable while the call site was fixed. Pass
    ``COMPACTION_KEEP_LATEST_TOOLS``.

    Returns a new list; the input messages are not modified, so the caller can
    re-render at a larger budget and get the full-fidelity content back.
    """
    stats = CompactionStats()
    if not messages:
        return ([], stats)

    tool_indices = [i for i, msg in enumerate(messages) if is_tool_message(msg)]
    # Slicing with ``[:-keep]`` reads as "all but the last N" but evaluates to
    # empty when N is 0, which would silently protect every result rather than
    # none. Stating the intent directly keeps 0 meaning what it says.
    protected = set(tool_indices[len(tool_indices) - keep_latest_tools :]) if keep_latest_tools else set()

    bounded: list[dict] = []
    for i, msg in enumerate(messages):
        content = msg.get("content")
        if i not in protected and is_tool_message(msg) and isinstance(content, str):
            copy = dict(msg)
            merge_compaction_stats(stats, bound_tool_message(copy, max_output))
            bounded.append(copy)
        else:
            if isinstance(content, str):
                stats.original_chars += len(content)
                stats.compacted_chars += len(content)
            bounded.append(msg)
    return (bounded, stats)
