from __future__ import annotations
import logging
from pathlib import Path
from server.config.loader import load_config
from .schemas import (MissingItem, StartupResult, StartupStatus)

logger = logging.getLogger(__name__)

def validate_startup(workspace_root: str = ".") -> StartupResult:
    missing: list[MissingItem] = []

    try:
        config = load_config(workspace_root)
    except Exception as e:
        logger.error("Config load failed: %s", e)
        return StartupResult(status=StartupStatus.CONFIGURATION_REQUIRED, missing=[MissingItem.CONFIG_FILE], message=f"Could not load configuration: {e}")

    providers = config.providers or {}
    active = config.active_provider

    if not providers or not active or active not in providers:
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

    return StartupResult(status=status, missing=missing, active_provider=active or "", active_model=active_model, provider_count=len(providers), message=message)
