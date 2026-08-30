import re

from .env import optional_int

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
HOST_ENV_VAR = "ZENITH_HOST"
PORT_ENV_VAR = "ZENITH_PORT"
WS_PATH = "/ws"
HEALTH_PATH = "/health"

TEST_WS_PATH = "/ws/test"
TEST_SIMULATION_DIR = "data/simulation"
TEST_SIMULATION_DIR_ENV = "ZENITH_SIMULATION_DIR"
CONTEXT_SUMMARY_THRESHOLD = 0.85
DEFAULT_CONTEXT_WINDOW = 128000
BUILD_MODE = "build"
PLAN_MODE = "plan"
READ_ONLY_MODE = "read_only"
CREWMATE_MODE = "crewmate"

READ_ONLY_TOOLS = ["file_read", "glob", "grep", "list_dir"]

# Per-mode context-budget allocation (Gap #8). Fractions of the input budget
# (context window minus output reserve). History absorbs a larger share in
# investigation-heavy modes; tool schemas get a smaller share in read_only.
MODE_BUDGET_PROFILES = {
    BUILD_MODE: {"tools_pct": 0.10, "history_pct": 0.40, "summary_pct": 0.05},
    PLAN_MODE: {"tools_pct": 0.08, "history_pct": 0.50, "summary_pct": 0.05},
    READ_ONLY_MODE: {"tools_pct": 0.05, "history_pct": 0.55, "summary_pct": 0.05},
}

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

# ---- Progressive efficiency guidance (adaptive harness) --------------------
# Instead of hard iteration caps, the system injects increasingly urgent
# guidance messages when token consumption is high relative to progress.
# Each level is a (token_threshold, message) pair. Messages are injected
# as in-band user-role hints — the model sees them as system feedback,
# not as tool results. The model decides whether to act on them.
#
# The thresholds are cumulative run-level tokens (prompt + completion),
# not context-window occupancy. This tracks actual cost, not capacity.
PROGRESSIVE_GUIDANCE_LEVELS: list[tuple[int, str]] = [
    (
        40_000,
        "[harness] You have used ~40K tokens this turn. If you have enough "
        "evidence to answer, write your final response now — do not issue "
        "more tool calls unless strictly necessary.",
    ),
    (
        70_000,
        "[harness] ~70K tokens consumed. You are approaching the point of "
        "diminishing returns. Synthesize what you have and deliver your "
        "answer. Additional exploration is unlikely to change the outcome.",
    ),
    (
        100_000,
        "[harness] ~100K tokens — this turn is expensive. Stop exploring. "
        "Write your final answer from the evidence already gathered.",
    ),
]
# Iteration-count guidance: fires based on LLM-call count, not tokens.
# This catches research-heavy turns where each call is cheap but the model
# keeps reading files instead of synthesizing.
#
# Thresholds are intentionally generous: a genuine analysis/research task
# routinely needs more than a handful of calls (grep -> glob -> read several
# files -> cross-check) just to gather the key facts. Firing at 3 calls
# pressures the model to halt before it has enough evidence, which degrades
# answer quality. These levels are advisory signals, not hard caps — the
# model still decides whether to act on them.
ITERATION_GUIDANCE_LEVELS: list[tuple[int, str]] = [
    (
        6,
        "[harness] You have made 6 LLM calls. If you already have the key "
        "facts needed to answer, synthesize your answer now — further tool "
        "calls add latency without meaningfully improving the response. If "
        "evidence is still incomplete, continue gathering it.",
    ),
    (
        10,
        "[harness] 10 LLM calls now. Most questions are answerable by this "
        "point. If you have enough evidence, stop exploring and deliver your "
        "answer; otherwise finish only the remaining targeted lookups.",
    ),
    (
        14,
        "[harness] 14 LLM calls — this turn is unusually long for a research "
        "question. Wrap up: provide your answer from what you have, or make "
        "at most one or two final targeted calls before concluding.",
    ),
]

# ---- WP5: explore delegation (Apogee crewmate) -------------------------------
# Model-invocable read-only exploration backed by the Captain/Crewmate pathway.
# Named for the highest point of an orbit — kin to Zenith itself.
EXPLORE_TOOL = "explore"
APPOGEE_AGENT_ID = "apogee"
APPOGEE_AGENT_NAME = "Apogee"
APPOGEE_AGENT_ROLE = "Codebase Cartographer"
# Thoroughness -> mission budget. Timeout bounds wall clock; context_tokens
# bounds the child's own window; max_turns is advisory steering for deep runs.
EXPLORE_BUDGETS: dict[str, dict[str, int]] = {
    "quick": {"timeout_s": 45, "context_tokens": 32_000},
    "standard": {"timeout_s": 90, "context_tokens": 64_000},
    "deep": {"timeout_s": 150, "context_tokens": 96_000},
}
EXPLORE_THOROUGHNESS_LEVELS = ("quick", "standard", "deep")
DEFAULT_EXPLORE_THOROUGHNESS = "standard"
# Parallel explores per assistant turn (D1): CAID puts the analytical cliff at
# ~2; 4 is a hard ceiling, not a target.
EXPLORE_PARALLEL_DEFAULT = 2
EXPLORE_PARALLEL_MAX = 4
# Aggregate spend guard across explore children within the rolling window (D6).
EXPLORE_TOKEN_BUDGET_ENV = "ZENITH_EXPLORE_TOKEN_BUDGET"
DEFAULT_EXPLORE_TOKEN_BUDGET = 120_000
EXPLORE_BUDGET_WINDOW_SECONDS = 600.0
# Governance modes (D3): off | tool | proactive.
EXPLORE_DELEGATION_OFF = "off"
EXPLORE_DELEGATION_TOOL = "tool"
EXPLORE_DELEGATION_PROACTIVE = "proactive"
EXPLORE_DELEGATION_MODES = (
    EXPLORE_DELEGATION_OFF,
    EXPLORE_DELEGATION_TOOL,
    EXPLORE_DELEGATION_PROACTIVE,
)
EXPLORE_DELEGATION_ENV = "ZENITH_EXPLORE_DELEGATION"
DEFAULT_EXPLORE_DELEGATION = EXPLORE_DELEGATION_TOOL
# Rendered report cap entering parent context (S2: <= ~2 KB).
EXPLORE_RESULT_MAX_CHARS = 2_000
# Custom crewmate runtime definitions (bounded free-text).
EXPLORE_CUSTOM_NAME_MAX_CHARS = 32
EXPLORE_CUSTOM_ROLE_MAX_CHARS = 48
EXPLORE_CUSTOM_FOCUS_MAX_CHARS = 600

# ---- WP6: structural retrieval (graph queries + mission brief) ---------------
# Crewmate-facing structural query tools over the tree-sitter symbol graph.
CODE_CALLERS_TOOL = "code_callers"
CODE_OUTLINE_TOOL = "code_outline"
CODE_BLAST_RADIUS_TOOL = "code_blast_radius"
CREWMATE_GRAPH_TOOLS = (CODE_CALLERS_TOOL, CODE_OUTLINE_TOOL, CODE_BLAST_RADIUS_TOOL)
GRAPH_QUERY_MAX_RESULTS = 20
GRAPH_QUERY_MAX_OUTPUT_CHARS = 4_000
# Mission brief injected into the crewmate prompt at spawn (CrewmateStart pattern).
EXPLORE_BRIEF_TOP_SYMBOLS = 12
EXPLORE_BRIEF_MAX_CHARS = 1_600
BRIEF_CACHE_TTL_SECONDS = 60.0
# Objective enrichment pre-pass (Deep Research instruction-builder pattern).
ENRICH_TIMEOUT_ENV = "ZENITH_ENRICH_TIMEOUT"
DEFAULT_ENRICH_TIMEOUT_SECONDS = 20.0
# Skip enrichment when the objective already reads like a research brief.
ENRICH_SKIP_MIN_CHARS = 120
ENRICH_DELIVERABLE_VERBS = (
    "find",
    "locate",
    "map",
    "trace",
    "list",
    "identify",
    "compare",
    "audit",
)
# Max previously-stored tool results replayed into context on a duplicate-call
# pass (gives the model its prior result instead of an empty correction).
TOOL_RESULT_REPLAY_CAP = 2
# Meta-placeholder texts some weak models emit instead of content (or instead
# of real tool calls). They are never rendered to the user as answers.
DEGENERATE_MESSAGE_PATTERN = r"^\[?\s*(tool\s*calls?|thinking|no\s*output)\s*\]?$"
# Turn-manifest verdicts (AGENT_RELIABILITY_PLAN P1): one terminal verdict per
# run, derived once at finalization and rendered consistently everywhere.
TURN_VERDICT_COMPLETED = "completed"
TURN_VERDICT_STALLED = "stalled"
TURN_VERDICT_FAILED = "failed"
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
SESSION_STATE_MAX_FILES = 50
SESSION_STATE_MARKER = "[Session state]"
SESSION_STATE_HASH_PREFIX_LEN = 10
SESSION_STATE_ENTRY_MAX_CHARS = 200
SESSION_STATE_INTRO = (
    "Files you already created or modified earlier in this session (they exist on "
    "disk; do not re-create or re-write them unless you are changing them):"
)
SESSION_STATE_OUTRO = (
    "If you need to modify one of these, read it first (file_read), then use "
    "file_edit for a targeted change."
)

STALE_TOKEN_MULTIPLIER = 2
HEAVY_TOOL_THRESHOLD_TOKENS = 8000
# Deterministic head/tail preview (chars) kept in-context when a heavy tool
# output is isolated to disk. No LLM summarization: the model decides whether
# to re-read the full output via the stored path.
HEAVY_TOOL_ISOLATION_PREVIEW_CHARS = 8_000
HEAVY_OUTPUT_SUBDIR = "heavy-outputs"
HEAVY_TOOL_MARKER_TEMPLATE = (
    "Output truncated ({total_chars} chars total). Full output available via file_read: {path}"
)

# Progress-step labels embed a short detail snippet from the tool params
# (command/path/pattern) so the UI shows WHAT ran, not just "Running commands".
PROGRESS_DETAIL_MAX_CHARS = 48

# Tools that mutate files — used to distinguish "tried to build but wrote
# nothing" (worth warning about) from pure Q&A turns (not).
FILE_MUTATING_TOOLS = frozenset({"file_write", "file_edit", "multi_edit"})

# Auto-generated session title cap (chars) before ellipsis.
SESSION_TITLE_MAX_CHARS = 50

# Emit a partial thinking event once this many new reasoning chars accumulated.
THINKING_PARTIAL_EMIT_CHARS = 200
PROJECT_MEMORY_MAX_TOKENS = 500
PROJECT_MEMORY_MAX_ENTRIES = 20

SMALL_CONTEXT_WINDOW = 32_000
LARGE_CONTEXT_WINDOW = 200_000
MAX_OUTPUT_TOKENS_CLAMP = 32_768

TOOL_GUIDELINES_DIR = ""
TOOL_GUIDELINES_FILE_NAME = "tool-guidelines.md"

MAX_TOOL_NAME_LENGTH = 64
MAX_TOOL_DESCRIPTION_LENGTH = 400
MAX_CAPABILITY_DESCRIPTION_LENGTH = 120
MAX_CAPABILITY_SEARCH_TERMS = 12

DEFAULT_TOOL_TIMEOUT_MS = 30_000
DEFAULT_BASH_TIMEOUT_MS = 60_000

RISK_SAFE = "safe"
RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"

PERMISSION_READ = "read"
PERMISSION_WRITE = "write"
PERMISSION_DELETE = "delete"
PERMISSION_COMMAND = "command"
PERMISSION_NETWORK = "network"
PERMISSION_MCP = "mcp"
PERMISSION_CREWMATE = "crewmate"

CONCURRENCY_GROUP_READONLY = "read_only"
CONCURRENCY_GROUP_WORKSPACE_MUTATION = "workspace_mutation"
CONCURRENCY_GROUP_SHELL = "shell"
CONCURRENCY_GROUP_LSP = "lsp"
CONCURRENCY_GROUP_MCP = "mcp"
CONCURRENCY_GROUP_CREWMATE = "crewmate"

COST_CLASS_LOW = "low"
COST_CLASS_MEDIUM = "medium"
COST_CLASS_HIGH = "high"
LATENCY_CLASS_LOW = "low"
LATENCY_CLASS_MEDIUM = "medium"
LATENCY_CLASS_HIGH = "high"

TOOL_DOMAIN_WORKSPACE_DISCOVERY = "workspace_discovery"
TOOL_DOMAIN_READ = "read"
TOOL_DOMAIN_EDIT = "edit"
TOOL_DOMAIN_EXECUTION = "execution"
TOOL_DOMAIN_VCS = "vcs"
TOOL_DOMAIN_WEB_MCP = "web_mcp"
TOOL_DOMAIN_TASK = "task"
TOOL_DOMAIN_CREWMATE = "crewmate"
TOOL_DOMAIN_DISCOVERY = "discovery"

CAPABILITY_TOOL_DISCOVERY = "tool_discovery"
DISCOVER_CAPABILITIES_TOOL = "discover_capabilities"
GET_TOOL_DEFINITION_TOOL = "get_tool_definition"
MAX_ACTIVE_TOOLS_PER_TURN = 12

DEFAULT_TOKENIZER_MODEL = "cl100k_base"

DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; Zenith-Agent/1.0; +https://example.invalid/zenith)"

WEBFETCH_TIMEOUT_ENV = "ZENITH_WEBFETCH_TIMEOUT"
WEBFETCH_MAX_BYTES_ENV = "ZENITH_WEBFETCH_MAX_BYTES"
WEBSEARCH_TIMEOUT_ENV = "ZENITH_WEBSEARCH_TIMEOUT"
DEFAULT_WEB_TIMEOUT = 30
DEFAULT_WEBFETCH_MAX_BYTES = 40_000

VALIDATION_TIMEOUT_ENV = "ZENITH_VALIDATION_TIMEOUT"
DEFAULT_VALIDATION_TIMEOUT = 30
SUMMARIZER_TIMEOUT_ENV = "ZENITH_SUMMARIZER_TIMEOUT"
DEFAULT_SUMMARIZER_TIMEOUT = 30.0

LLM_MAX_TOKENS_ENV = "ZENITH_MAX_TOKENS"
LLM_TEMPERATURE_ENV = "ZENITH_TEMPERATURE"
DEFAULT_LLM_MAX_TOKENS = 4096
DEFAULT_LLM_TEMPERATURE = 0.7


LSP_INIT_POLL_INTERVAL = 0.5
LSP_REQUEST_TIMEOUT = 10.0
MCP_SHUTDOWN_TIMEOUT = 5.0

FILE_WRITE_TOOL = "file_write"
FILE_EDIT_TOOL = "file_edit"
FILE_DELETE_TOOL = "file_delete"
FILE_READ_TOOL = "file_read"
BASH_TOOL = "bash"
TERMINAL_TOOL = "terminal"

FILE_OVERWRITE_PARAM = "overwrite"
BASH_WORKDIR_PARAM = "workdir"

BASH_FALSE_SUCCESS_PATTERNS = ("Unable to initialize device PRN",)

POLL_TOOLS = ("job_output",)

AUTO_LINT_FIX_ENABLED = True

BASH_TOOL_DESCRIPTION_WINDOWS = (
    "Run a PowerShell command in the workspace (PowerShell syntax only; never Unix "
    "commands like ls -la, grep, mkdir -p). Prefer glob/grep/list_dir for file "
    "discovery: faster and ignore-safe. Unbounded recursive listings (Get-ChildItem "
    "-Recurse without -First N, tree, ls -R, find .) are refused; scope and limit "
    "them. To act in a subfolder, start with 'Set-Location <folder>;'."
)
BASH_TOOL_DESCRIPTION_UNIX = (
    "Run a shell command in the workspace (POSIX/bash syntax only: mkdir -p, ls, "
    "grep, rm; never PowerShell cmdlets). Prefer glob/grep/list_dir for file "
    "discovery: faster and ignore-safe. Unbounded recursive listings (ls -R, tree, "
    "find . without -maxdepth) are refused; scope and limit them. To act in a "
    "subfolder, start with 'cd <folder> &&'."
)

BASH_TOOL_COMMAND_PARAM_WINDOWS = "PowerShell command to execute (Windows PowerShell syntax only)"
BASH_TOOL_COMMAND_PARAM_UNIX = "Shell command to execute (POSIX/bash syntax only)"

FILE_EXISTS_ERROR_MARKER = "already exists"
FILE_ALREADY_EXISTS_ERROR = (
    "File already exists: {path}. Use {overwrite_param}: true to replace it."
)

MAX_TOOL_OUTPUT_BASELINE = optional_int("ZENITH_MAX_TOOL_OUTPUT", 10_000)
MAX_TOOL_METADATA_PREVIEW_CHARS = 200
MAX_TOOL_OUTPUT_TIERS = (
    (1_000_000, 50_000),
    (LARGE_CONTEXT_WINDOW, 25_000),
    (DEFAULT_CONTEXT_WINDOW, 15_000),
)

ATTACHMENT_MAX_FILE = 512 * 1024
ATTACHMENT_MAX_TOTAL = 2 * 1024 * 1024

# Workspace skipping has a single source of truth: the .zenithignore file at
# the workspace root (gitignore syntax, see server/workspace/ignore.py).
# The template below seeds newly created ignore files and doubles as the
# in-memory fallback when the file is missing and cannot be created.
ZENITH_IGNORE_FILE_NAME = ".zenithignore"

DEFAULT_ZENITH_IGNORE_CONTENT = """\
# .zenithignore — paths Zenith treats as nonexistent (never scanned or altered).
# Syntax mirrors .gitignore: one pattern per line, '#' comments,
# trailing '/' pins a directory, '*' wildcards are allowed, '!' negates.
.git/
.svn/
.hg/
node_modules/
__pycache__/
.pytest_cache/
.mypy_cache/
.mypy/
.ruff_cache/
.tox/
.cache/
htmlcov/
.nyc_output/
coverage/
.venv/
venv/
dist/
build/
.next/
.turbo/
.gemini/
.idea/
.vscode/
.zenith/
.agents/
.freebuff/
ref_repo/
reference_repo/
data/
.env
.env.*
*.log
package-lock.json
pnpm-lock.yaml
yarn.lock
poetry.lock
Cargo.lock
"""
GLOB_MAX_RESULTS = 100
GLOB_MAX_OUTPUT_CHARS = 10_000
GREP_MAX_RESULTS = 100
GREP_MAX_OUTPUT_CHARS = 10_000
GREP_MAX_FILES = 200
BROAD_PATTERN_THRESHOLD = 50
EPHEMERAL_TOOL_WINDOW_SIZE = 2
TOOL_DIGEST_MAX_CHARS = 300
DEFAULT_FILE_READ_LINES = 250
MAX_FILE_CHARS = 8000
MAX_FILE_READ_LINES = 1000
TOOL_MAX_OUTPUT_CHARS = 15_000
MAX_SKILLS_IN_PROMPT = 20
SKILL_ROOTS = ("skills", "agents/skills", ".zenith/skills", ".agent/skills")
FUZZY_THRESHOLD = 0.85
# Output-size layering (each layer is independently capped and labeled):
#   TOOL_MAX_OUTPUT_CHARS / MAX_TOOL_OUTPUT_TIERS — what the MODEL sees.
#   GLOB/GREP_MAX_OUTPUT_CHARS                    — per-tool internal caps.
#   MAX_EVENT_OUTPUT                              — what the UI wire event
#     carries (a preview; tool_result events carry a ``truncated`` flag).
MAX_EVENT_OUTPUT = 5000

# System-prompt budget allocation (chars, approximated at CHARS_PER_TOKEN).
# These bound dynamic sections so total context stays under control.
SKILLS_BUDGET_RATIO = 0.05
SKILLS_MAX_CHARS = 12_000

ANSI_RE = re.compile(
    r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*(?:\x07|\x1b\\)|\x1b[PXQ^_][^\x1b]*\x1b\\|\x1b[()][A-Za-z0-9]"
)
URL_SCHEME_RE = re.compile(r"^https?://", re.IGNORECASE)


LOOP_DETECTION_WINDOW_SIZE = 10
LOOP_DETECTION_MAX_REPEATS = 2
LOOP_IDENTICAL_CONSECUTIVE_LIMIT = 3

MIN_REQUEST_INTERVAL_ENV = "ZENITH_MIN_REQUEST_INTERVAL"
DEFAULT_MIN_REQUEST_INTERVAL = 0.0
REQUEST_THROTTLE_JITTER = 0.5


def default_max_tokens_for_context(context_window: int) -> int:
    return max(DEFAULT_LLM_MAX_TOKENS, min(context_window // 2, MAX_OUTPUT_TOKENS_CLAMP))
