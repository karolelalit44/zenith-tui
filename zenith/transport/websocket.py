"""WebSocket handler — dispatches JSON-RPC methods, manages connections."""

from __future__ import annotations

import json
import logging
from fastapi import WebSocket, WebSocketDisconnect

from .protocol import JsonRpcRequest, make_response, make_error_response, make_event
from zenith.core.session import Session
from zenith.core.message import Message
from zenith.core.events import Event, EventKind
from zenith.db.connection import Database
from zenith.db.repository import SessionRepository, MessageRepository
from zenith.providers.registry import ProviderRegistry
from zenith.tools.registry import ToolRegistry
from zenith.tools import create_default_registry
from zenith.agent.loop import AgentLoop
from zenith.agent.recovery import RecoverableAgentLoop
from zenith.agent.context import ContextManager
from zenith.skills.loader import SkillLoader
from zenith.session.export import SessionExporter
from zenith.config.settings import AppSettings

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self.connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        await websocket.accept()
        self.connections[session_id] = websocket
        logger.info("Client connected: %s", session_id)

    def register(self, session_id: str, websocket: WebSocket) -> None:
        self.connections[session_id] = websocket
        logger.info("Registered connection for session: %s", session_id)

    def disconnect(self, session_id: str) -> None:
        self.connections.pop(session_id, None)
        logger.info("Client disconnected: %s", session_id)

    async def send_event(self, session_id: str, event: Event) -> None:
        ws = self.connections.get(session_id)
        if ws:
            event.session_id = session_id
            event_text = make_event(event)
            data_preview = str(event.data)[:200] if event.data else ""
            logger.info(
                "WS SEND session=%s kind=%s data=%s",
                session_id, event.kind, data_preview,
            )
            await ws.send_text(event_text)
        else:
            logger.warning(
                "WS DROP session=%s kind=%s reason=no_connection",
                session_id, event.kind,
            )



class ZenithHandler:
    def __init__(
        self,
        config: AppSettings,
        db: Database,
        registry: ProviderRegistry,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self.config = config
        self.db = db
        self.registry = registry
        self.tool_registry = tool_registry or create_default_registry(
            timeout=config.tools.max_bash_timeout
        )
        self.session_repo = SessionRepository(db)
        self.message_repo = MessageRepository(db)
        self.manager = ConnectionManager()
        self.skill_loader = SkillLoader(config.workspace_root)
        self.exporter = SessionExporter()

    def _reload_config(self) -> None:
        """Reload configuration from SQLite database after setup wizard saves to zenith.db."""
        from zenith.config.loader import load_config  # noqa: F811
        from zenith.providers.registry import ProviderRegistry  # noqa: F811

        self.config = load_config()
        self.registry = ProviderRegistry.from_config(
            self.config.providers, self.config.active_provider
        )
        self.skill_loader = SkillLoader(self.config.workspace_root)
        logger.info(
            "Config reloaded: active_provider=%s, providers=%s",
            self.config.active_provider,
            list((self.config.providers or {}).keys()),
        )

    async def handle(self, websocket: WebSocket) -> None:
        session_id = None
        try:
            await websocket.accept()
            while True:
                raw = await websocket.receive_text()
                try:
                    data = json.loads(raw)
                    request = JsonRpcRequest(**data)
                    session_id = await self._dispatch(websocket, request, session_id)
                    if session_id:
                        self.manager.register(session_id, websocket)
                except json.JSONDecodeError as e:
                    await websocket.send_text(
                        make_error_response(0, -32700, f"Parse error: {e}")
                    )
                except Exception as e:
                    logger.exception("Handler error")
                    await websocket.send_text(
                        make_error_response(0, -32603, str(e))
                    )
        except WebSocketDisconnect:
            pass
        finally:
            if session_id:
                self.manager.disconnect(session_id)

    async def _dispatch(
        self,
        websocket: WebSocket,
        request: JsonRpcRequest,
        current_session_id: str | None,
    ) -> str | None:
        method = request.method
        params = request.params
        rid = request.id

        if method == "session.create":
            return await self._handle_session_create(websocket, rid, params)

        elif method == "session.list":
            await self._handle_session_list(websocket, rid)
            return current_session_id

        elif method == "session.resume":
            return await self._handle_session_resume(websocket, rid, params)

        elif method == "session.export":
            await self._handle_session_export(websocket, rid, params, current_session_id)
            return current_session_id

        elif method == "prompt.send":
            await self._handle_prompt(websocket, rid, params, current_session_id)
            return current_session_id

        elif method == "provider.validate":
            await self._handle_provider_validate(websocket, rid, params)
            return current_session_id

        elif method == "provider.models":
            await self._handle_provider_models(websocket, rid, params)
            return current_session_id

        elif method == "tools.list":
            await self._handle_tools_list(websocket, rid, params)
            return current_session_id

        elif method == "workspace.status":
            await self._handle_workspace_status(websocket, rid)
            return current_session_id

        elif method == "workspace.diff":
            await self._handle_workspace_diff(websocket, rid, params)
            return current_session_id

        elif method == "workspace.log":
            await self._handle_workspace_log(websocket, rid, params)
            return current_session_id

        elif method == "workspace.repo_map":
            await self._handle_workspace_repo_map(websocket, rid, params)
            return current_session_id

        elif method == "health":
            await websocket.send_text(make_response(rid, {"status": "ok"}))
            return current_session_id

        else:
            await websocket.send_text(
                make_error_response(rid, -32601, f"Method not found: {method}")
            )
            return current_session_id

    async def _handle_session_create(self, ws: WebSocket, rid, params) -> str:
        session = Session(title=params.get("title", "New Session"))
        await self.session_repo.create(session)
        await ws.send_text(make_response(rid, session.model_dump(mode="json")))
        return session.id

    async def _handle_session_list(self, ws: WebSocket, rid) -> None:
        sessions = await self.session_repo.list_active()
        await ws.send_text(
            make_response(rid, [s.model_dump(mode="json") for s in sessions])
        )

    async def _handle_session_resume(self, ws: WebSocket, rid, params) -> str | None:
        sid = params.get("session_id", "")
        session = await self.session_repo.get(sid)
        if not session:
            await ws.send_text(make_error_response(rid, -32602, "Session not found"))
            return None
        messages = await self.message_repo.get_by_session(sid)
        await ws.send_text(
            make_response(
                rid,
                {
                    "session": session.model_dump(mode="json"),
                    "messages": [m.model_dump(mode="json") for m in messages],
                },
            )
        )
        return sid

    async def _handle_session_export(self, ws: WebSocket, rid, params, session_id) -> None:
        if not session_id:
            await ws.send_text(make_error_response(rid, -32602, "No active session"))
            return

        session = await self.session_repo.get(session_id)
        if not session:
            await ws.send_text(make_error_response(rid, -32602, "Session not found"))
            return

        messages = await self.message_repo.get_by_session(session_id)
        output_dir = params.get("output_dir", "zenith_exports")

        try:
            filepath = self.exporter.export(session, messages, output_dir)
            markdown = self.exporter.export_to_string(session, messages)
            await ws.send_text(
                make_response(rid, {"filepath": filepath, "markdown": markdown})
            )
        except Exception as e:
            await ws.send_text(make_error_response(rid, -32603, f"Export failed: {e}"))

    async def _handle_prompt(
        self, ws: WebSocket, rid, params, session_id: str | None
    ) -> None:
        content = params.get("content", "")
        mode = params.get("mode", "build")

        if not content.strip():
            await ws.send_text(make_error_response(rid, -32602, "Empty prompt"))
            return

        if not session_id:
            session = Session(title=content[:50])
            await self.session_repo.create(session)
            session_id = session.id

        user_msg = Message(session_id=session_id, role="user", content=content)
        await self.message_repo.create(user_msg)

        provider_name = params.get("provider", self.config.active_provider)
        provider = self.registry.get(provider_name)
        if not provider:
            await ws.send_text(
                make_error_response(
                    rid, -32602, f"Provider '{provider_name}' not available"
                )
            )
            return

        await ws.send_text(
            make_response(rid, {"session_id": session_id, "status": "processing"})
        )

        history = await self.message_repo.get_by_session(session_id)
        context_manager = ContextManager(self.config)
        agent = RecoverableAgentLoop(
            self.config, provider, context_manager, self.tool_registry
        )

        skills_section = self.skill_loader.get_skill_prompt()

        collected_events: list[Event] = []
        response_text = ""

        try:
            async for event in agent.process_prompt(
                content, session_id, history, mode,
                skills_section=skills_section,
            ):
                collected_events.append(event)
                await self.manager.send_event(session_id, event)
                if event.kind == EventKind.MESSAGE and not event.data.get("partial"):
                    response_text += event.data.get("text", "")

        except Exception as e:
            error_event = Event(
                kind=EventKind.ERROR,
                data={"message": str(e)},
                session_id=session_id,
            )
            await self.manager.send_event(session_id, error_event)
            collected_events.append(error_event)

        assistant_msg = Message(
            session_id=session_id,
            role="assistant",
            content=response_text,
            events=collected_events,
        )
        await self.message_repo.create(assistant_msg)

    async def _handle_provider_validate(self, ws: WebSocket, rid, params) -> None:
        name = params.get("provider", self.config.active_provider)
        provider = self.registry.get(name)
        if not provider:
            await ws.send_text(
                make_response(rid, {"valid": False, "error": "Not registered"})
            )
            return
        valid = await provider.validate()
        await ws.send_text(make_response(rid, {"valid": valid}))

    async def _handle_provider_models(self, ws: WebSocket, rid, params) -> None:
        name = params.get("provider", self.config.active_provider)
        provider = self.registry.get(name)
        if not provider:
            await ws.send_text(make_response(rid, {"models": []}))
            return
        models = await provider.list_models()
        await ws.send_text(make_response(rid, {"models": models}))

    async def _handle_tools_list(self, ws: WebSocket, rid, params) -> None:
        mode = params.get("mode", "build")
        schemas = self.tool_registry.get_schemas_for_mode(mode)
        await ws.send_text(make_response(rid, {"tools": schemas}))

    async def _handle_workspace_status(self, ws: WebSocket, rid) -> None:
        from zenith.workspace.git import GitOps

        git = GitOps(self.config.workspace_root)
        status = git.status()
        await ws.send_text(make_response(rid, status))

    async def _handle_workspace_diff(self, ws: WebSocket, rid, params) -> None:
        from zenith.workspace.git import GitOps

        git = GitOps(self.config.workspace_root)
        file_path = params.get("path")
        staged = params.get("staged", False)

        if staged:
            diff = git.diff_staged()
        else:
            diff = git.diff(file_path)
        await ws.send_text(make_response(rid, {"diff": diff}))

    async def _handle_workspace_log(self, ws: WebSocket, rid, params) -> None:
        from zenith.workspace.git import GitOps

        git = GitOps(self.config.workspace_root)
        count = params.get("count", 10)
        log = git.log(count)
        await ws.send_text(make_response(rid, {"log": log}))

    async def _handle_workspace_repo_map(self, ws: WebSocket, rid, params) -> None:
        from zenith.workspace.repo_map import RepoMap

        repo = RepoMap(self.config.workspace_root)
        max_depth = params.get("depth", 3)
        structure = repo.get_structure(max_depth)
        summary = repo.get_summary()
        key_files = repo.get_key_files()
        await ws.send_text(
            make_response(rid, {
                "structure": structure,
                "summary": summary,
                "keyFiles": key_files,
            })
        )
