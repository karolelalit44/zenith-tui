"""WebSocket handler — dispatches JSON-RPC methods, manages connections."""

from __future__ import annotations

import asyncio
import json
import logging
from fastapi import WebSocket, WebSocketDisconnect

from .protocol import (
    JsonRpcRequest, Connection, TransportService,
    make_response, make_error_response, make_event,
)
from core.events import Event
from db.connection import Database
from providers.registry import ProviderRegistry
from tools.registry import ToolRegistry
from tools import create_default_registry
from config.settings import AppSettings
from .handlers import MethodHandlers
from .prompt import PromptExecutor

logger = logging.getLogger(__name__)


class ConnectionManager(TransportService):
    """WebSocket connection manager implementing TransportService."""

    def __init__(self) -> None:
        self.connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        await websocket.accept()
        self.connections[session_id] = websocket
        logger.info("Client connected: %s", session_id)

    def register(self, session_id: str, websocket: WebSocket) -> None:
        self.connections[session_id] = websocket

    def disconnect(self, session_id: str) -> None:
        self.connections.pop(session_id, None)
        logger.info("Client disconnected: %s", session_id)

    def get_connections(self) -> list[Connection]:
        return [Connection(session_id=sid, client=str(ws.client)) for sid, ws in self.connections.items()]

    async def start(self, host: str, port: int) -> None:
        pass

    async def stop(self) -> None:
        for sid in list(self.connections):
            self.disconnect(sid)

    async def broadcast(self, event: Event) -> None:
        for sid in list(self.connections):
            await self.send_event(sid, event)

    async def send_event(self, session_id: str, event: Event) -> None:
        ws = self.connections.get(session_id)
        if ws:
            event.session_id = session_id
            try:
                await ws.send_text(make_event(event))
            except Exception as exc:
                logger.warning("WS SEND FAIL session=%s kind=%s: %s", session_id, event.kind, exc)
        else:
            logger.warning("WS DROP session=%s kind=%s reason=no_connection", session_id, event.kind)


class ZenithHandler:
    def __init__(
        self,
        config: AppSettings,
        db: Database,
        registry: ProviderRegistry,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self.config = config
        self.tool_registry = tool_registry or create_default_registry(
            timeout=config.tools.max_bash_timeout,
            provider=registry.get(config.active_provider),
        )
        self.manager = ConnectionManager()
        self.handlers = MethodHandlers(config, db, registry, self.tool_registry)
        self._executor = PromptExecutor(
            config, registry.get(config.active_provider), self.tool_registry,
            self.handlers.session_repo, self.handlers.message_repo, self.handlers.skill_loader,
        )
        self.handlers.manager = self.manager
        self.handlers._shared_executor = self._executor

    def _reload_config(self) -> None:
        self.handlers.reload_config()
        self._executor = PromptExecutor(
            self.handlers.config, self.handlers.registry.get(self.handlers.config.active_provider),
            self.tool_registry, self.handlers.session_repo, self.handlers.message_repo, self.handlers.skill_loader,
        )
        self.handlers._shared_executor = self._executor

    @property
    def session_repo(self):
        return self.handlers.session_repo

    @property
    def message_repo(self):
        return self.handlers.message_repo

    async def handle(self, websocket: WebSocket) -> None:
        session_id = None
        ping_task = None
        try:
            async def _keepalive_ping():
                """Send WS pings every 30s to prevent idle connection drops."""
                while True:
                    await asyncio.sleep(30)
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
                    session_id = await self.handlers.dispatch(websocket, request.method, request.id, request.params, session_id)
                    if session_id:
                        self.manager.register(session_id, websocket)
                except json.JSONDecodeError as e:
                    await websocket.send_text(make_error_response(0, -32700, f"Parse error: {e}"))
                except Exception as e:
                    logger.exception("Handler error")
                    await websocket.send_text(make_error_response(0, -32603, str(e)))
        except WebSocketDisconnect:
            pass
        finally:
            if ping_task:
                ping_task.cancel()
            if session_id:
                self.manager.disconnect(session_id)
            self._executor.cancel_active()
