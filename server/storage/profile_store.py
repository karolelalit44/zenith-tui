"""user_profile.json — identity, API keys, and preferences.

The single secret-bearing file in the storage layout (decision D5/D6).
The server owns it; the TUI reads masked data over HTTP only.

All read-modify-write cycles on the profile document run under
:data:`PROFILE_LOCK` (a process-wide ``threading.RLock``) because profile
writes originate both from the asyncio event loop and from FastAPI's
threadpool (sync ``def`` endpoints); an ``asyncio.Lock`` cannot serialize
across those boundaries.
"""

from __future__ import annotations

import copy
import logging
import threading

from .atomic import read_json, write_json_atomic
from .paths import StorageHome

logger = logging.getLogger(__name__)

PROFILE_VERSION = 1

PROFILE_LOCK = threading.RLock()

_DEFAULT_PROFILE: dict = {
    "version": PROFILE_VERSION,
    "activeProviderId": "",
    "activeModelId": "",
    "apiKeys": {},
    "providerSettings": {},
    "preferences": {
        "theme": "dark",
    },
}

_ALLOWED_PREFERENCE_TYPES: dict[str, type] = {
    "theme": str,
    "thinkingCollapsed": bool,
    "calmMode": bool,
    "autoApproveTools": bool,
    "defaultMode": str,
}


def validate_preferences(updates: dict) -> dict:
    """Reject unknown or wrongly-typed preference keys with ``ValueError``."""
    unknown = sorted(set(updates) - set(_ALLOWED_PREFERENCE_TYPES))
    if unknown:
        raise ValueError(f"unsupported preference key(s): {unknown}")
    for key, value in updates.items():
        expected = _ALLOWED_PREFERENCE_TYPES[key]
        if expected is str:
            if not isinstance(value, str):
                raise ValueError(f"preference {key!r} must be a string")
            if key == "defaultMode" and value not in ("build", "plan"):
                raise ValueError(f"preference defaultMode must be 'build' or 'plan', got {value!r}")
            if key == "theme" and not value.strip():
                raise ValueError("preference theme must be non-empty")
        elif expected is bool and not isinstance(value, bool):
            raise ValueError(f"preference {key!r} must be a boolean")
        elif expected is list:
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise ValueError(f"preference {key!r} must be a list of strings")
            if len(value) > 20:
                raise ValueError(f"preference {key!r} exceeds maximum length")
    return updates


def default_profile() -> dict:
    return copy.deepcopy(_DEFAULT_PROFILE)


def load_profile(home: StorageHome) -> dict:
    data = read_json(home.profile_path, None)
    if not isinstance(data, dict):
        data = default_profile()
    version = data.get("version")
    if isinstance(version, int) and version > PROFILE_VERSION:
        logger.warning(
            "user_profile.json declares version %s, newer than supported %s — "
            "proceeding with defaults merged in",
            version,
            PROFILE_VERSION,
        )
    merged = default_profile()
    for key, value in data.items():
        if key == "preferences" and isinstance(value, dict) and isinstance(merged[key], dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


def save_profile(home: StorageHome, profile: dict) -> None:
    write_json_atomic(home.profile_path, profile, private=True)


def mask_api_key(key: str | None) -> str:
    """Minimal exposure: never show leading characters of a secret."""
    if not key:
        return ""
    stripped = key.strip()
    if not stripped:
        return ""
    if len(stripped) <= 4:
        return "***"
    return "***" + stripped[-4:]


def get_api_key(profile: dict, provider_id: str) -> str:
    keys = profile.get("apiKeys") or {}
    value = keys.get(provider_id, "")
    return value.strip() if isinstance(value, str) else ""


def set_api_key(profile: dict, provider_id: str, api_key: str) -> None:
    keys = profile.setdefault("apiKeys", {})
    if api_key:
        keys[provider_id] = api_key
    else:
        keys.pop(provider_id, None)


def has_any_key(profile: dict) -> bool:
    return any(bool(v) for v in (profile.get("apiKeys") or {}).values())


def public_profile(profile: dict) -> dict:
    """Masked view safe to send over HTTP."""
    keys = profile.get("apiKeys") or {}
    settings = profile.get("providerSettings") or {}
    return {
        "version": profile.get("version", PROFILE_VERSION),
        "activeProviderId": profile.get("activeProviderId", ""),
        "activeModelId": profile.get("activeModelId", ""),
        "providers": {
            pid: {
                "hasApiKey": bool(value),
                "apiKeyMasked": mask_api_key(value),
            }
            for pid, value in keys.items()
        },
        "providerSettings": settings,
        "preferences": profile.get("preferences") or {},
    }


def update_preferences(home: StorageHome, updates: dict) -> dict:
    """Atomically merge validated preference updates; returns new prefs."""
    validate_preferences(updates)
    with PROFILE_LOCK:
        profile = load_profile(home)
        prefs = profile.setdefault("preferences", {})
        for key, value in updates.items():
            # Defense in depth: secrets are never writable via this path.
            if key.lower() in {"apikey", "apikeys", "apikey_masked"}:
                continue
            prefs[key] = value
        save_profile(home, profile)
    return prefs

