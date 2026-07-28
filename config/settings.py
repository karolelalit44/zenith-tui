from dataclasses import dataclass
from typing import Optional
from pydantic import BaseModel, Field, field_validator
from .providers import ProviderConfig
from .env import optional_env, optional_int, optional_float


# ---------------------------------------------------------------------------
# Agent mode configurations (inspired by Crush's Agent struct + Aider's
# architect/editor separation)
# ---------------------------------------------------------------------------

# Read-only tools for plan mode — comprehensive set matching the device.
# These tools NEVER modify the filesystem or system state.
PLAN_READ_ONLY_TOOLS = [
    "file_read",       # Read file contents
    "glob",            # Find files by pattern
    "grep",            # Search file contents
]

@dataclass(frozen=True)
class AgentModeConfig:
    """Configuration for an agent mode (plan or build).

    Inspired by Crush's Agent{Model, AllowedTools, AllowedMCP} and
    Aider's architect/editor separation.

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
    description: str = ""

PLAN_MODE_CONFIG = AgentModeConfig(
    name="plan",
    allowed_tools=PLAN_READ_ONLY_TOOLS,
    description="Read-only analysis and planning. No file modifications.",
)

BUILD_MODE_CONFIG = AgentModeConfig(
    name="build",
    allowed_tools=None,  # All tools
    description="Full execution with all tools.",
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
        default=optional_float("ZENITH_RETRY_BASE_DELAY", 0.5), ge=0.1, le=30.0
    )
    retry_max_delay: float = Field(
        default=optional_float("ZENITH_RETRY_MAX_DELAY", 10.0), ge=1.0, le=300.0
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

    def get_active_provider_config(self) -> Optional[ProviderConfig]:
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
