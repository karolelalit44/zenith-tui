"""Startup schemas — Pydantic models for startup validation endpoints."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from server.config.env import require_float, require_int

_DEFAULT_MAX_TOKENS = require_int("ZENITH_MAX_TOKENS")
_DEFAULT_TEMPERATURE = require_float("ZENITH_TEMPERATURE")


class StartupStatus(str, Enum):
    READY = "ready"
    CONFIGURATION_REQUIRED = "configuration_required"


class MissingItem(str, Enum):
    PROVIDER = "provider"
    MODEL = "model"
    API_KEY = "apiKey"
    CONFIG_FILE = "configFile"
    WORKSPACE = "workspace"
    DB_PATH = "dbPath"


class StartupResult(BaseModel):
    status: StartupStatus
    missing: list[MissingItem] = Field(default_factory=list)
    active_provider: str = ""
    active_model: str = ""
    provider_count: int = 0
    message: str = ""


class ProviderSetupRequest(BaseModel):
    provider: str
    api_key: str = ""
    model: str = ""
    base_url: str = ""
    max_tokens: int = _DEFAULT_MAX_TOKENS
    temperature: float = _DEFAULT_TEMPERATURE


class ProviderSetupResult(BaseModel):
    valid: bool
    provider: str = ""
    model: str = ""
    message: str = ""


class ProviderConfigResponse(BaseModel):
    active_provider: str = ""
    providers: dict[str, dict[str, Any]] = {}


class ProviderModelInfo(BaseModel):
    id: str
    name: str
    context_window: int = 128000
    description: str = ""
    is_default: bool = False
    status: str = "active"
    parameters: Any = None
    architecture: Any = None
    input_modalities: Any = None
    output_modalities: Any = None
    tags: list[str] = Field(default_factory=list)
    model_capabilities: dict[str, Any] = Field(default_factory=dict)
    speed_tier: Any = None
    best_for: list[str] = Field(default_factory=list)
    pricing: dict[str, Any] = Field(default_factory=dict)


class ProviderInfo(BaseModel):
    id: str
    name: str
    description: str = ""
    adapter: str = ""
    swatch: list[str] = Field(default_factory=list)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    api_key_prefix: str | None = None
    requires_api_key: bool = True
    config_fields: list[dict[str, Any]] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)
    has_api_key: bool = False
    api_key_masked: str = ""
    validation_status: str = "unconfigured"
    last_validation_error: str = ""
    is_active: bool = False
    model: str = ""
    models: dict[str, ProviderModelInfo] = Field(default_factory=dict)


class ProviderListResponse(BaseModel):
    all: list[ProviderInfo] = Field(default_factory=list)
    default: dict[str, str] = Field(default_factory=dict)
    connected: list[str] = Field(default_factory=list)


class ProviderAuthRequest(BaseModel):
    api_key: str = ""


class ProviderModelRequest(BaseModel):
    model: str


class ProviderValidationRequest(BaseModel):
    api_key: str = ""
    base_url: str = ""
    model: str = ""


class ValidationStepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class ValidationStep(BaseModel):
    key: str
    label: str
    status: ValidationStepStatus = ValidationStepStatus.PENDING
    message: str = ""


class ValidationError(BaseModel):
    code: str = ""
    message: str = ""


class ValidationResult(BaseModel):
    valid: bool
    provider: str = ""
    steps: list[ValidationStep] = Field(default_factory=list)
    models: list[ProviderModelInfo] = Field(default_factory=list)
    error: ValidationError | None = None
