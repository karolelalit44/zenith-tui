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

# Default policy. Read/write of workspace files is allowed (the platform's
# promise), while destructive, command, network, crewmate, and plan actions
# require explicit approval. Users can override any scope via the UI
# (profile.preferences.permissionPolicy) or the session permission.policy RPC.
DEFAULT_PERMISSION_POLICY: dict[str, str] = {
    PERMISSION_READ: PermissionLevel.ALLOW.value,
    PERMISSION_WRITE: PermissionLevel.ALLOW.value,
    PERMISSION_DELETE: PermissionLevel.ASK.value,
    PERMISSION_COMMAND: PermissionLevel.ASK.value,
    PERMISSION_NETWORK: PermissionLevel.ASK.value,
    PERMISSION_CREWMATE: PermissionLevel.ASK.value,
    PERMISSION_PLAN: PermissionLevel.ASK.value,
}


def _normalize_policy(policy: Mapping[str, str] | None) -> dict[str, str]:
    """Merge caller-supplied overrides onto the defaults, ignoring junk."""
    merged = dict(DEFAULT_PERMISSION_POLICY)
    if policy:
        for scope, level in policy.items():
            if scope in PERMISSION_SCOPES and level in _LEVELS:
                merged[scope] = level
    return merged


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
        """Ask for approval; returns True only when a human allowed it."""
        level = self.policy_for(scope)
        if level == PermissionLevel.ALLOW.value:
            return True
        if level == PermissionLevel.DENY.value:
            log.info(
                "Permission request denied by policy for session %s scope=%s tool=%s",
                self.session_id,
                scope,
                tool,
            )
            return False

        request_id = self._next_request_id()
        await self._emit_event(
            EventKind.PERMISSION_REQUESTED,
            session_id=self.session_id,
            requestId=request_id,
            scope=scope,
            tool=tool,
            reason=reason,
            label=label,
            params=params,
            timeout=self._timeout if timeout is None else timeout,
        )
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        granted = False
        try:
            try:
                granted = await asyncio.wait_for(
                    asyncio.shield(future),
                    timeout=self._timeout if timeout is None else timeout,
                )
            except TimeoutError:
                log.info(
                    "Permission request %s timed out after %.0fs (denied)",
                    request_id,
                    self._timeout if timeout is None else timeout,
                )
                granted = False
        finally:
            self._pending.pop(request_id, None)
            await self._emit_event(
                EventKind.PERMISSION_RESOLVED,
                session_id=self.session_id,
                requestId=request_id,
                scope=scope,
                tool=tool,
                allow=granted,
            )
        return granted

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
    _registry[service.session_id] = service
    log.info("Permission service registered for session %s", service.session_id)


def unregister_permission_service(session_id: str) -> None:
    removed = _registry.pop(session_id, None)
    if removed is not None:
        log.info("Permission service unregistered for session %s", session_id)


def get_permission_service(session_id: str) -> PermissionService | None:
    return _registry.get(session_id)