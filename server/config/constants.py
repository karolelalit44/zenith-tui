DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
HOST_ENV_VAR = "ZENITH_HOST"
PORT_ENV_VAR = "ZENITH_PORT"
WS_PATH = "/ws"
HEALTH_PATH = "/health"
DEFAULT_BASH_TIMEOUT = 120
CONTEXT_SUMMARY_THRESHOLD = 0.85
DEFAULT_CONTEXT_WINDOW = 128000
BUILD_MODE = "build"
PLAN_MODE = "plan"

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
PERMISSION_INTERACTION = "interaction"

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

# Tool names (registry keys)
FILE_WRITE_TOOL = "file_write"
FILE_EDIT_TOOL = "file_edit"
FILE_DELETE_TOOL = "file_delete"
FILE_READ_TOOL = "file_read"
BASH_TOOL = "bash"
TERMINAL_TOOL = "terminal"

# Tool parameter keys
FILE_OVERWRITE_PARAM = "overwrite"

# Bash tool descriptions (OS-specific commands only)
BASH_TOOL_DESCRIPTION_WINDOWS = (
    "Execute a Windows PowerShell command in the workspace. Only use PowerShell commands "
    "and PowerShell syntax (e.g. New-Item, Get-ChildItem, Get-Content, Set-Content, "
    "Remove-Item, Select-String, Start-Process). Do NOT use Unix shell commands "
    "(mkdir -p, ls, grep, touch, rm) or bash syntax."
)
BASH_TOOL_DESCRIPTION_UNIX = (
    "Execute a shell command in the workspace. Only use Unix/Linux shell commands and bash "
    "syntax (e.g. mkdir -p, ls, grep, touch, rm, cat). Do NOT use Windows PowerShell cmdlets."
)

# Bash tool command parameter descriptions (OS-specific)
BASH_TOOL_COMMAND_PARAM_WINDOWS = (
    "PowerShell command to execute (Windows PowerShell syntax only)"
)
BASH_TOOL_COMMAND_PARAM_UNIX = (
    "Shell command to execute (POSIX/bash syntax only)"
)

# Tool error markers
FILE_EXISTS_ERROR_MARKER = "already exists"
FILE_ALREADY_EXISTS_ERROR = (
    "File already exists: {path}. Use {overwrite_param}: true to replace it."
)

# Tool output formatting
MAX_TOOL_OUTPUT_BASELINE = 10_000
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
