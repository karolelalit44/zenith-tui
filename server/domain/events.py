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
    AGENT_SPAWNED = "agent_spawned"
    AGENT_COMPLETE = "agent_complete"
    AGENT_FAILED = "agent_failed"
    AGENT_ORCHESTRATION = "agent_orchestration"
    SESSION_CREATED = "session_created"
    SESSION_INITIALIZED = "session_initialized"
    SESSION_RESUMED = "session_resumed"
    SESSION_COMPLETED = "session_completed"
    SESSION_SUMMARIZED = "session_summarized"
    SESSION_PAUSED = "session_paused"
    SESSION_ARCHIVED = "session_archived"
    SESSION_EXPORTED = "session_exported"
    SESSION_DELETED = "session_deleted"
    SESSION_RENAMED = "session_renamed"
    SESSION_DUPLICATED = "session_duplicated"
    SESSION_RESTORED = "session_restored"
    SESSION_ERROR = "session_error"
    SESSION_STATE_CHANGED = "session_state_changed"
    SESSION_CHECKPOINT_CREATED = "session_checkpoint_created"
    CONTEXT_UPDATED = "context_updated"
    CONTEXT_COMPACTED = "context_compacted"
    CONTEXT_RESET = "context_reset"
    CONTEXT_COMPACTION_STARTED = "context_compaction_started"
    CONTEXT_COMPACTION_PHASE = "context_compaction_phase"
    CONTEXT_COMPACTION_ENDED = "context_compaction_ended"
    TOKEN_USAGE_RECORDED = "token_usage_recorded"
    TOKEN_BUDGET_EXCEEDED = "token_budget_exceeded"
    TOKEN_STATS_UPDATED = "token_stats_updated"
    SYNC_STATUS = "sync_status"
    SYNC_EVENT = "sync_event"
    AGENT_STATUS = "agent_status"
    PLAN_READY = "plan_ready"
    PLAN_APPROVED = "plan_approved"
    PLAN_REJECTED = "plan_rejected"
    TURN_MANIFEST = "turn_manifest"
    TODO_BOARD = "todo_board"
    TODO_TEST = "todo_test"
    MODE_SWITCH = "mode_switch"
    PROVIDER_SWITCHED = "provider_switched"
    PROVIDER_ERROR = "provider_error"
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


class Subscription:
    def __init__(self, sub_id: str, queue: asyncio.Queue[Event | None], bus: EventBus):
        self.id = sub_id
        self._queue = queue
        self._bus = bus

    def cancel(self) -> None:
        self._bus.unsubscribe(self.id)

    async def next(self, timeout: float | None = None) -> Event | None:
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


class EventBus:
    def publish(self, event: Event, mode: DeliveryMode = DeliveryMode.LOSSY) -> None: ...

    def subscribe(
        self, event_type: EventKind | None = None, session_id: str | None = None
    ) -> Subscription:
        raise NotImplementedError

    def unsubscribe(self, subscription_id: str) -> None: ...


class AsyncEventBus(EventBus):
    def __init__(self, buffer_size: int = 4096) -> None:
        self._buffer_size = buffer_size
        self._subscriptions: dict[str, _SubscriptionEntry] = {}
        self._dropped: int = 0
        self._counter: int = 0

    def publish(self, event: Event, mode: DeliveryMode = DeliveryMode.LOSSY) -> None:
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

    def subscribe(
        self, event_type: EventKind | None = None, session_id: str | None = None
    ) -> Subscription:
        self._counter += 1
        sub_id = f"sub_{self._counter}"
        queue: asyncio.Queue[Event | None] = asyncio.Queue(maxsize=self._buffer_size)
        entry = _SubscriptionEntry(queue=queue, event_type=event_type, session_id=session_id)
        self._subscriptions[sub_id] = entry
        return Subscription(sub_id, queue, self)

    def unsubscribe(self, subscription_id: str) -> None:
        entry = self._subscriptions.pop(subscription_id, None)
        if entry is not None:
            try:
                entry.queue.put_nowait(None)
            except asyncio.QueueFull:
                pass

    def _matches(self, entry: _SubscriptionEntry, event: Event) -> bool:
        if entry.event_type is not None and event.kind != entry.event_type:
            return False
        return not (entry.session_id is not None and event.session_id != entry.session_id)


class _SubscriptionEntry(BaseModel):
    queue: Any
    event_type: EventKind | None = None
    session_id: str | None = None
