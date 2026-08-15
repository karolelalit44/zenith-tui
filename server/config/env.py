from __future__ import annotations

import os

from dotenv import load_dotenv


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
    val = os.environ.get(key)
    if val is None or val.strip() == "":
        raise RuntimeError(
            f"Required environment variable '{key}' is not set. Set it before starting the server."
        )
    return val.strip()


def require_int(key: str) -> int:
    val = require_env(key)
    try:
        return int(val)
    except ValueError:
        raise RuntimeError(
            f"Environment variable '{key}' must be an integer, got: {val!r}"
        ) from None


def optional_int(key: str, default: int) -> int:
    val = os.environ.get(key, "").strip()
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def optional_int_none(key: str) -> int | None:
    val = os.environ.get(key, "").strip()
    if not val:
        return None
    try:
        return int(val)
    except ValueError:
        return None


def optional_float(key: str, default: float) -> float:
    val = os.environ.get(key, "").strip()
    if not val:
        return default
    try:
        return float(val)
    except ValueError:
        return default


def optional_env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip() or default
