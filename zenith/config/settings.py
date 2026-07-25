from pathlib import Path
from typing import Optional
import os
from pydantic import BaseModel, Field, field_validator
from .providers import ProviderConfig
from .env import require_env, require_int, require_float


class ToolConfig(BaseModel):
    bash_enabled: bool = True
    file_write_enabled: bool = True
    file_edit_enabled: bool = True
    file_delete_enabled: bool = True
    max_bash_timeout: int = Field(
        default=require_int("ZENITH_BASH_TIMEOUT"), ge=1, le=300
    )
    max_iterations: int = Field(
        default=require_int("ZENITH_MAX_ITERATIONS"), ge=1, le=100
    )
    max_tool_output: int = Field(
        default=require_int("ZENITH_MAX_TOOL_OUTPUT"), ge=1000
    )
    max_retries: int = Field(
        default=require_int("ZENITH_MAX_RETRIES"), ge=0, le=10
    )
    stream_max_retries: int = Field(
        default=require_int("ZENITH_STREAM_MAX_RETRIES"), ge=0, le=10
    )
    retry_base_delay: float = Field(
        default=require_float("ZENITH_RETRY_BASE_DELAY"), ge=0.1, le=30.0
    )
    retry_max_delay: float = Field(
        default=require_float("ZENITH_RETRY_MAX_DELAY"), ge=1.0, le=300.0
    )
    webfetch_timeout: int = Field(
        default=require_int("ZENITH_WEBFETCH_TIMEOUT"), ge=5, le=120
    )
    webfetch_max_bytes: int = Field(
        default=require_int("ZENITH_WEBFETCH_MAX_BYTES"), ge=1000, le=1000000
    )
    git_timeout: int = Field(
        default=require_int("ZENITH_GIT_TIMEOUT"), ge=5, le=120
    )


class BootstrapDefaults(BaseModel):
    active_provider: str = require_env("ZENITH_ACTIVE_PROVIDER")
    db_path: str = require_env("ZENITH_DB_PATH")
    log_level: str = require_env("ZENITH_LOG_LEVEL")
    max_context_tokens: int = Field(
        default=require_int("ZENITH_MAX_CONTEXT_TOKENS"), ge=1000
    )
    summary_threshold: float = Field(
        default=require_float("ZENITH_SUMMARY_THRESHOLD"), ge=0.1, le=1.0
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
