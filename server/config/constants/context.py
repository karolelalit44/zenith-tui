"""Context window, compaction, and loop-step constants.

Owns token-budget sizing, the context-exhaustion/compaction knobs, and the
advisory step-loop bounds. Depends only on ``web.py`` for the LLM max-tokens
default used by ``default_max_tokens_for_context``.
"""

import re

from .web import DEFAULT_LLM_MAX_TOKENS

CONTEXT_SUMMARY_THRESHOLD = 0.85
DEFAULT_CONTEXT_WINDOW = 128000

CHARS_PER_TOKEN = 4
SUMMARY_FRAMING_TOKENS = 4
MIN_OUTPUT_RESERVE_TOKENS = 8_000
HARD_STOP_USAGE_RATIO = 0.95
CONTEXT_EXHAUSTED_MESSAGE = "Context window exhausted even after summarization"
CONTEXT_EXHAUSTED_HINT = "Start a new session to free up context."
COMPACTION_KEEP_TAIL = 8
# How many of the most recent tool results survive in-flight pruning at full
# fidelity. One constant, read by both the pruner and the agent loop, so the two
# cannot drift: a default that silently differs from the caller's argument looks
# configured but is not.
COMPACTION_KEEP_LATEST_TOOLS = 6
# Recent-history budget for compaction: keep this many tokens of the tail when
# folding the older prefix into the summary. The band is clamped to the input
# budget so small windows never request more than the context can hold.
COMPACTION_KEEP_MIN_TOKENS = 8_000
COMPACTION_KEEP_MAX_TOKENS = 20_000
COMPACTION_KEEP_BUDGET_RATIO = 0.25
SKIP_WARNING_CAP = 6
SUMMARY_MIN_CHARS = 40
# Consecutive do-nothing iterations (every emitted call was a duplicate)
# before the loop stops the turn. Duplicate feedback itself is delivered
# in-band per call; this cap only bounds wasted iterations.
STALL_FINALIZE_AFTER_ITERATIONS = 2
# Max chars of a prior tool result embedded into an in-band duplicate-call
# blocked notice.
DUP_RESULT_PREVIEW_CHARS = 1_200

SMALL_CONTEXT_WINDOW = 32_000
LARGE_CONTEXT_WINDOW = 200_000
MAX_OUTPUT_TOKENS_CLAMP = 32_768

# Repo-map share of the context window. The map is orientation, not payload: it
# is the first thing to cut when the window is tight, and the last thing worth
# spending a large window on. Named so the ratio is a decision on record rather
# than an inline literal in the agent layer.
REPO_MAP_WINDOW_RATIO = 0.05
REPO_MAP_MIN_TOKENS = 100
REPO_MAP_MAX_TOKENS = 1_024
# The agent creates and edits files while it runs, so a map frozen at turn 1
# describes a workspace that no longer exists. Rebuild when the catalog's mtime
# or size moves past what was last rendered.
REPO_MAP_STALE_AFTER_SECONDS = 30.0

# Smallest generation ceiling worth deriving. Below this a window cannot hold a
# prompt and a usable reply together, so the ceiling stops being a budget and
# becomes the whole allocation.
MIN_OUTPUT_TOKENS_FLOOR = 1_024

ANSI_RE = re.compile(
    r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*(?:\x07|\x1b\\)|\x1b[PXQ^_][^\x1b]*\x1b\\|\x1b[()][A-Za-z0-9]"
)


# --- module 01 (turn/loop) ---
# New opencode/codex-style loop design knobs. Additive-only additions.
# The loop stops emergently when the model emits no tool calls, so the only
# bound is one safety guard against a repetitive tool loop.
DOOM_LOOP_THRESHOLD = (
    3  # consecutive identical (name + input) tool calls → warn and stop the turn for human review
)
MAX_STEPS_DEFAULT = (
    25  # safety net iteration cap for a single turn; triggers salvage if budget exhausted
)


def default_max_tokens_for_context(context_window: int) -> int:
    """Generation ceiling for a model of the given window.

    The generation ceiling is charged against the same window as the prompt, so
    it is derived from a share of the window rather than from a flat default. A
    flat default is not merely inelegant here, it is unsound: on a small-window
    model it yields a ceiling larger than the entire window, which guarantees the
    provider rejects or truncates the request instead of reserving room for the
    prompt that has to accompany it. The window is therefore the outer bound,
    whatever the floor would prefer.

    The lower bound is not cosmetic either. Output budgets are elastic and a cap
    set too low is exceeded by more than a comfortable cap would have been, so
    the floor keeps the ceiling a real budget rather than a formality — except
    on a window too small to afford one, where obeying it would leave the prompt
    no room at all.
    """
    if context_window <= 0:
        return DEFAULT_LLM_MAX_TOKENS
    return min(
        context_window,
        max(MIN_OUTPUT_TOKENS_FLOOR, min(context_window // 2, MAX_OUTPUT_TOKENS_CLAMP)),
    )
