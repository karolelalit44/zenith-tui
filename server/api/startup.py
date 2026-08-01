"""Startup validation — thin wrapper re-exporting schemas + startup check."""

from __future__ import annotations

import logging
from pathlib import Path

from server.config.loader import load_config
from server.persistence.repositories import load_catalog

from .provider_validation import (  # noqa: F401 — re-export
    get_provider_config,
    save_provider_config_endpoint,
    validate_provider_setup,
)

# Backward-compat alias for import resolution
save_provider_setup = save_provider_config_endpoint
from .schemas import (  # noqa: F401, E402 — re-export for backward compat
    MissingItem,
    ProviderConfigResponse,
    ProviderSetupRequest,
    ProviderSetupResult,
    StartupResult,
    StartupStatus,
)

logger = logging.getLogger(__name__)


def validate_startup(workspace_root: str = ".") -> StartupResult:
    """Validate all startup prerequisites and return structured result."""
    missing: list[MissingItem] = []

    try:
        config = load_config(workspace_root)
    except Exception as e:
        logger.error("Config load failed: %s", e)
        return StartupResult(
            status=StartupStatus.CONFIGURATION_REQUIRED,
            missing=[MissingItem.CONFIG_FILE],
            message=f"Could not load configuration: {e}",
        )

    providers = config.providers or {}
    active = config.active_provider
    catalog = load_catalog()
    known_providers = set(catalog.get("providers", {}).keys())

    if not providers or not active or (active not in providers and active not in known_providers):
        missing.append(MissingItem.PROVIDER)

    provider_config = providers.get(active) if active else None
    active_model = ""
    if provider_config:
        active_model = provider_config.model or ""

    if not active_model:
        missing.append(MissingItem.MODEL)

    if provider_config:
        has_key = bool(provider_config.api_key and provider_config.api_key.strip())
        if not has_key:
            missing.append(MissingItem.API_KEY)

    if not config.workspace_root or not Path(config.workspace_root).exists():
        missing.append(MissingItem.WORKSPACE)

    status = StartupStatus.READY if not missing else StartupStatus.CONFIGURATION_REQUIRED
    message = ""
    if missing:
        items = ", ".join(m.value for m in missing)
        message = f"Missing configuration: {items}"

    return StartupResult(
        status=status,
        missing=missing,
        active_provider=active or "",
        active_model=active_model,
        provider_count=len(providers),
        message=message,
    )
