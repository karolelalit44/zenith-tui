from dataclasses import dataclass

from pydantic import BaseModel, Field, field_validator

from .constants import (
    BUILD_MODE,
    DEFAULT_CONTEXT_WINDOW,
    PLAN_MODE,
    READ_ONLY_MODE,
    READ_ONLY_TOOLS,
)
from .env import optional_env, optional_float, optional_int, optional_int_none
from .providers import ProviderConfig

CORE_PLAN_TOOLS = [
    "file_read",
    "file_write",
    "file_edit",
    "glob",
    "grep",
    "websearch",
    "webfetch",
]


@dataclass(frozen=True)
class AgentModeConfig:
    name: str
    allowed_tools: list[str] | None = None
    allowed_mcp: dict[str, list[str]] | None = None
    description: str = ""
    model_override: str | None = None
    sub_agent: bool = False
    tool_choice: str = "auto"


PLAN_MODE_CONFIG = AgentModeConfig(
    name=PLAN_MODE,
    allowed_tools=CORE_PLAN_TOOLS,
    allowed_mcp={},
    description="Read-only analysis and planning with core tools and dynamic escalation.",
    sub_agent=False,
)
# Always-offered schemas. Web research tools stay registered and are promoted on
# demand (get_tool_definition or a direct call auto-escalates), so a pure code
# task never pays for their (large) schemas on every turn.
CORE_BUILD_TOOLS = ["file_read", "file_edit", "file_write", "bash", "glob", "grep"]
BUILD_MODE_CONFIG = AgentModeConfig(
    name=BUILD_MODE,
    allowed_tools=CORE_BUILD_TOOLS,
    allowed_mcp=None,
    description="Full execution with core tools and dynamic schema escalation.",
    sub_agent=True,
    tool_choice="auto",
)
READ_ONLY_MODE_CONFIG = AgentModeConfig(
    name=READ_ONLY_MODE,
    allowed_tools=READ_ONLY_TOOLS,
    allowed_mcp={},
    description="Pure read-only investigation: no file-mutation tools attached.",
    sub_agent=False,
    tool_choice="none",
)
AGENT_MODES: dict[str, AgentModeConfig] = {
    PLAN_MODE: PLAN_MODE_CONFIG,
    BUILD_MODE: BUILD_MODE_CONFIG,
    READ_ONLY_MODE: READ_ONLY_MODE_CONFIG,
}


class ToolConfig(BaseModel):
    bash_enabled: bool = True
    file_write_enabled: bool = True
    file_edit_enabled: bool = True
    file_delete_enabled: bool = True
    max_bash_timeout: int = Field(default=optional_int("ZENITH_BASH_TIMEOUT", 30), ge=1, le=300)


class McpServerConfig(BaseModel):
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


class HooksConfig(BaseModel):
    pre_tool_use: list[str] = Field(default_factory=list)
    post_tool_use: list[str] = Field(default_factory=list)
    session_start: list[str] = Field(default_factory=list)
    timeout: int = Field(default=30, ge=1, le=300)


class BootstrapDefaults(BaseModel):
    active_provider: str = ""
    db_path: str = optional_env("ZENITH_DB_PATH", "data/zenith.db")
    log_level: str = optional_env("ZENITH_LOG_LEVEL", "INFO")
    max_context_tokens: int = Field(
        default=optional_int("ZENITH_MAX_CONTEXT_TOKENS", DEFAULT_CONTEXT_WINDOW), ge=1000
    )
    summary_threshold: float = Field(
        default=optional_float("ZENITH_SUMMARY_THRESHOLD", 0.8), ge=0.1, le=1.0
    )
    # Context compaction watermark: when the composed context uses >= this ratio of the
    # window, fold the rolling window into a running summary (design §3.7 / §6.2). Wired the
    # same way as summary_threshold; load_config() also honors it at load time.
    context_compaction_threshold: float = Field(
        default=optional_float("ZENITH_CONTEXT_COMPACTION_THRESHOLD", 0.7), ge=0.0, le=1.0
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
    context_compaction_threshold: float = DEFAULTS.context_compaction_threshold
    auto_approve_plan: bool = Field(
        default=False, description="Skip user confirmation when running a plan in build mode"
    )
    auto_overwrite: bool = Field(
        default=True,
        description="Automatically allow overwriting existing files without confirmation",
    )
    auto_risky: bool = Field(
        default=True,
        description="Automatically allow risky operations (file deletion, risky commands) without confirmation",
    )
    plan_model: str | None = Field(
        default=None, description="Optional separate model for plan mode (e.g. 'gpt-4o-mini')"
    )
    weak_model: str | None = Field(
        default=None,
        description="Optional cheap model for summaries, commit messages (two-tier strategy)",
    )
    repo_map_enabled: bool = True
    repo_map_tokens: int | None = Field(
        default=optional_int_none("ZENITH_REPO_MAP_TOKENS"),
        ge=256,
        le=32000,
        description="Token budget for the repo map. None = auto (context/8, clamped to 1024-4096)",
    )
    memory_enabled: bool = True
    async_summary_enabled: bool = True
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
        return (v or "").strip()

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
                f"Provider '{self.active_provider}' is not configured. Available: {list(self.providers.keys()) or 'none'}. Configure and activate a provider via the setup wizard."
            )
        return config
