from .env import optional_int

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
HOST_ENV_VAR = "ZENITH_HOST"
PORT_ENV_VAR = "ZENITH_PORT"
WS_PATH = "/ws"
HEALTH_PATH = "/health"

# Static test simulation backend: a second WebSocket endpoint (/ws/test) that
# plays back scripted responses from data/simulation/*.json. No DB, no provider.
TEST_WS_PATH = "/ws/test"
TEST_SIMULATION_DIR = "data/simulation"
TEST_SIMULATION_DIR_ENV = "ZENITH_SIMULATION_DIR"
CONTEXT_SUMMARY_THRESHOLD = 0.85
DEFAULT_CONTEXT_WINDOW = 128000
BUILD_MODE = "build"
PLAN_MODE = "plan"

# Compaction simulation defaults (used by the /ws/test endpoint and the TUI
# simulation backend). These keep the dynamic compaction UI grounded in
# realistic, non-fabricated numbers: the test route emits a lifecycle whose
# `used`/`total`/`tokensSaved` are derived from these values.
COMPACTION_SIM_TOTAL_TOKENS = 128_000
COMPACTION_SIM_USED_TOKENS = 118_000  # ~92% — triggers automatic compaction
COMPACTION_SIM_AFTER_TOKENS = 43_000
COMPACTION_SIM_SUMMARY_CHARS = 12_000

# On-demand tool-guidelines reference file. Written to the workspace root on
# first prompt build; the system prompt points the model at it so detailed tool
# guidance is read lazily instead of being re-sent on every call.
TOOL_GUIDELINES_DIR = ".zenith"
TOOL_GUIDELINES_FILE_NAME = "tool-guidelines.md"

# Tool metadata bounds
MAX_TOOL_NAME_LENGTH = 64
MAX_TOOL_DESCRIPTION_LENGTH = 400
MAX_CAPABILITY_DESCRIPTION_LENGTH = 120
MAX_CAPABILITY_SEARCH_TERMS = 12

# Default tool timeouts (milliseconds)
DEFAULT_TOOL_TIMEOUT_MS = 30_000
DEFAULT_BASH_TIMEOUT_MS = 60_000

# Tool risk levels
RISK_SAFE = "safe"
RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"

# Tool permission scopes
PERMISSION_READ = "read"
PERMISSION_WRITE = "write"
PERMISSION_DELETE = "delete"
PERMISSION_COMMAND = "command"
PERMISSION_NETWORK = "network"
PERMISSION_MCP = "mcp"
PERMISSION_SUBAGENT = "sub_agent"

# Tool concurrency groups
CONCURRENCY_GROUP_READONLY = "read_only"
CONCURRENCY_GROUP_WORKSPACE_MUTATION = "workspace_mutation"
CONCURRENCY_GROUP_SHELL = "shell"
CONCURRENCY_GROUP_LSP = "lsp"
CONCURRENCY_GROUP_MCP = "mcp"
CONCURRENCY_GROUP_SUBAGENT = "sub_agent"

# Tool cost/latency classes
COST_CLASS_LOW = "low"
COST_CLASS_MEDIUM = "medium"
COST_CLASS_HIGH = "high"
LATENCY_CLASS_LOW = "low"
LATENCY_CLASS_MEDIUM = "medium"
LATENCY_CLASS_HIGH = "high"

# Tool capability domains
TOOL_DOMAIN_WORKSPACE_DISCOVERY = "workspace_discovery"
TOOL_DOMAIN_READ = "read"
TOOL_DOMAIN_EDIT = "edit"
TOOL_DOMAIN_EXECUTION = "execution"
TOOL_DOMAIN_VCS = "vcs"
TOOL_DOMAIN_WEB_MCP = "web_mcp"
TOOL_DOMAIN_TASK = "task"
TOOL_DOMAIN_SUBAGENT = "sub_agent"
TOOL_DOMAIN_DISCOVERY = "discovery"

# Tool discovery (on-demand / lazy schema loading)
CAPABILITY_TOOL_DISCOVERY = "tool_discovery"
DISCOVER_CAPABILITIES_TOOL = "discover_capabilities"
GET_TOOL_DEFINITION_TOOL = "get_tool_definition"
# Leaves room for on-demand escalations beyond the mode seed. The build seed
# alone is 6 core tools + 2 discovery; a cap of 8 gave it zero headroom, so the
# first escalation evicted a core tool (e.g. file_read) from the active set.
MAX_ACTIVE_TOOLS_PER_TURN = 12

# Schema-token benchmark
DEFAULT_TOKENIZER_MODEL = "cl100k_base"

# Shared HTTP user agent for web tools
DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; Zenith-Agent/1.0; +https://example.invalid/zenith)"

# Web tool timeouts/limits (env-driven, defaults here)
WEBFETCH_TIMEOUT_ENV = "ZENITH_WEBFETCH_TIMEOUT"
WEBFETCH_MAX_BYTES_ENV = "ZENITH_WEBFETCH_MAX_BYTES"
WEBSEARCH_TIMEOUT_ENV = "ZENITH_WEBSEARCH_TIMEOUT"
DEFAULT_WEB_TIMEOUT = 30
DEFAULT_WEBFETCH_MAX_BYTES = 40_000

# Provider validation / summarizer timeouts (env-driven)
VALIDATION_TIMEOUT_ENV = "ZENITH_VALIDATION_TIMEOUT"
DEFAULT_VALIDATION_TIMEOUT = 30
SUMMARIZER_TIMEOUT_ENV = "ZENITH_SUMMARIZER_TIMEOUT"
DEFAULT_SUMMARIZER_TIMEOUT = 30.0

# Fallback LLM defaults when a provider has no catalog entry (env-driven)
LLM_MAX_TOKENS_ENV = "ZENITH_MAX_TOKENS"
LLM_TEMPERATURE_ENV = "ZENITH_TEMPERATURE"
DEFAULT_LLM_MAX_TOKENS = 4096
DEFAULT_LLM_TEMPERATURE = 0.7

# SQLite pragmas
SQLITE_BUSY_TIMEOUT_MS = 30_000

# LSP / MCP protocol timings (intrinsic)
LSP_INIT_POLL_INTERVAL = 0.5
LSP_REQUEST_TIMEOUT = 10.0
MCP_SHUTDOWN_TIMEOUT = 5.0

# Tool names (registry keys)
FILE_WRITE_TOOL = "file_write"
FILE_EDIT_TOOL = "file_edit"
FILE_DELETE_TOOL = "file_delete"
FILE_READ_TOOL = "file_read"
BASH_TOOL = "bash"
TERMINAL_TOOL = "terminal"

# Tool parameter keys
FILE_OVERWRITE_PARAM = "overwrite"
# Internal bash parameter injected by the prechecks: the resolved working
# directory extracted from a leading `cd <dir>;` / `Set-Location <dir>;` prefix,
# so the subprocess runs inside the folder the model asked for instead of having
# the intent silently dropped.
BASH_WORKDIR_PARAM = "workdir"

# Bash false-success signatures: a shell command that exits 0 but whose output
# proves it did not actually run (e.g. the Windows Store `python` alias prints
# "Unable to initialize device PRN" and does nothing). A match upgrades the tool
# result to a failure so the agent is told the command did not execute.
BASH_FALSE_SUCCESS_PATTERNS = ("Unable to initialize device PRN",)

# Read-only tools that may legitimately be re-invoked with identical parameters.
# They are exempt from the identical-param skip guard so polling loops (e.g.
# checking a background job's output more than once) keep working.
POLL_TOOLS = ("job_output",)

# Auto-fix lint issues found after file writes (ruff/eslint --fix). When a fix
# is applied the post-write lint hook re-reports only the issues that remain.
AUTO_LINT_FIX_ENABLED = True

# Bash tool descriptions (OS-specific commands only)
BASH_TOOL_DESCRIPTION_WINDOWS = (
    "Execute a PowerShell command in the workspace (Windows PowerShell syntax only, "
    "e.g. New-Item, Get-ChildItem, Get-Content, Set-Content, Remove-Item, Select-String). "
    "Never use Unix shell commands (mkdir -p, ls, grep, touch, rm). To act inside a "
    "subfolder, start with 'Set-Location <folder>;'."
)
BASH_TOOL_DESCRIPTION_UNIX = (
    "Execute a shell command in the workspace. Use Unix/Linux shell commands and bash "
    "syntax only (mkdir -p, ls, grep, touch, rm, cat). Never use Windows PowerShell "
    "cmdlets. To act inside a subfolder, start the command with 'cd <folder> &&'."
)

# Bash tool command parameter descriptions (OS-specific)
BASH_TOOL_COMMAND_PARAM_WINDOWS = "PowerShell command to execute (Windows PowerShell syntax only)"
BASH_TOOL_COMMAND_PARAM_UNIX = "Shell command to execute (POSIX/bash syntax only)"

# Tool error markers
FILE_EXISTS_ERROR_MARKER = "already exists"
FILE_ALREADY_EXISTS_ERROR = (
    "File already exists: {path}. Use {overwrite_param}: true to replace it."
)

# Tool output formatting
MAX_TOOL_OUTPUT_BASELINE = optional_int("ZENITH_MAX_TOOL_OUTPUT", 10_000)
MAX_TOOL_METADATA_PREVIEW_CHARS = 200
# Ordered high-to-low (context window tier, max tool output in chars).
MAX_TOOL_OUTPUT_TIERS = (
    (1_000_000, 50_000),
    (200_000, 25_000),
    (DEFAULT_CONTEXT_WINDOW, 15_000),
)

# Agent loop detection
LOOP_DETECTION_WINDOW_SIZE = 10
LOOP_DETECTION_MAX_REPEATS = 2
LOOP_IDENTICAL_CONSECUTIVE_LIMIT = 3

# Rate limiting / quota handling
# Client-side request pacing: provider failures are surfaced explicitly (no
# silent retries), so pacing is the only client-side mitigation. The env var is
# the global default; the provider catalog may override it per provider via
# `rate_limit`.
MIN_REQUEST_INTERVAL_ENV = "ZENITH_MIN_REQUEST_INTERVAL"
DEFAULT_MIN_REQUEST_INTERVAL = 0.0  # disabled unless configured
REQUEST_THROTTLE_JITTER = 0.5
