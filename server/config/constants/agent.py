"""Agent loop, mode, and session constants.

Owns agent-mode identifiers, salvage-pass behavior, terminal verdicts/handoff
placeholders, session-state/running-summary caps, and loop tool-behavior knobs.
Leaf module: all cross-constant references are internal to this submodule.
"""

BUILD_MODE = "build"
PLAN_MODE = "plan"
READ_ONLY_MODE = "read_only"
CREWMATE_MODE = "crewmate"

READ_ONLY_TOOLS = ["file_read", "glob", "grep", "list_dir"]

# ---- WP3: salvage pass ------------------------------------------------------
# Any harness-forced exit (stall cap, repetition-loop cap, iteration budget)
# must never discard the turn's accumulated evidence. One tools-free
# completion converts the gathered context into a best-effort answer.
SALVAGE_INSTRUCTION = (
    "You have run out of steps for this turn. Produce your FINAL ANSWER now "
    "using only the evidence already gathered in this conversation. No tools "
    "are available. State concisely: what you found or changed, what you "
    "verified, and what remains unresolved."
)
DEFAULT_SALVAGE_TIMEOUT_SECONDS = 60.0
SALVAGE_TIMEOUT_ENV = "ZENITH_SALVAGE_TIMEOUT"
# Fallback digest size when the salvage completion itself fails.
SALVAGE_DIGEST_MAX_ITEMS = 10

# Turn-manifest verdicts (AGENT_RELIABILITY_PLAN P1): one terminal verdict per
# run, derived once at finalization and rendered consistently everywhere.
TURN_VERDICT_COMPLETED = "completed"
TURN_VERDICT_STALLED = "stalled"
# Terminal-status labels for assistant-message persistence. The placeholder
# must reflect what actually ended the turn — never a guess.
TERMINAL_STATUS_COMPLETED = "completed"
TERMINAL_STATUS_CANCELLED = "cancelled"
TERMINAL_STATUS_ERROR = "error"
HANDOFF_PLACEHOLDER_CANCELLED = "[Cancelled by user]"
HANDOFF_PLACEHOLDER_ERROR = "[Turn ended with an error]"
HANDOFF_PLACEHOLDER_NO_SUMMARY = "[No summary recorded]"
BG_OUTPUT_TAIL = 800
MANIFEST_CHECKS_CAP = 5
RUNNING_SUMMARY_MESSAGE_LIMIT = 50
SESSION_STATE_MAX_TOKENS = 400
SESSION_STATE_MARKER = "[Session state]"
SESSION_STATE_HASH_PREFIX_LEN = 10
SESSION_STATE_ENTRY_MAX_CHARS = 200

# Progress-step labels embed a short detail snippet from the tool params
# (command/path/pattern) so the UI shows WHAT ran, not just "Running commands".
PROGRESS_DETAIL_MAX_CHARS = 48

# Tools that mutate files — used to distinguish "tried to build but wrote
# nothing" (worth warning about) from pure Q&A turns (not).
FILE_MUTATING_TOOLS = frozenset({"file_write", "file_edit"})

# Auto-generated session title cap (chars) before ellipsis.
SESSION_TITLE_MAX_CHARS = 50

EPHEMERAL_TOOL_WINDOW_SIZE = 2

POLL_TOOLS = ("job_output",)
