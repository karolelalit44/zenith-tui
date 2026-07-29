"""Startup schemas — Pydantic models for startup validation endpoints."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from config.env import require_float, require_int

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
