"""Tool registry, toolkit, and crewmate-tool metadata constants.

Owns tool names, permission/risk/cost/concurrency/domain metadata, discovery
caps, output-size limits, special error markers, glob/grep/ignore limits,
attachments, and the structural-retrieval crewmate tool knobs.
Depends on ``context.py`` for the context-window sizes used by the output-tier
table, and on ``env.py``.
"""

from ..env import optional_int
from .context import DEFAULT_CONTEXT_WINDOW, LARGE_CONTEXT_WINDOW

MAX_TOOL_NAME_LENGTH = 64
MAX_TOOL_DESCRIPTION_LENGTH = 400

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
PERMISSION_CREWMATE = "crewmate"

CONCURRENCY_GROUP_READONLY = "read_only"
CONCURRENCY_GROUP_WORKSPACE_MUTATION = "workspace_mutation"
CONCURRENCY_GROUP_SHELL = "shell"
CONCURRENCY_GROUP_CREWMATE = "crewmate"

COST_CLASS_LOW = "low"
COST_CLASS_MEDIUM = "medium"
COST_CLASS_HIGH = "high"
LATENCY_CLASS_LOW = "low"
LATENCY_CLASS_HIGH = "high"

TOOL_DOMAIN_WORKSPACE_DISCOVERY = "workspace_discovery"
TOOL_DOMAIN_READ = "read"
TOOL_DOMAIN_EDIT = "edit"
TOOL_DOMAIN_EXECUTION = "execution"
TOOL_DOMAIN_WEB = "web"
TOOL_DOMAIN_TASK = "task"
TOOL_DOMAIN_CREWMATE = "crewmate"
TOOL_DOMAIN_DISCOVERY = "discovery"

CAPABILITY_TOOL_DISCOVERY = "tool_discovery"
DISCOVER_CAPABILITIES_TOOL = "discover_capabilities"
GET_TOOL_DEFINITION_TOOL = "get_tool_definition"
MAX_ACTIVE_TOOLS_PER_TURN = 12

FILE_WRITE_TOOL = "file_write"
FILE_EDIT_TOOL = "file_edit"
FILE_DELETE_TOOL = "file_delete"
FILE_READ_TOOL = "file_read"
BASH_TOOL = "bash"
TERMINAL_TOOL = "terminal"

FILE_OVERWRITE_PARAM = "overwrite"
BASH_WORKDIR_PARAM = "workdir"

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
BROAD_PATTERN_THRESHOLD = 50
TOOL_DIGEST_MAX_CHARS = 300
DEFAULT_FILE_READ_LINES = 250
MAX_FILE_READ_LINES = 1000
TOOL_MAX_OUTPUT_CHARS = 15_000

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
DEFAULT_EXPLORE_DELEGATION = EXPLORE_DELEGATION_TOOL
# Rendered report cap entering parent context (S2: <= ~2 KB).
EXPLORE_RESULT_MAX_CHARS = 2_000
# Custom crewmate runtime definitions (bounded free-text).
EXPLORE_CUSTOM_NAME_MAX_CHARS = 32
EXPLORE_CUSTOM_ROLE_MAX_CHARS = 48
EXPLORE_CUSTOM_FOCUS_MAX_CHARS = 600

# Mission brief injected into the crewmate prompt at spawn (CrewmateStart pattern).
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
