from __future__ import annotations

from dataclasses import dataclass, field

UNCONFIGURED = "unconfigured"
CONFIGURED = "configured"
VALIDATED = "validated"
FAILED = "failed"
_statuses: dict[str, _Entry] = {}


@dataclass
class _Entry:
    status: str = CONFIGURED
    last_error: str = ""
    last_validated_at: str = ""
    extra: dict[str, object] = field(default_factory=dict)


def reset(provider_id: str) -> None:
    _statuses.pop(provider_id, None)


def mark_validated(provider_id: str) -> None:
    from datetime import datetime

    entry = _statuses.setdefault(provider_id, _Entry())
    entry.status = VALIDATED
    entry.last_error = ""
    entry.last_validated_at = datetime.now().isoformat()


def get_status(provider_id: str, is_configured: bool) -> str:
    """Report the provider's validation state.

    ``is_configured`` is the caller's "usable" decision, not just key presence:
    a keyless provider (local model, self-hosted base_url) is usable with no key,
    and folding the two together made `connected` disagree with the client.
    """
    if not is_configured:
        return UNCONFIGURED
    entry = _statuses.get(provider_id)
    if entry is None:
        return CONFIGURED
    if entry.status == FAILED:
        return FAILED
    if entry.status == VALIDATED:
        return VALIDATED
    return CONFIGURED


def get_last_error(provider_id: str) -> str:
    entry = _statuses.get(provider_id)
    if entry is None:
        return ""
    return entry.last_error or ""


def _get(provider_id: str) -> _Entry:
    return _statuses.setdefault(provider_id, _Entry())
