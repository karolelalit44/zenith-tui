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

# A failure report is worth a budget of its own. The ordinary lane exists to
# keep the common case small; the failure lane exists so a diagnostic the model
# needs in order to fix something is not trimmed to the point of being useless.
FAILURE_MIN_CHARS = 4_000

# How many diagnostic lines to preserve before the budget takes over and
# head/tail trimming of the survivors applies.
FAILURE_LINE_BUDGET = 160

# Failure nouns matched as whole words by the prioritiser. Kept here rather than
# inline so the set is one readable line and adding a toolchain's vocabulary does
# not mean editing a condition.
_FAILURE_WORDS = frozenset(
    {
        "abort",
        "aborted",
        "assert",
        "crash",
        "crashed",
        "denied",
        "err",
        "error",
        "errored",
        "exception",
        "fail",
        "failed",
        "failing",
        "failure",
        "failures",
        "fatal",
        "fault",
        "killed",
        "panic",
        "panicked",
        "rejected",
        "refused",
        "segfault",
        "timeout",
        "traceback",
        "uncaught",
    }
)

# ``TypeError``, ``NullPointerException`` and friends: a capitalised identifier
# ending in Error/Exception. Covers every language's exception vocabulary without
# listing it.
_EXCEPTION_NAME = re.compile(r"\b[A-Za-z_]\w*(?:Error|Exception)\b")


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
    """True when a line is worth preferring when a *failed* result is trimmed.

    This is a prioritiser, not a filter and not a lane selector. Two consequences
    of that distinction are load-bearing:

    * It only ever runs on a result the loop already stamped as failed, so a
      successful command whose output merely mentions a word like "fail" is
      never routed here. The earlier version called this from the lane selector
      and a green build log containing "duration: 15" was reduced to that one
      line — a command that succeeded, reported to the model as a fragment.
    * Whatever it selects is announced. Nothing is dropped in silence, so a
      misfire costs density rather than correctness.

    Deliberately loose. It runs only on a result that already failed, where the
    cost of keeping a line that turns out to be noise is a few characters.
    """
    s = line.strip()
    if not s:
        return False

    # Section banners and separators (=== FAILURES ===, ___ test ___, --- FAIL ---)
    if (s.startswith(("===", "___", "---", "***")) and len(s) >= 5) or (
        s.endswith(("===", "___", "---", "***")) and len(s) >= 5
    ):
        return True

    # Terminal error markers: pytest's E/F gutter, cargo/npm/ruff, and prose
    # that leads with the word rather than embedding it.
    if s.startswith(
        ("E ", "E\t", "F ", "!", "[!]", "[FAIL]", "[ERROR]", "Error:", "error:", "FAIL:", "FAILED:")
    ):
        return True
    if s.startswith(("✗", "✘", "❌")):
        return True

    # Stack frames and code positions.
    if (
        ("file " in s.lower() and "line " in s.lower())
        or ": in " in s
        or "-->" in s
        or (s.startswith("at ") and "(" in s and ")" in s)
        or _has_location(s)
    ):
        return True

    # Error nouns, anchored to a word boundary so "failover" and "tolerance" do
    # not match. A tool result that failed is worth this looseness.
    if _has_failure_word(s):
        return True

    # Language-level exception names (TypeError, NullPointerException). Matching
    # the *shape* rather than enumerating every runtime's vocabulary.
    if _EXCEPTION_NAME.search(s):
        return True

    lowered = s.lower()
    if "exit status " in lowered or "exit code " in lowered or "exited with code " in lowered:
        return not (
            "exit status 0" in lowered or "exit code 0" in lowered or "exited with code 0" in lowered
        )

    return False


def _has_location(line: str) -> bool:
    """True for ``path:123`` / ``path:123:45`` style positions.

    Requires a numeric tail *and* a path-shaped head, so prose such as
    ``duration: 15`` — which a successful build log is full of — is not treated
    as a code location.
    """
    if ":" not in line:
        return False
    head, _, tail = line.rpartition(":")
    if not tail.isdigit():
        return False
    return "/" in head or "\\" in head or "." in head


def _has_failure_word(line: str) -> bool:
    """True when a failure noun appears in *line* as a whole word."""
    words = set(re.findall(r"[a-z]+", line.lower()))
    if not words & _FAILURE_WORDS:
        return False
    # "0 errors" is the report of a clean run.
    return not re.fullmatch(r"\d+ (error|errors|warning|warnings|fail|fails|failure|failures)", line.strip().lower())


def failure_lines(text: str, limit: int = FAILURE_LINE_BUDGET) -> list[str]:
    """Lines of *text* worth preferring when a failed result is trimmed."""
    if not text:
        return []
    hits = [line for line in text.splitlines() if is_diagnostic_line(line)]
    return hits[:limit]




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
    """Bound a result the tool reported as failed, keeping its diagnosis.

    Picks the lines most likely to say what went wrong, then fits them to the
    budget. The one invariant this must not break: **any line it drops is
    announced.** A trim that silently deletes body text leaves the model
    reasoning about a command it has been shown only part of, and nothing in the
    output distinguishes that from a complete result.

    Falls back to the ordinary head/tail trim when nothing in the body looks
    diagnostic, so a failed result that is just large is not filtered down to
    whatever happened to match.
    """
    if len(content) <= max_chars:
        return content
    header, body = _split_result_header(content)
    if not body:
        return content

    lines = body.splitlines()
    picked = failure_lines(body, limit=FAILURE_LINE_BUDGET)
    if not picked:
        return _bound_ordinary_result(content, max_chars)

    budget = max(0, max_chars - len(header) - 1)
    omitted_from_body = len(lines) - len(picked)
    return f"{header}\n" + "\n".join(_fit_lines(picked, budget, omitted_from_body))


def _fit_lines(lines: list[str], budget: int, omitted_from_body: int) -> list[str]:
    """Fit *lines* to *budget*, keeping both ends and counting what is dropped.

    Two-thirds from the top, one-third from the bottom: a report states the
    command first and the summary last, so the ends carry more than the middle.
    """
    cost = sum(len(line) + 1 for line in lines)
    if cost <= budget:
        if omitted_from_body <= 0:
            return lines
        return [*lines, f"... [{omitted_from_body} line(s) omitted: kept diagnostic lines only] ..."]

    head_budget = budget * 2 // 3
    tail_budget = budget - head_budget

    def _take(source: list[str], allowance: int, from_end: bool) -> list[str]:
        picked: list[str] = []
        used = 0
        ordered = reversed(source) if from_end else source
        for line in ordered:
            step = len(line) + 1
            if used + step > allowance:
                break
            picked.append(line)
            used += step
        if from_end:
            picked.reverse()
        return picked

    head = _take(lines, head_budget, from_end=False)
    tail = _take(lines, tail_budget, from_end=True)
    omitted = omitted_from_body + (len(lines) - len(head) - len(tail))
    if omitted <= 0:
        return lines
    return [*head, f"... [{omitted} line(s) omitted] ...", *tail]




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
    * failure — see :func:`bound_failure_result`. Entered on the structured
      ``tool_status`` stamp alone. It is deliberately not also entered on what
      the output *looks* like: a successful build log mentioning an error is a
      success, and routing it through a filter that keeps "diagnostic-looking"
      lines reduces a green run to an arbitrary fragment of itself;
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
    failure = is_failed_result(msg)

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
