from __future__ import annotations

import threading
from dataclasses import dataclass, field

UNCONFIGURED = "unconfigured"
CONFIGURED = "configured"
VALIDATED = "validated"
FAILED = "failed"
_statuses: dict[str, dict[str, object]] = {}
_lock = threading.Lock()


@dataclass
class _Entry:
    status: str = CONFIGURED
    last_error: str = ""
    last_validated_at: str = ""
    extra: dict[str, object] = field(default_factory=dict)


def reset(provider_id: str) -> None:
    with _lock:
        _statuses.pop(provider_id, None)


def mark_validated(provider_id: str) -> None:
    from datetime import datetime

    with _lock:
        entry = _get(provider_id)
        entry.status = VALIDATED
        entry.last_error = ""
        entry.last_validated_at = datetime.now().isoformat()


def get_status(provider_id: str, has_api_key: bool) -> str:
    if not has_api_key:
        return UNCONFIGURED
    with _lock:
        entry = _get(provider_id)
        if entry.status == FAILED:
            return FAILED
        if entry.status == VALIDATED:
            return VALIDATED
        return CONFIGURED


def get_last_error(provider_id: str) -> str:
    with _lock:
        entry = _get(provider_id)
        return entry.last_error or ""


def _get(provider_id: str) -> _Entry:
    entry = _statuses.get(provider_id)
    if entry is None:
        entry = _statuses[provider_id] = _Entry()
    return entry
