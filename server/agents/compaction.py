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

# ---------------------------------------------------------------------------
# Failure detection
# ---------------------------------------------------------------------------

# A failure report is worth a budget of its own. The ordinary lane exists to
# keep the common case small; the failure lane exists so a diagnostic the model
# needs in order to fix something is not trimmed to the point of being useless.
FAILURE_MIN_CHARS = 4_000

# How many failure lines to preserve when a report has to be cut. Errors
# cluster at the tail of a transcript — the command at the top, the traceback
# at the bottom — so the ends are what get kept when the middle does not fit.
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
    never depends on model-visible prose. Falls back to the header only for
    messages written before the stamp existed.
    """
    status = msg.get("tool_status")
    if isinstance(status, str) and status:
        return status != "ok"
    content = msg.get("content")
    if isinstance(content, str) and content.startswith("[Tool:"):
        header = content.partition("\n")[0]
        return "Status: FAILED" in header or "Status: ERROR" in header
    return False


def is_diagnostic_line(line: str) -> bool:
    """True when a line carries failure or diagnostic context.

    Evaluates structural characteristics: banners, stack frames, error markers,
    and assertion traces, without hardcoded language dictionaries or fragile regexes.
    """
    s = line.strip()
    if not s:
        return False

    # 1. Section banners and separators (=== FAILURES ===, ___ test ___, --- FAIL ---)
    if (s.startswith(("===", "___", "---", "***")) and len(s) >= 5) or (
        s.endswith(("===", "___", "---", "***")) and len(s) >= 5
    ):
        return True

    # 2. Terminal error markers
    if s.startswith(("E ", "E\t", "F ", "!", "[!]", "[FAIL]", "[ERROR]", "Error:", "error:", "FAIL:", "FAILED:")):
        return True

    if s.startswith(("✗", "✘", "❌")) or "● " in s:
        return True

    lower = s.lower()
    # 3. Stack trace frames and code positions
    if (
        ("file " in lower and "line " in lower)
        or (": in " in s)
        or ("-->" in s)
        or (s.startswith("at ") and "(" in s and ")" in s)
    ):
        return True

    parts = s.split(":", 2)
    if len(parts) >= 2 and parts[1].strip().isdigit():
        return True

    # 4. Universal failure terms
    for term in (
        "error",
        "fail",
        "failed",
        "failing",
        "exception",
        "traceback",
        "panic",
        "panicked",
        "segmentation fault",
        "err!",
    ):
        if term in lower:
            if f"0 {term}" in lower or f"0 {term}s" in lower:
                continue
            return True

    if "exit status " in lower or "exit code " in lower or "exited with code " in lower:
        succeeded = "exit status 0" in lower or "exit code 0" in lower or "exited with code 0" in lower
        if not succeeded:
            return True

    return False


def failure_lines(text: str, limit: int = FAILURE_LINE_BUDGET) -> list[str]:
    """Lines of *text* that carry diagnostic or failure details, in document order."""
    if not text:
        return []
    hits = [line for line in text.splitlines() if is_diagnostic_line(line)]
    return hits[:limit]


def has_failure_report(content: str, tool_name: str) -> bool:
    """True when *content* is a transcript that reports a failure.

    Only meaningful for capture tools. Condition-oriented check without regex.
    """
    if not content:
        return False
    from server.toolkit.executor import TERMINAL_OUTPUT_TOOLS

    if tool_name not in TERMINAL_OUTPUT_TOOLS:
        return False
    header, sep, body = content.partition("\n")
    if header.startswith("[Tool:") and ("Status: FAILED" in header or "Status: ERROR" in header):
        return True
    target = body if sep else content
    for line in target.splitlines():
        if is_diagnostic_line(line):
            return True
    return False




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
    # Results relabelled rather than reduced: a read that a later edit
    # invalidated stays in context and gains a notice, so it costs a little and
    # protects correctness. Counting it as a saving would flatter the number.
    superseded: int = 0

    @property
    def changed(self) -> bool:
        return self.trimmed or self.superseded > 0


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
    """Bound a failed tool result while preserving diagnostic detail and traceback.

    Filters out high-volume repetitive noise (such as hundreds of passing test items)
    to retain failure banners, stack frames, file/line locations, and assertion errors.
    """
    if len(content) <= max_chars:
        return content
    header, body = _split_result_header(content)
    if not body:
        return content
    budget = max(0, max_chars - len(header) - 1)

    lines = failure_lines(body, limit=FAILURE_LINE_BUDGET * 4)
    if not lines:
        return _bound_ordinary_result(content, max_chars)

    kept = "\n".join(lines)
    if len(kept) <= budget:
        return f"{header}\n{kept}"

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
        return f"{header}\n" + "\n".join(lines)
    marker = [f"... [{omitted} failure lines omitted] ..."]
    return f"{header}\n" + "\n".join([*head, *marker, *tail])




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


# Tools whose result changes the file they name. A read of a path any of these
# has touched is describing a version of the file that no longer exists.
MUTATING_TOOLS: frozenset[str] = frozenset({"file_write", "file_edit", "file_delete", "apply_patch"})


def _normalise_path(raw: str) -> str:
    """Comparable form of a path as a message or a conversation might spell it."""
    return raw.replace("\\", "/").removeprefix("./").lstrip("/")


def dedupe_tool_results(messages: list[dict]) -> tuple[list[dict], CompactionStats]:
    """Collapse tool results the conversation has already paid for.

    Two reductions, both decided by walking the list newest-first so that only
    information *after* a result can supersede it:

    * **Stale reads.** Once a mutating tool has changed a path, every earlier read
      of that path describes a version of the file that is gone. The read stays in
      context but is relabelled, because the alternative — dropping it — leaves the
      model either re-reading a file it believes it has, or worse, editing from a
      version that no longer matches disk.
    * **Repeated reads.** A second read of a path already read in context is
      replaced with a pointer to the first, so the same file occupies the window
      once instead of once per re-read.

    Operates on copies: the entries on disk keep full fidelity, and a re-render at
    a larger budget recovers the original text.
    """
    stats = CompactionStats()
    if not messages:
        return ([], stats)

    mutated: set[str] = set()
    read_paths: dict[str, int] = {}
    out: list[dict] = list(messages)

    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if not is_tool_message(msg):
            continue
        tool = _message_tool_name(msg)
        raw_paths = msg.get("tool_paths")
        paths = [_normalise_path(str(p)) for p in raw_paths] if isinstance(raw_paths, list) else []

        if tool in MUTATING_TOOLS:
            mutated.update(paths)
            continue

        if tool != "file_read":
            continue
        content = msg.get("content")
        if not isinstance(content, str) or not paths:
            continue

        path = paths[0]
        already = read_paths.get(path)
        if already is not None:
            original = len(content)
            out[i] = {
                **msg,
                "content": _read_pointer(path, messages[already]),
                "time": "deduped",
            }
            stats.chars_removed += max(0, original - len(out[i]["content"]))
            continue
        read_paths[path] = i

        if path in mutated:
            out[i] = {
                **msg,
                "content": _stale_read_notice(path, content),
                "time": "deduped",
            }
            stats.superseded += 1

    stats.tokens_saved = stats.chars_removed // CHARS_PER_TOKEN
    stats.trimmed = stats.chars_removed > 0
    if stats.changed:
        stats.reason = "duplicate or superseded tool results"
    return (out, stats)


def _read_pointer(path: str, original: dict) -> str:
    content = original.get("content") or ""
    header = _split_result_header(content)[0] if isinstance(content, str) else ""
    return (
        f"[Superseded read of {path}: this file's content is already in context above "
        f"from an earlier read. Read it again only to see a range not already shown.]"
        + (f"\n{header}" if header else "")
    )


def _stale_read_notice(path: str, content: str) -> str:
    """Prefix a read that a later edit invalidated, keeping its body for reference."""
    header = _split_result_header(content)[0] if isinstance(content, str) else ""
    notice = (
        f"[Stale: {path} was changed after this read. The text below is the version as "
        f"read, not as it is now on disk. Re-read before editing it.]"
    )
    return f"{header}\n{notice}\n{content}" if header else f"{notice}\n{content}"


def normalise_tool_pairs(messages: list[dict]) -> tuple[list[dict], CompactionStats]:
    """Make a bounded message list safe to send, without inventing history.

    A request whose assistant turn declares tool calls the following messages do
    not answer is rejected outright by strict providers, and every pruning and
    bounding rule in this module can create that condition.

    The repair is *removal*, never synthesis. Tool results here carry no call
    id, so an unanswered call cannot be matched to a result that may or may not be
    its own — and inventing a result would put a fabricated "this call did nothing"
    into the model's history, which is a worse lie than an absent one. So a call
    that nothing answers is dropped from the declaring turn instead, leaving a turn
    that still says something and asks for nothing unanswered.

    A no-op on a list that was never pruned, which is the common case.
    """
    stats = CompactionStats()
    if not messages:
        return ([], stats)

    out: list[dict] = []
    i = 0
    dropped_calls = 0
    while i < len(messages):
        msg = messages[i]
        if not iter_tool_calls(msg):
            # A `role="tool"` result that names a call no turn declared is debris;
            # one that names no call is an external event, which is evidence.
            if msg.get("role") == "tool" and msg.get("tool_call_id"):
                stats.chars_removed += len(str(msg.get("content") or ""))
                stats.superseded += 1
            else:
                out.append(msg)
            i += 1
            continue

        # The results answering this turn are the consecutive tool messages that
        # follow it, up to the next non-tool message.
        answered = 0
        while i + 1 + answered < len(messages) and is_tool_message(messages[i + 1 + answered]):
            answered += 1
        results = messages[i + 1 : i + 1 + answered]

        if answered < len(msg["tool_calls"]):
            # Drop the trailing calls nothing answers, and their would-be results.
            keep = answered
            dropped_calls += len(msg["tool_calls"]) - keep
            if keep:
                trimmed = dict(msg)
                trimmed["tool_calls"] = msg["tool_calls"][:keep]
                out.append(trimmed)
                out.extend(results)
            else:
                # No call is left to answer, so the turn must not carry the key:
                # an empty `tool_calls` array is itself rejected by strict
                # providers. The turn's prose survives, so the model still has a
                # coherent account of what it was doing.
                out.append({k: v for k, v in msg.items() if k != "tool_calls"})
        else:
            out.append(msg)
            out.extend(results)
        i += 1 + answered

    if dropped_calls:
        stats.reason = f"{dropped_calls} unanswered tool call(s) removed"
    elif stats.superseded:
        stats.reason = "orphan tool result(s) dropped"
    stats.tokens_saved = stats.chars_removed // CHARS_PER_TOKEN
    return (out, stats)


def iter_tool_calls(msg: dict) -> list[tuple[str, str]]:
    """``(name, call_id)`` for every tool call an assistant turn declares.

    Tolerant of the three shapes a call takes in this codebase's history: the
    OpenAI ``tool_calls`` array it is stored with, and the flattened
    ``function.name`` / ``id`` pair older persisted turns may carry.
    """
    if msg.get("role") != "assistant":
        return []
    out: list[tuple[str, str]] = []
    for call in msg.get("tool_calls") or []:
        if not isinstance(call, dict):
            continue
        fn = call.get("function") or {}
        name = str(fn.get("name") or call.get("name") or "")
        if not name:
            continue
        out.append((name, str(call.get("id") or fn.get("id") or "")))
    if not out and msg.get("tool_name"):
        out.append((str(msg["tool_name"]), str(msg.get("tool_call_id") or "")))
    return out


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
