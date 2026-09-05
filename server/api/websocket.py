from __future__ import annotations

import asyncio
import json
import logging

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from server.config.settings import AppSettings
from server.domain.events import Event, EventKind
from server.providers.registry import ProviderRegistry
from server.storage import StorageHome
from server.storage.session_store import (
    FileCheckpointRepository,
    FileMessageRepository,
    FileSessionRepository,
    FileSyncEventRepository,
)
from server.toolkit import create_default_registry
from server.toolkit.registry import ToolRegistry

from .handlers import MethodHandlers
from .protocol import (
    Connection,
    JsonRpcRequest,
    TransportService,
    make_error_response,
    serialize_event,
)

logger = logging.getLogger(__name__)


class ConnectionManager(TransportService):
    def __init__(self) -> None:
        self.connections: dict[str, WebSocket] = {}
        self.event_buffers: dict[str, list[str]] = {}
        self._disconnect_at: dict[str, int] = {}
        self._sequences: dict[str, int] = {}
        self.max_buffered_events = 5000
        self._session_service = None

    def set_session_service(self, service) -> None:
        self._session_service = service

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        self.connections[session_id] = websocket
        await self._init_sequence(session_id)
        logger.info("Client connected: %s", session_id)

    async def register(self, session_id: str, websocket: WebSocket) -> None:
        self.connections[session_id] = websocket
        await self._init_sequence(session_id)

    async def _init_sequence(self, session_id: str) -> None:
        if session_id in self._sequences:
            return
        db_latest = 0
        if self._session_service:
            try:
                db_latest = await self._session_service.get_latest_sync_sequence(session_id)
            except Exception:
                logger.debug("Failed to load sync sequence for session %s", session_id)
        self._sequences[session_id] = db_latest

    def disconnect(self, session_id: str) -> None:
        self.connections.pop(session_id, None)
        buf = self.event_buffers.get(session_id)
        if buf is not None:
            self._disconnect_at[session_id] = len(buf)
        logger.info("Client disconnected: %s", session_id)

    def drop_buffer(self, session_id: str) -> None:
        self.event_buffers.pop(session_id, None)
        self._disconnect_at.pop(session_id, None)
        self._sequences.pop(session_id, None)
        logger.info("Buffer dropped for session %s", session_id)

    def get_connections(self) -> list[Connection]:
        return [
            Connection(session_id=sid, client=str(ws.client))
            for sid, ws in self.connections.items()
        ]

    async def start(self, host: str, port: int) -> None:
        pass

    async def stop(self) -> None:
        for sid in list(self.connections):
            self.disconnect(sid)

    async def broadcast(self, event: Event) -> None:
        for sid in list(self.connections):
            await self.send_event(sid, event)

    def next_sequence(self, session_id: str) -> int:
        seq = self._sequences.get(session_id, 0) + 1
        self._sequences[session_id] = seq
        return seq

    async def send_event(self, session_id: str, event: Event) -> None:
        seq = self.next_sequence(session_id)
        event.metadata["sequence"] = seq
        payload = serialize_event(event)
        buf = self.event_buffers.setdefault(session_id, [])
        buf.append(payload)
        if len(buf) > self.max_buffered_events:
            # Front-eviction shifts every remaining index down; adjust the
            # replay marker recorded at disconnect() accordingly or the next
            # reconnect would replay an offset slice (duplicates/gaps).
            excess = len(buf) - self.max_buffered_events
            del buf[:excess]
            marked = self._disconnect_at.get(session_id)
            if marked is not None:
                self._disconnect_at[session_id] = max(0, marked - excess)
        await self._persist_event(session_id, event, seq)
        ws = self.connections.get(session_id)
        if ws:
            event.session_id = session_id
            try:
                await ws.send_text(payload)
            except Exception as exc:
                logger.warning("WS SEND FAIL session=%s kind=%s: %s", session_id, event.kind, exc)
        else:
            logger.debug(
                "WS BUFFER session=%s kind=%s buffer_size=%d", session_id, event.kind, len(buf)
            )

    def _should_persist(self, event: Event) -> bool:
        return not (
            event.kind == EventKind.THINKING
            or (event.kind == EventKind.MESSAGE and event.data.get("partial"))
        )

    async def _persist_event(self, session_id: str, event: Event, seq: int) -> None:
        if not session_id or self._session_service is None:
            return
        if not self._should_persist(event):
            return
        try:
            await self._session_service.record_sync_event(
                session_id, str(event.kind), event.data, sequence=seq
            )
        except Exception as exc:
            logger.warning(
                "Failed to persist sync event %s (session=%s): %s", event.kind, session_id, exc
            )

    async def schedule_session_event(
        self, session_id: str, kind: str | EventKind, event_data: dict
    ) -> None:
        if isinstance(kind, str):
            kind_map = {
                "session.created": EventKind.SESSION_CREATED,
                "session.paused": EventKind.SESSION_PAUSED,
                "session.duplicated": EventKind.SESSION_DUPLICATED,
            }
            event_kind = kind_map.get(kind)
            if event_kind is None:
                logger.warning("Unknown sync event kind: %s", kind)
                return
        else:
            event_kind = kind
        evt = Event(kind=event_kind, data=event_data, session_id=session_id)
        await self.send_event(session_id, evt)

    async def replay_events(self, session_id: str, websocket: WebSocket) -> int:
        buf = self.event_buffers.get(session_id)
        if not buf:
            return 0
        start = self._disconnect_at.pop(session_id, 0)
        new_events = buf[start:]
        if not new_events:
            return 0
        for payload in new_events:
            try:
                await websocket.send_text(payload)
            except Exception:
                break
        logger.info(
            "Replayed %d/%d buffered events for session %s", len(new_events), len(buf), session_id
        )
        return len(new_events)


class ZenithHandler:
    def __init__(
        self,
        config: AppSettings,
        home: StorageHome,
        registry: ProviderRegistry,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self.config = config
        self.home = home
        self.tool_registry = tool_registry or create_default_registry(
            timeout=config.tools.max_bash_timeout,
            provider=registry.get(config.active_provider),
            hooks=config.hooks,
        )
        from server.sessions.service import DefaultSessionService

        self.manager = ConnectionManager()
        # C-F03: DefaultSessionService publishes domain events on this bus;
        # without a live subscriber every _publish call is a silent no-op and
        # only session.created/paused/duplicated ever reached clients (via the
        # ad-hoc schedule_session_event path, now removed).
        from server.domain.events import AsyncEventBus

        self._event_bus = AsyncEventBus()
        self._bus_task: asyncio.Task | None = None
        self.handlers = MethodHandlers(config, home, registry, self.tool_registry)
        self.handlers.manager = self.manager
        self._session_service = DefaultSessionService(
            session_repo=FileSessionRepository(home),
            message_repo=FileMessageRepository(home),
            checkpoint_repo=FileCheckpointRepository(home),
            sync_event_repo=FileSyncEventRepository(home),
            event_bus=self._event_bus,
            hooks=config.hooks,
        )
        self.handlers._session_service = self._session_service
        self.manager.set_session_service(self._session_service)

    def _ensure_event_bus_bridge(self) -> None:
        """Drain the domain-event bus into connected WebSocket clients.

        Started lazily on the first handle() call so the bridge task always
        has a running loop (ZenithHandler may be constructed outside one).
        """

        if self._bus_task is not None and not self._bus_task.done():
            return

        # Subscribe synchronously *before* scheduling the task: publishes are
        # lossy and fire-and-forget, so a fast first publish (file-backed
        # repos don't yield like SQLite did) must already see a subscriber.
        subscription = self._event_bus.subscribe()

        async def _bridge():
            while True:
                event = await subscription.next()
                if event is None:
                    break
                if not event.session_id:
                    continue
                try:
                    await self.manager.send_event(event.session_id, event)
                except Exception as exc:
                    logger.warning(
                        "Event-bus delivery failed (session=%s kind=%s): %s",
                        event.session_id,
                        event.kind,
                        exc,
                    )

        self._bus_task = asyncio.ensure_future(_bridge())

    def _reload_provider(self, provider_id: str) -> None:
        self.handlers.reload_provider(provider_id)

    @property
    def session_repo(self):
        return self.handlers.session_repo

    @property
    def message_repo(self):
        return self.handlers.message_repo

    async def handle(self, websocket: WebSocket) -> None:
        self._ensure_event_bus_bridge()
        session_id = None
        ping_task = None
        try:

            async def _keepalive_ping():
                while True:
                    await asyncio.sleep(15)
                    try:
                        await websocket.send_text('{"jsonrpc":"2.0","method":"ping","params":{}}')
                    except Exception:
                        break

            ping_task = asyncio.ensure_future(_keepalive_ping())
            while True:
                raw = await websocket.receive_text()
                try:
                    data = json.loads(raw)
                    request = JsonRpcRequest(**data)
                    session_id = await self.handlers.dispatch(
                        websocket, request.method, request.id, request.params, session_id
                    )
                    if session_id:
                        await self.manager.register(session_id, websocket)
                except json.JSONDecodeError as e:
                    await websocket.send_text(make_error_response(0, -32700, f"Parse error: {e}"))
                except ValidationError as e:
                    await websocket.send_text(
                        make_error_response(0, -32600, f"Invalid request: {e}")
                    )
                except Exception as e:
                    logger.exception("Handler error")
                    rid_val = getattr(request, "id", 0) if "request" in locals() else 0
                    await websocket.send_text(make_error_response(rid_val or 0, -32603, str(e)))
        except WebSocketDisconnect:
            pass
        finally:
            if ping_task:
                ping_task.cancel()
            if session_id:
                self.manager.disconnect(session_id)
