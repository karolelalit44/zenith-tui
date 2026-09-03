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

ANSI_RE = re.compile(
    r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*(?:\x07|\x1b\\)|\x1b[PXQ^_][^\x1b]*\x1b\\|\x1b[()][A-Za-z0-9]"
)


# --- module 01 (turn/loop) ---
# New opencode/codex-style loop design knobs. Additive-only additions.
# The loop stops emergently when the model emits no tool calls, so the only
# bounds are one advisory step nudge and one safety guard against a repetitive
# tool loop.
DOOM_LOOP_THRESHOLD = (
    3  # consecutive identical (name + input) tool calls → ask permission before continuing
)
MAX_STEPS_DEFAULT = (
    1_000_000  # advisory step cap (opencode/agent.steps default Infinity); never hit in practice
)
MAX_STEPS_PROMPT = (
    "You have been working on this task for a very long time. Wrap up: finish the current "
    "step, then produce your final answer. Do not start new tool calls."
)


def default_max_tokens_for_context(context_window: int) -> int:
    return max(DEFAULT_LLM_MAX_TOKENS, min(context_window // 2, MAX_OUTPUT_TOKENS_CLAMP))
