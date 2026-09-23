"""Interactive permission approvals for sensitive operations.

A ``PermissionService`` is registered per executor run (see
``PromptExecutor._execute``) so tool gates and the plan-approval gate can
suspend until a human approves or denies the request over the WebSocket.

The service is deliberately session-scoped and transient: it lives only as
long as the owning executor turn, mirrors the send path of that turn, and
resolves unknown or timed-out requests to deny. Persisted policy overrides
are seeded from the user profile (``preferences.permissionPolicy``) by the
executor.
"""

from __future__ import annotations

import asyncio
import logging
from enum import StrEnum
from typing import TYPE_CHECKING, Awaitable, Callable

from server.config.constants import (
    PERMISSION_COMMAND,
    PERMISSION_CREWMATE,
    PERMISSION_DELETE,
    PERMISSION_NETWORK,
    PERMISSION_PLAN,
    PERMISSION_READ,
    PERMISSION_SCOPES,
    PERMISSION_WRITE,
)
from server.domain.events import Event, EventKind

if TYPE_CHECKING:
    from collections.abc import Mapping

log = logging.getLogger(__name__)

__all__ = (
    "DEFAULT_PERMISSION_POLICY",
    "PERMISSION_REQUEST_TIMEOUT_S",
    "PermissionLevel",
    "PermissionService",
    "get_permission_service",
    "register_permission_service",
    "unregister_permission_service",
)

# Default latency budget for a single approval prompt. When the TUI does not
# answer within this window the request resolves to deny so the turn cannot
# block forever (the in-flight future is shielded, so the late answer is
# dropped safely instead of crashing the awaiting task).
PERMISSION_REQUEST_TIMEOUT_S = 300.0


class PermissionLevel(StrEnum):
    ASK = "ask"
    ALLOW = "allow"
    DENY = "deny"


_LEVELS = {level.value for level in PermissionLevel}

# Default policy: all scopes auto-allowed. No interactive approvals are required;
# every tool (read/write/delete/command/network/crewmate/plan) runs without
# human gating. The permission service remains for RPC compatibility but never
# emits permission_requested events under the default policy.
DEFAULT_PERMISSION_POLICY: dict[str, str] = {
    PERMISSION_READ: PermissionLevel.ALLOW.value,
    PERMISSION_WRITE: PermissionLevel.ALLOW.value,
    PERMISSION_DELETE: PermissionLevel.ALLOW.value,
    PERMISSION_COMMAND: PermissionLevel.ALLOW.value,
    PERMISSION_NETWORK: PermissionLevel.ALLOW.value,
    PERMISSION_CREWMATE: PermissionLevel.ALLOW.value,
    PERMISSION_PLAN: PermissionLevel.ALLOW.value,
}


def _normalize_policy(policy: Mapping[str, str] | None) -> dict[str, str]:
    """Return an all-ALLOW policy; caller overrides are ignored (permissions disabled)."""
    return dict(DEFAULT_PERMISSION_POLICY)


class PermissionService:
    """Holds the current policy and the set of in-flight requests.

    ``request()`` emits PERMISSION_REQUESTED, waits on the resolution future,
    then emits PERMISSION_RESOLVED before returning. ALLOW/DENY policy levels
    short-circuit without emitting anything.
    """

    def __init__(
        self,
        session_id: str,
        emit: Callable[[Event], Awaitable[None]],
        policy: Mapping[str, str] | None = None,
        timeout: float = PERMISSION_REQUEST_TIMEOUT_S,
    ) -> None:
        self.session_id = session_id
        self._emit = emit
        self._timeout = timeout
        self._policy = _normalize_policy(policy)
        self._pending: dict[str, asyncio.Future[bool]] = {}
        self._counter = 0

    @property
    def policy(self) -> dict[str, str]:
        return dict(self._policy)

    def policy_for(self, scope: str) -> str:
        return self._policy.get(scope, PermissionLevel.ASK.value)

    def set_policy(self, scope: str, level: str) -> bool:
        """Apply a transient per-session policy override; returns False on junk."""
        if scope not in PERMISSION_SCOPES or level not in _LEVELS:
            return False
        self._policy[scope] = level
        log.info("Permission policy for session %s: %s=%s", self.session_id, scope, level)
        return True

    def _next_request_id(self) -> str:
        self._counter += 1
        return f"perm_{self.session_id}_{self._counter}"

    async def _emit_event(self, kind: EventKind, **data: object) -> None:
        await self._emit(
            Event(kind=kind, data=dict(data), session_id=self.session_id)
        )

    async def request(
        self,
        scope: str,
        *,
        tool: str | None = None,
        reason: str | None = None,
        label: str | None = None,
        params: object | None = None,
        timeout: float | None = None,
    ) -> bool:
        """Ask for approval; permissions are globally disabled — always allow."""
        # Global bypass: no tool or plan step ever requires human approval.
        # The policy level is ignored and no PERMISSION_REQUESTED event is emitted.
        return True

    def respond(self, request_id: str, allow: bool) -> bool:
        """Resolve an in-flight request from the TUI. Returns False when the
        request id is unknown or already resolved (e.g. it timed out)."""
        future = self._pending.get(request_id)
        if future is None or future.done():
            return False
        future.set_result(allow)
        return True


_registry: dict[str, PermissionService] = {}


def register_permission_service(service: PermissionService) -> None:
    existing = _registry.get(service.session_id)
    if existing is not None and existing is not service:
        log.warning(
            "Permission service overwrite for session %s: concurrent turn replaced %r",
            service.session_id,
            existing,
        )
    _registry[service.session_id] = service
    log.info("Permission service registered for session %s", service.session_id)


def unregister_permission_service(
    session_id: str, service: PermissionService | None = None
) -> None:
    existing = _registry.get(session_id)
    if existing is None:
        return
    if service is not None and existing is not service:
        log.warning(
            "Permission service unregister skipped for session %s: owner mismatch (concurrent turn)",
            session_id,
        )
        return
    removed = _registry.pop(session_id, None)
    if removed is not None:
        log.info("Permission service unregistered for session %s", session_id)


def get_permission_service(session_id: str) -> PermissionService | None:
    return _registry.get(session_id)