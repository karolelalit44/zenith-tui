"""Event system — domain events, event bus, and subscriptions.

This module provides:
- EventKind: all event types in the system
- Event: the core event model
- EventBus: pub/sub broker for decoupled communication
- AsyncEventBus: async implementation using asyncio.Queue

The EventBus supports:
- Typed subscriptions (filter by event_type and/or session_id)
- Multiple delivery modes (lossy, blocking, persistent)
- Automatic cleanup on unsubscribe
- Drop counters for observability
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from .domain import DeliveryMode

log = logging.getLogger(__name__)


class EventKind(StrEnum):
    THINKING = "thinking"
    MESSAGE = "message"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    WARNING = "warning"
    SUCCESS = "success"
    PROGRESS = "progress"
    CONFIRMATION_REQUEST = "confirmation_request"

    # Agent events
    AGENT_SPAWNED = "agent_spawned"
    AGENT_COMPLETE = "agent_complete"
    AGENT_FAILED = "agent_failed"

    # Session events
    SESSION_CREATED = "session_created"
    SESSION_RESUMED = "session_resumed"
    SESSION_SUMMARIZED = "session_summarized"

    # Plan/Approval events
    PLAN_READY = "plan_ready"
    PLAN_APPROVED = "plan_approved"
    PLAN_REJECTED = "plan_rejected"

    # Mode switch events
    MODE_SWITCH = "mode_switch"

    # Provider events
    PROVIDER_SWITCHED = "provider_switched"
    PROVIDER_ERROR = "provider_error"

    # System events
    SYSTEM_READY = "system_ready"
    SYSTEM_SHUTDOWN = "system_shutdown"


class Event(BaseModel):
    kind: EventKind
    id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}")
    session_id: str | None = None
    timestamp: float = Field(default_factory=time.time)
    data: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    parent_event_id: str | None = None


def make_event(kind: EventKind, data: dict[str, Any], session_id: str | None = None) -> Event:
    return Event(kind=kind, data=data, session_id=session_id)


# ---------------------------------------------------------------------------
# Subscription handle
# ---------------------------------------------------------------------------

class Subscription:
    """Handle returned by EventBus.subscribe(). Call cancel() to unsubscribe."""

    def __init__(
        self,
        sub_id: str,
        queue: asyncio.Queue[Event | None],
        bus: EventBus,
    ):
        self.id = sub_id
        self._queue = queue
        self._bus = bus

    def cancel(self) -> None:
        self._bus.unsubscribe(self.id)

    async def next(self, timeout: float | None = None) -> Event | None:
        """Wait for the next event. Returns None when the subscription ends."""
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except TimeoutError:
            return None

    def __aiter__(self) -> AsyncIterator[Event]:
        return self._aiter()

    async def _aiter(self) -> AsyncIterator[Event]:
        while True:
            event = await self.next()
            if event is None:
                break
            yield event


# ---------------------------------------------------------------------------
# EventBus ABC
# ---------------------------------------------------------------------------

class EventBus:
    """Abstract event bus interface.

    Concrete implementations handle delivery guarantees and persistence.
    """

    def publish(
        self,
        event: Event,
        mode: DeliveryMode = DeliveryMode.LOSSY,
    ) -> None:
        ...

    def subscribe(
        self,
        event_type: EventKind | None = None,
        session_id: str | None = None,
    ) -> Subscription:
        ...

    def unsubscribe(self, subscription_id: str) -> None:
        ...

    async def get_persistent_events(
        self,
        session_id: str,
        since: float | None = None,
    ) -> list[Event]:
        ...

    @property
    def dropped_count(self) -> int:
        return 0


# ---------------------------------------------------------------------------
# AsyncEventBus — in-memory async implementation
# ---------------------------------------------------------------------------

class AsyncEventBus(EventBus):
    """In-memory async event bus using asyncio.Queue.

    DeliveryMode.LOSSY:  drops events when a subscriber's buffer is full.
    DeliveryMode.BLOCKING: waits until the subscriber consumes the event.
    """

    def __init__(self, buffer_size: int = 4096) -> None:
        self._buffer_size = buffer_size
        self._subscriptions: dict[str, _SubscriptionEntry] = {}
        self._dropped: int = 0
        self._counter: int = 0

    # -- publish -------------------------------------------------------------

    def publish(
        self,
        event: Event,
        mode: DeliveryMode = DeliveryMode.LOSSY,
    ) -> None:
        for entry in list(self._subscriptions.values()):
            if not self._matches(entry, event):
                continue
            if mode == DeliveryMode.BLOCKING:
                entry.queue.put_nowait(event)
            else:
                if entry.queue.full():
                    self._dropped += 1
                    continue
                entry.queue.put_nowait(event)

    # -- subscribe / unsubscribe ---------------------------------------------

    def subscribe(
        self,
        event_type: EventKind | None = None,
        session_id: str | None = None,
    ) -> Subscription:
        self._counter += 1
        sub_id = f"sub_{self._counter}"
        queue: asyncio.Queue[Event | None] = asyncio.Queue(
            maxsize=self._buffer_size,
        )
        entry = _SubscriptionEntry(
            queue=queue,
            event_type=event_type,
            session_id=session_id,
        )
        self._subscriptions[sub_id] = entry
        return Subscription(sub_id, queue, self)

    def unsubscribe(self, subscription_id: str) -> None:
        entry = self._subscriptions.pop(subscription_id, None)
        if entry is not None:
            try:
                entry.queue.put_nowait(None)
            except asyncio.QueueFull:
                pass

    # -- persistence (no-op for in-memory) -----------------------------------

    async def get_persistent_events(
        self,
        session_id: str,
        since: float | None = None,
    ) -> list[Event]:
        return []

    # -- observability -------------------------------------------------------

    @property
    def dropped_count(self) -> int:
        return self._dropped

    # -- internal ------------------------------------------------------------

    def _matches(self, entry: _SubscriptionEntry, event: Event) -> bool:
        if entry.event_type is not None and event.kind != entry.event_type:
            return False
        return not (entry.session_id is not None and event.session_id != entry.session_id)


class _SubscriptionEntry(BaseModel):
    """Internal record for a subscription."""
    queue: Any  # asyncio.Queue[Event | None]
    event_type: EventKind | None = None
    session_id: str | None = None
