"""Typed configuration model for Zenith.

Precedence model (highest wins):
  1. CLI / caller-supplied overrides — ``AppSettings(**overrides)`` or ``model_copy(update=...)``.
  2. environment variables          — ``ZENITH_*`` scalars (read at import time via ``env.py``).
  3. storage file                   — provider catalog + user profile (loaded by ``loader.load_config``).
  4. code defaults                  — ``BootstrapDefaults`` / ``DEFAULTS`` / field defaults.

``load_config()`` handles (3)+(2)+(4) together; callers add (1) via constructor
overrides.  See ``loader.py`` for the merge implementation.
"""

from dataclasses import dataclass

from pydantic import BaseModel, Field, field_validator

from .constants import (
    BUILD_MODE,
    DEFAULT_CONTEXT_WINDOW,
    DEFAULT_EXPLORE_DELEGATION,
    DEFAULT_EXPLORE_TOKEN_BUDGET,
    EXPLORE_DELEGATION_MODES,
    EXPLORE_TOKEN_BUDGET_ENV,
    PLAN_MODE,
    READ_ONLY_MODE,
    READ_ONLY_TOOLS,
)
from .env import optional_bool, optional_env, optional_float, optional_int
from .providers import ProviderConfig


def default_home() -> str:
    from pathlib import Path

    return str(Path.home() / ".zenith")


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
    description: str = ""
    model_override: str | None = None
    tool_choice: str = "auto"
    crewmate: bool = False


PLAN_MODE_CONFIG = AgentModeConfig(
    name=PLAN_MODE,
    allowed_tools=CORE_PLAN_TOOLS,
    description="Read-only analysis and planning with core tools and dynamic escalation.",
)
# Always-offered schemas. Web research tools stay registered and are promoted on
# demand (get_tool_definition or a direct call auto-escalates), so a pure code
# task never pays for their (large) schemas on every turn.
CORE_BUILD_TOOLS = ["file_read", "file_edit", "file_write", "bash", "glob", "grep"]
BUILD_MODE_CONFIG = AgentModeConfig(
    name=BUILD_MODE,
    allowed_tools=CORE_BUILD_TOOLS,
    description="Full execution with core tools and dynamic schema escalation.",
    tool_choice="auto",
    crewmate=True,
)
READ_ONLY_MODE_CONFIG = AgentModeConfig(
    name=READ_ONLY_MODE,
    allowed_tools=READ_ONLY_TOOLS,
    description="Pure read-only investigation: no file-mutation tools attached.",
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


class HooksConfig(BaseModel):
    pre_tool_use: list[str] = Field(default_factory=list)
    post_tool_use: list[str] = Field(default_factory=list)
    session_start: list[str] = Field(default_factory=list)
    timeout: int = Field(default=30, ge=1, le=300)


class BootstrapDefaults(BaseModel):
    active_provider: str = ""
    home_dir: str = Field(default_factory=lambda: optional_env("ZENITH_HOME", str(default_home())))
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
    async_summary_enabled: bool = Field(
        default_factory=lambda: optional_bool("ZENITH_ASYNC_SUMMARY_ENABLED", False)
    )
    tools: ToolConfig = Field(default_factory=ToolConfig)


DEFAULTS = BootstrapDefaults()


class AppSettings(BaseModel):
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    active_provider: str = DEFAULTS.active_provider
    workspace_root: str = "."
    home_dir: str = DEFAULTS.home_dir
    log_level: str = DEFAULTS.log_level
    tools: ToolConfig = Field(default_factory=ToolConfig)
    max_context_tokens: int = DEFAULTS.max_context_tokens
    summary_threshold: float = DEFAULTS.summary_threshold
    context_compaction_threshold: float = DEFAULTS.context_compaction_threshold
    async_summary_enabled: bool = DEFAULTS.async_summary_enabled
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
    repo_map_enabled: bool = Field(
        default=True,
        description="Whether repository map generation is enabled for context",
    )
    repo_map_tokens: int | None = Field(
        default=None,
        description="Explicit token budget for repo map; if None, scales automatically with context window",
    )
    plan_model: str | None = Field(
        default=None, description="Optional separate model for plan mode (e.g. 'gpt-4o-mini')"
    )
    weak_model: str | None = Field(
        default=None,
        description="Optional cheap model for summaries, commit messages (two-tier strategy)",
    )
    explore_delegation: str = Field(
        default=DEFAULT_EXPLORE_DELEGATION,
        description=(
            "Explore delegation governance: 'off' (no explore tool, no pre-loop "
            "routing), 'tool' (ONLY the mid-turn explore tool delegates — the "
            "recommended default), 'proactive' (explore tool PLUS legacy pre-loop "
            "capability routing)."
        ),
    )
    explore_token_budget: int = Field(
        default=optional_int(EXPLORE_TOKEN_BUDGET_ENV, DEFAULT_EXPLORE_TOKEN_BUDGET),
        ge=1_000,
        description="Aggregate token ceiling across explore children per rolling window",
    )
    allowed_ws_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost", "https://localhost", "http://127.0.0.1", "https://127.0.0.1"],
        description="Allowed WebSocket Origin values. Scheme, host, and optional port are matched exactly.",
    )
    allow_empty_ws_origin: bool = Field(
        default=True,
        description="Allow WebSocket clients that do not send an Origin header, such as the local TUI.",
    )
    hooks: HooksConfig = Field(
        default_factory=HooksConfig,
        description="Lifecycle hooks (PreToolUse/PostToolUse/SessionStart). Loaded from ZENITH_HOOKS (JSON).",
    )

    @field_validator("active_provider")
    @classmethod
    def validate_active_provider(cls, v: str) -> str:
        return (v or "").strip()

    @field_validator("explore_delegation")
    @classmethod
    def validate_explore_delegation(cls, v: str) -> str:
        mode = (v or "").strip().lower()
        if mode not in EXPLORE_DELEGATION_MODES:
            raise ValueError(
                f"explore_delegation must be one of {', '.join(EXPLORE_DELEGATION_MODES)}"
            )
        return mode

    def get_active_provider_config(self) -> ProviderConfig | None:
        return self.providers.get(self.active_provider)

    def require_active_provider_config(self) -> ProviderConfig:
        config = self.get_active_provider_config()
        if config is None:
            raise ValueError(
                f"Provider '{self.active_provider}' is not configured. Available: {list(self.providers.keys()) or 'none'}. Configure and activate a provider via the setup wizard."
            )
        return config
