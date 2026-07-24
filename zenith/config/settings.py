from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field, field_validator
from .providers import ProviderConfig


class ToolConfig(BaseModel):
    bash_enabled: bool = True
    file_write_enabled: bool = True
    file_edit_enabled: bool = True
    file_delete_enabled: bool = True
    max_bash_timeout: int = Field(default=30, ge=1, le=300)
    max_iterations: int = Field(default=25, ge=1, le=100)


class BootstrapDefaults(BaseModel):
    active_provider: str = "openai"
    db_path: str = "zenith.db"
    log_level: str = "info"
    max_context_tokens: int = Field(default=128000, ge=1000)
    summary_threshold: float = Field(default=0.8, ge=0.1, le=1.0)
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
                f"Add it to .zenith.json or set ZENITH_ACTIVE_PROVIDER."
            )
        return config
