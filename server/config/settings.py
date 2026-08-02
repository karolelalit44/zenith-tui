from dataclasses import dataclass

from pydantic import BaseModel, Field, field_validator

from .env import optional_env, optional_float, optional_int
from .providers import ProviderConfig

# ---------------------------------------------------------------------------
# Agent mode configurations (inspired by Crush's Agent struct + Aider's
# architect/editor separation)
# ---------------------------------------------------------------------------

# Read-only tools for plan mode — comprehensive set matching the device.
# These tools NEVER modify the filesystem or system state.
PLAN_READ_ONLY_TOOLS = [
    "file_read",           # Read file contents
    "glob",                # Find files by pattern
    "grep",                # Search file contents
    "lsp_definition",      # Go-to-definition (language-aware)
    "lsp_diagnostics",     # Lint/typecheck (read-only analysis)
    "lsp_symbols",         # List symbols in file/project
    "lsp_call_hierarchy",  # Show callers/callees
    "lsp_references",      # Find all references
    "sourcegraph",         # Semantic code search
    "webfetch",            # Fetch URLs (read-only)
    "question",            # Ask user questions (read-only checkpoint)
]

@dataclass(frozen=True)
class AgentModeConfig:
    """Configuration for an agent mode (plan or build).

    Inspired by Crush's Agent{Model, AllowedTools, AllowedMCP} and
    Aider's architect/editor separation.

    allowed_tools:  Tool names allowed in this mode. None = all tools.
    allowed_mcp:    MCP access per mode:
                    - None = all MCPs allowed (build mode).
                    - {}   = no MCPs allowed (plan mode).
                    - {"server": ["tool"]} = specific MCP tools.
    model_override: Optional model name for this mode (e.g. "gpt-4o-mini"
                    for planning). None = use session default.
    sub_agent:      If True, spawn a fresh agent instance for this mode
                    (Aider-style architect→editor sub-agent). The mode's
                    output (plan) becomes the sub-agent's input message.

    auto_approve_plan: If True, skip user confirmation when transitioning
      from plan output to build execution.

    Stopping is dynamic — controlled by:
      1. Loop detection (Crush-style SHA-256 signature matching)
      2. Context window exhaustion (auto-summarize when >85% full)
      3. Tool-level stop_turn (tools can end the turn)
      4. Task completion signals

    max_iterations is ONLY a safety net (default 100). Do NOT rely on it
    for normal operation — the agent should stop via the above mechanisms.
    """
    name: str
    allowed_tools: list[str] | None = None  # None = all tools
    allowed_mcp: dict[str, list[str]] | None = None  # None=all, {}=none
    description: str = ""
    model_override: str | None = None
    sub_agent: bool = False
    tool_choice: str = "auto"  # "auto", "required", "none", or specific function name

PLAN_MODE_CONFIG = AgentModeConfig(
    name="plan",
    allowed_tools=PLAN_READ_ONLY_TOOLS,
    allowed_mcp={},  # No MCPs in plan mode
    description="Read-only analysis and planning. No file modifications.",
    sub_agent=False,
)

BUILD_MODE_CONFIG = AgentModeConfig(
    name="build",
    allowed_tools=None,  # All tools
    allowed_mcp=None,  # All MCPs
    description="Full execution with all tools.",
    sub_agent=True,  # Spawn fresh sub-agent on plan→build transition
    tool_choice="required",  # Force tool calling in build mode
)

AGENT_MODES: dict[str, AgentModeConfig] = {
    "plan": PLAN_MODE_CONFIG,
    "build": BUILD_MODE_CONFIG,
}


class ToolConfig(BaseModel):
    bash_enabled: bool = True
    file_write_enabled: bool = True
    file_edit_enabled: bool = True
    file_delete_enabled: bool = True
    max_bash_timeout: int = Field(
        default=optional_int("ZENITH_BASH_TIMEOUT", 30), ge=1, le=300
    )
    max_tool_output: int = Field(
        default=optional_int("ZENITH_MAX_TOOL_OUTPUT", 10000), ge=1000
    )
    max_retries: int = Field(
        default=optional_int("ZENITH_MAX_RETRIES", 3), ge=0, le=10
    )
    stream_max_retries: int = Field(
        default=optional_int("ZENITH_STREAM_MAX_RETRIES", 3), ge=0, le=10
    )
    retry_base_delay: float = Field(
        default=optional_float("ZENITH_RETRY_BASE_DELAY", 0.125), ge=0.1, le=30.0
    )
    retry_max_delay: float = Field(
        default=optional_float("ZENITH_RETRY_MAX_DELAY", 60.0), ge=1.0, le=300.0
    )
    webfetch_timeout: int = Field(
        default=optional_int("ZENITH_WEBFETCH_TIMEOUT", 30), ge=5, le=120
    )
    webfetch_max_bytes: int = Field(
        default=optional_int("ZENITH_WEBFETCH_MAX_BYTES", 100000), ge=1000, le=1000000
    )
    git_timeout: int = Field(
        default=optional_int("ZENITH_GIT_TIMEOUT", 30), ge=5, le=120
    )


class McpServerConfig(BaseModel):
    """Configuration for a single MCP (Model Context Protocol) server.

    command:  Executable to spawn (e.g. "npx").
    args:     Arguments passed to the executable.
    env:      Optional extra environment variables for the subprocess.
    """
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


class HooksConfig(BaseModel):
    """Config-driven lifecycle hooks (HP-10).

    Each entry is a shell command run as a subprocess in the workspace root.
    Template fields ({tool_name}, {session_id}, {params}, ...) are substituted
    and the full JSON payload is written to the command's stdin.

    pre_tool_use:   run before a tool executes; a non-zero exit blocks the tool.
    post_tool_use:  run after a tool executes; non-zero exit is logged only.
    session_start:  run once when a session is created; non-zero exit is logged.
    timeout:        per-hook timeout in seconds.
    """
    pre_tool_use: list[str] = Field(default_factory=list)
    post_tool_use: list[str] = Field(default_factory=list)
    session_start: list[str] = Field(default_factory=list)
    timeout: int = Field(default=30, ge=1, le=300)


class BootstrapDefaults(BaseModel):
    active_provider: str = optional_env("ZENITH_ACTIVE_PROVIDER", "nvidia")
    db_path: str = optional_env("ZENITH_DB_PATH", "data/zenith.db")
    log_level: str = optional_env("ZENITH_LOG_LEVEL", "INFO")
    max_context_tokens: int = Field(
        default=optional_int("ZENITH_MAX_CONTEXT_TOKENS", 128000), ge=1000
    )
    summary_threshold: float = Field(
        default=optional_float("ZENITH_SUMMARY_THRESHOLD", 0.8), ge=0.1, le=1.0
    )
    tools: ToolConfig = Field(default_factory=ToolConfig)


DEFAULTS = BootstrapDefaults()


class AppSettings(BaseModel):
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    active_provider: str = DEFAULTS.active_provider
    workspace_root: str = "."
    db_path: str = DEFAULTS.db_path
    log_level: str = DEFAULTS.log_level
    tools: ToolConfig = Field(default_factory=ToolConfig)
    max_context_tokens: int = DEFAULTS.max_context_tokens
    summary_threshold: float = DEFAULTS.summary_threshold
    auto_approve_plan: bool = Field(
        default=False,
        description="Skip user confirmation when running a plan in build mode",
    )
    plan_model: str | None = Field(
        default=None,
        description="Optional separate model for plan mode (e.g. 'gpt-4o-mini')",
    )
    weak_model: str | None = Field(
        default=None,
        description="Optional cheap model for summaries, commit messages (two-tier strategy)",
    )
    repo_map_enabled: bool = True
    repo_map_tokens: int | None = Field(
        default=optional_int("ZENITH_REPO_MAP_TOKENS", None),
        ge=256,
        le=32000,
        description="Token budget for the repo map. None = auto (context/8, clamped to 1024-4096)",
    )
    memory_enabled: bool = True
    mcp_servers: dict[str, McpServerConfig] = Field(
        default_factory=dict,
        description="MCP servers: {name: McpServerConfig}. Loaded from ZENITH_MCP_SERVERS (JSON).",
    )
    hooks: HooksConfig = Field(
        default_factory=HooksConfig,
        description="Lifecycle hooks (PreToolUse/PostToolUse/SessionStart). Loaded from ZENITH_HOOKS (JSON).",
    )

    @field_validator("active_provider")
    @classmethod
    def validate_active_provider(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("active_provider cannot be empty")
        return v.strip()

    @field_validator("db_path")
    @classmethod
    def validate_db_path(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("db_path cannot be empty")
        return v

    def get_active_provider_config(self) -> ProviderConfig | None:
        return self.providers.get(self.active_provider)

    def require_active_provider_config(self) -> ProviderConfig:
        config = self.get_active_provider_config()
        if config is None:
            raise ValueError(
                f"Provider '{self.active_provider}' is not configured. "
                f"Available: {list(self.providers.keys()) or 'none'}. "
                f"Configure via setup wizard or set ZENITH_ACTIVE_PROVIDER env var."
            )
        return config
