"""Environment variable helpers — read and validate required config values."""

from __future__ import annotations

import os

from dotenv import load_dotenv


# Load .env at import time — before any require_* calls at module level.
def _init_dotenv() -> None:
    try:
        from dotenv import find_dotenv
        env_path = find_dotenv(usecwd=True)
        if env_path:
            load_dotenv(env_path, override=False)
    except Exception:
        pass

_init_dotenv()


def require_env(key: str) -> str:
    """Read a required string environment variable. Raises immediately if not set."""
    val = os.environ.get(key)
    if val is None or val.strip() == "":
        raise RuntimeError(
            f"Required environment variable '{key}' is not set. "
            f"Set it before starting the server."
        )
    return val.strip()


def require_int(key: str) -> int:
    """Read a required integer environment variable. Raises if missing or invalid."""
    val = require_env(key)
    try:
        return int(val)
    except ValueError:
        raise RuntimeError(
            f"Environment variable '{key}' must be an integer, got: {val!r}"
        ) from None


def require_float(key: str) -> float:
    """Read a required float environment variable. Raises if missing or invalid."""
    val = require_env(key)
    try:
        return float(val)
    except ValueError:
        raise RuntimeError(
            f"Environment variable '{key}' must be a float, got: {val!r}"
        ) from None


def optional_int(key: str, default: int) -> int:
    """Read an optional integer env var, returning default if missing or invalid."""
    val = os.environ.get(key, "").strip()
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def optional_float(key: str, default: float) -> float:
    """Read an optional float env var, returning default if missing or invalid."""
    val = os.environ.get(key, "").strip()
    if not val:
        return default
    try:
        return float(val)
    except ValueError:
        return default


def optional_env(key: str, default: str = "") -> str:
    """Read an optional string env var, returning default if missing."""
    return os.environ.get(key, default).strip() or default
