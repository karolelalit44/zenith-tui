"""Environment configuration and resolution for Zenith server.

Central source of truth for runtime environment details and configuration.
No .env files are loaded; environment configuration is defined directly as
typed constants in this module and can be overridden via process environment variables.
"""

from __future__ import annotations

import os
from pathlib import Path


def _default_home() -> str:
    return str(Path.home() / ".zenith")


# Direct constant values for environment configuration
ZENITH_HOST: str = os.environ.get("ZENITH_HOST") or "127.0.0.1"
ZENITH_PORT: int = int(os.environ.get("ZENITH_PORT") or 8765)
ZENITH_HOME: str = os.environ.get("ZENITH_HOME") or _default_home()
ZENITH_LOG_LEVEL: str = os.environ.get("ZENITH_LOG_LEVEL") or "info"
ZENITH_MAX_CONTEXT_TOKENS: int = int(os.environ.get("ZENITH_MAX_CONTEXT_TOKENS") or 128000)
ZENITH_SUMMARY_THRESHOLD: float = float(os.environ.get("ZENITH_SUMMARY_THRESHOLD") or 0.8)
ZENITH_CONTEXT_COMPACTION_THRESHOLD: float = float(
    os.environ.get("ZENITH_CONTEXT_COMPACTION_THRESHOLD") or 0.7
)
ZENITH_ASYNC_SUMMARY_ENABLED: bool = (
    os.environ.get("ZENITH_ASYNC_SUMMARY_ENABLED", "false").strip().lower()
    in {"1", "true", "yes", "on"}
)
ZENITH_MAX_TOOL_OUTPUT: int = int(os.environ.get("ZENITH_MAX_TOOL_OUTPUT") or 10000)
ZENITH_BASH_TIMEOUT: int = int(os.environ.get("ZENITH_BASH_TIMEOUT") or 300)
ZENITH_GIT_TIMEOUT: int = int(os.environ.get("ZENITH_GIT_TIMEOUT") or 300)
ZENITH_WEBFETCH_TIMEOUT: int = int(os.environ.get("ZENITH_WEBFETCH_TIMEOUT") or 300)
ZENITH_WEBFETCH_MAX_BYTES: int = int(os.environ.get("ZENITH_WEBFETCH_MAX_BYTES") or 50000)
ZENITH_WEBSEARCH_TIMEOUT: int = int(os.environ.get("ZENITH_WEBSEARCH_TIMEOUT") or 300)
ZENITH_VALIDATION_TIMEOUT: int = int(os.environ.get("ZENITH_VALIDATION_TIMEOUT") or 300)
ZENITH_SUMMARIZER_TIMEOUT: float = float(os.environ.get("ZENITH_SUMMARIZER_TIMEOUT") or 300.0)
ZENITH_MAX_TOKENS: int = int(os.environ.get("ZENITH_MAX_TOKENS") or 4096)
ZENITH_TEMPERATURE: float = float(os.environ.get("ZENITH_TEMPERATURE") or 0.7)
ZENITH_WS_MAX_RECONNECT: int = int(os.environ.get("ZENITH_WS_MAX_RECONNECT") or 5)
ZENITH_WS_RECONNECT_DELAY: int = int(os.environ.get("ZENITH_WS_RECONNECT_DELAY") or 1000)
ZENITH_WS_RPC_TIMEOUT: int = int(os.environ.get("ZENITH_WS_RPC_TIMEOUT") or 60000)
ZENITH_GIT_CACHE_TTL: int = int(os.environ.get("ZENITH_GIT_CACHE_TTL") or 30000)
ZENITH_EXPLORE_DELEGATION: str = os.environ.get("ZENITH_EXPLORE_DELEGATION") or "tool"
ZENITH_EXPLORE_TOKEN_BUDGET: int = int(os.environ.get("ZENITH_EXPLORE_TOKEN_BUDGET") or 120000)
ZENITH_ENRICH_TIMEOUT: float = float(os.environ.get("ZENITH_ENRICH_TIMEOUT") or 20.0)
ZENITH_SALVAGE_TIMEOUT: float = float(os.environ.get("ZENITH_SALVAGE_TIMEOUT") or 60.0)
ZENITH_MIN_REQUEST_INTERVAL: float = float(os.environ.get("ZENITH_MIN_REQUEST_INTERVAL") or 0.0)

# Seed unset variables into os.environ with canonical constants
_CANONICAL_VARS: dict[str, str] = {
    "ZENITH_HOST": ZENITH_HOST,
    "ZENITH_PORT": str(ZENITH_PORT),
    "ZENITH_HOME": ZENITH_HOME,
    "ZENITH_LOG_LEVEL": ZENITH_LOG_LEVEL,
    "ZENITH_MAX_CONTEXT_TOKENS": str(ZENITH_MAX_CONTEXT_TOKENS),
    "ZENITH_SUMMARY_THRESHOLD": str(ZENITH_SUMMARY_THRESHOLD),
    "ZENITH_CONTEXT_COMPACTION_THRESHOLD": str(ZENITH_CONTEXT_COMPACTION_THRESHOLD),
    "ZENITH_ASYNC_SUMMARY_ENABLED": "true" if ZENITH_ASYNC_SUMMARY_ENABLED else "false",
    "ZENITH_MAX_TOOL_OUTPUT": str(ZENITH_MAX_TOOL_OUTPUT),
    "ZENITH_BASH_TIMEOUT": str(ZENITH_BASH_TIMEOUT),
    "ZENITH_GIT_TIMEOUT": str(ZENITH_GIT_TIMEOUT),
    "ZENITH_WEBFETCH_TIMEOUT": str(ZENITH_WEBFETCH_TIMEOUT),
    "ZENITH_WEBFETCH_MAX_BYTES": str(ZENITH_WEBFETCH_MAX_BYTES),
    "ZENITH_WEBSEARCH_TIMEOUT": str(ZENITH_WEBSEARCH_TIMEOUT),
    "ZENITH_VALIDATION_TIMEOUT": str(ZENITH_VALIDATION_TIMEOUT),
    "ZENITH_SUMMARIZER_TIMEOUT": str(ZENITH_SUMMARIZER_TIMEOUT),
    "ZENITH_MAX_TOKENS": str(ZENITH_MAX_TOKENS),
    "ZENITH_TEMPERATURE": str(ZENITH_TEMPERATURE),
    "ZENITH_WS_MAX_RECONNECT": str(ZENITH_WS_MAX_RECONNECT),
    "ZENITH_WS_RECONNECT_DELAY": str(ZENITH_WS_RECONNECT_DELAY),
    "ZENITH_WS_RPC_TIMEOUT": str(ZENITH_WS_RPC_TIMEOUT),
    "ZENITH_GIT_CACHE_TTL": str(ZENITH_GIT_CACHE_TTL),
    "ZENITH_EXPLORE_DELEGATION": ZENITH_EXPLORE_DELEGATION,
    "ZENITH_EXPLORE_TOKEN_BUDGET": str(ZENITH_EXPLORE_TOKEN_BUDGET),
    "ZENITH_ENRICH_TIMEOUT": str(ZENITH_ENRICH_TIMEOUT),
    "ZENITH_SALVAGE_TIMEOUT": str(ZENITH_SALVAGE_TIMEOUT),
    "ZENITH_MIN_REQUEST_INTERVAL": str(ZENITH_MIN_REQUEST_INTERVAL),
}

for _k, _v in _CANONICAL_VARS.items():
    os.environ.setdefault(_k, _v)


def get_env(key: str) -> str:
    """Retrieve an environment configuration value by variable name."""
    raw = os.environ.get(key)
    if raw is not None and raw.strip() != "":
        return raw.strip()
    val = globals().get(key)
    if val is not None:
        return str(val)
    raise KeyError(f"Environment variable '{key}' is not defined in environment configuration.")


def get_int(key: str) -> int:
    """Retrieve an integer environment configuration value by variable name."""
    val = globals().get(key)
    if val is not None and isinstance(val, int):
        raw = os.environ.get(key)
        if raw is not None and raw.strip() != "":
            try:
                return int(raw.strip())
            except ValueError as err:
                raise ValueError(f"Environment variable '{key}' value {raw!r} cannot be parsed as int.") from err
        return val
    raw_str = get_env(key)
    try:
        return int(raw_str)
    except ValueError as err:
        raise ValueError(f"Environment variable '{key}' value {raw_str!r} cannot be parsed as int.") from err


def get_float(key: str) -> float:
    """Retrieve a float environment configuration value by variable name."""
    val = globals().get(key)
    if val is not None and isinstance(val, (float, int)):
        raw = os.environ.get(key)
        if raw is not None and raw.strip() != "":
            try:
                return float(raw.strip())
            except ValueError as err:
                raise ValueError(f"Environment variable '{key}' value {raw!r} cannot be parsed as float.") from err
        return float(val)
    raw_str = get_env(key)
    try:
        return float(raw_str)
    except ValueError as err:
        raise ValueError(f"Environment variable '{key}' value {raw_str!r} cannot be parsed as float.") from err


def get_bool(key: str) -> bool:
    """Retrieve a boolean environment configuration value by variable name."""
    val = globals().get(key)
    raw = os.environ.get(key)
    target = raw.strip().lower() if raw is not None and raw.strip() != "" else None
    if target is None and val is not None and isinstance(val, bool):
        return val
    if target is not None:
        if target in {"1", "true", "yes", "on"}:
            return True
        if target in {"0", "false", "no", "off"}:
            return False
        raise ValueError(f"Environment variable '{key}' value {raw!r} cannot be parsed as bool.")
    if val is not None and isinstance(val, bool):
        return val
    raise KeyError(f"Environment variable '{key}' is not defined in environment configuration.")


def optional_env(key: str, default: str | None = None) -> str:
    return get_env(key)


def optional_int(key: str, default: int | None = None) -> int:
    return get_int(key)


def optional_float(key: str, default: float | None = None) -> float:
    return get_float(key)


def optional_bool(key: str, default: bool | None = None) -> bool:
    return get_bool(key)


__all__ = [
    "ZENITH_ASYNC_SUMMARY_ENABLED",
    "ZENITH_BASH_TIMEOUT",
    "ZENITH_CONTEXT_COMPACTION_THRESHOLD",
    "ZENITH_ENRICH_TIMEOUT",
    "ZENITH_EXPLORE_DELEGATION",
    "ZENITH_EXPLORE_TOKEN_BUDGET",
    "ZENITH_GIT_CACHE_TTL",
    "ZENITH_GIT_TIMEOUT",
    "ZENITH_HOME",
    "ZENITH_HOST",
    "ZENITH_LOG_LEVEL",
    "ZENITH_MAX_CONTEXT_TOKENS",
    "ZENITH_MAX_TOKENS",
    "ZENITH_MAX_TOOL_OUTPUT",
    "ZENITH_MIN_REQUEST_INTERVAL",
    "ZENITH_PORT",
    "ZENITH_SALVAGE_TIMEOUT",
    "ZENITH_SUMMARIZER_TIMEOUT",
    "ZENITH_SUMMARY_THRESHOLD",
    "ZENITH_TEMPERATURE",
    "ZENITH_VALIDATION_TIMEOUT",
    "ZENITH_WEBFETCH_MAX_BYTES",
    "ZENITH_WEBFETCH_TIMEOUT",
    "ZENITH_WEBSEARCH_TIMEOUT",
    "ZENITH_WS_MAX_RECONNECT",
    "ZENITH_WS_RECONNECT_DELAY",
    "ZENITH_WS_RPC_TIMEOUT",
    "get_bool",
    "get_env",
    "get_float",
    "get_int",
    "optional_bool",
    "optional_env",
    "optional_float",
    "optional_int",
]
