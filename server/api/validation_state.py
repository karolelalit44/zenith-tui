"""Runtime provider validation state — in-memory only, not persisted.

Validation status is derived at read time from persisted facts (does the
provider have an API key?) plus session-scoped results of the validate
pipeline. Deliberately NOT stored in the DB: status falls back to
``configured`` after a server restart, which is correct and cheap.
"""

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
    """Drop session state for a provider (e.g. after credentials change)."""
    with _lock:
        _statuses.pop(provider_id, None)


def mark_validated(provider_id: str) -> None:
    from datetime import datetime

    with _lock:
        entry = _get(provider_id)
        entry.status = VALIDATED
        entry.last_error = ""
        entry.last_validated_at = datetime.now().isoformat()


def mark_failed(provider_id: str, message: str) -> None:
    from datetime import datetime

    with _lock:
        entry = _get(provider_id)
        entry.status = FAILED
        entry.last_error = message or ""
        entry.last_validated_at = datetime.now().isoformat()


def mark_configured(provider_id: str) -> None:
    with _lock:
        entry = _get(provider_id)
        if entry.status not in (VALIDATED,):
            entry.status = CONFIGURED
            entry.last_error = ""


def get_status(provider_id: str, has_api_key: bool) -> str:
    """Effective status: unconfigured when no key, else session state (configured/validated/failed)."""
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


def snapshot() -> dict[str, dict[str, object]]:
    """Full copy of session state (for tests/debugging)."""
    with _lock:
        return {pid: dict(entry.extra, status=entry.status, last_error=entry.last_error) for pid, entry in _statuses.items()}


def _get(provider_id: str) -> _Entry:
    entry = _statuses.get(provider_id)
    if entry is None:
        entry = _statuses[provider_id] = _Entry()
    return entry  # type: ignore[return-value]
