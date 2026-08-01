"""Middleware — validates application state before processing requests."""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import wraps

from server.config.settings import AppSettings
from server.domain.errors import ConfigError

logger = logging.getLogger(__name__)

PROVIDER_METHODS = {
    "prompt.send",
    "provider.validate",
    "provider.models",
}


def validate_provider_config(config: AppSettings) -> None:
    """Validate that the active provider is properly configured.

    Raises ConfigError if validation fails.
    """
    active = config.active_provider
    if not active:
        raise ConfigError("No active provider configured.")

    providers = config.providers or {}
    provider_config = providers.get(active)
    if not provider_config:
        raise ConfigError(
            f"Active provider '{active}' is not configured. "
            f"Available: {list(providers.keys()) or 'none'}. "
            "Use the /provider command to configure a provider."
        )

    if not provider_config.api_key or not provider_config.api_key.strip():
        raise ConfigError(
            f"API key for '{active}' is missing. "
            "Configure it via the /provider command."
        )

    if not provider_config.model or not provider_config.model.strip():
        raise ConfigError(
            f"Model for '{active}' is not set. "
            "Select a model via the /provider command."
        )


def require_provider(method_name: str) -> bool:
    """Check if a WebSocket method requires provider configuration."""
    return method_name in PROVIDER_METHODS or method_name.startswith("prompt.")


def wrap_handler(dispatch_fn: Callable) -> Callable:
    """Wrap WebSocket dispatch with provider validation middleware.

    ``dispatch_fn`` is a bound method (e.g. ``handlers.dispatch``),
    so the middleware calls it with (ws, method, rid, params, session_id).
    """

    @wraps(dispatch_fn)
    async def middleware(ws, method: str, rid, params: dict, session_id: str | None):
        if require_provider(method):
            try:
                validate_provider_config(dispatch_fn.__self__.config)
            except ConfigError as e:
                from .protocol import make_error_response

                await ws.send_text(
                    make_error_response(rid, -32000, str(e))
                )
                return session_id
        return await dispatch_fn(ws, method, rid, params, session_id)

    return middleware
