"""Protocol handlers — JSON-RPC method implementations."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING

from fastapi import WebSocket

from core.events import Event, EventKind
from core.message import Message
from core.session import Session
from db.connection import Database
from db.repository import MessageRepository, SessionRepository
from session.export import SessionExporter
from skills.loader import SkillLoader

from .protocol import make_error_response, make_response

if TYPE_CHECKING:
    from config.settings import AppSettings
    from providers.registry import ProviderRegistry
    from tools.registry import ToolRegistry

    from .prompt import PromptExecutor

logger = logging.getLogger(__name__)


class MethodHandlers:
    """Dispatches JSON-RPC methods to handler functions."""

    def __init__(
        self,
        config: AppSettings,
        db: Database,
        registry: ProviderRegistry,
        tool_registry: ToolRegistry,
    ) -> None:
        self.config = config
        self.registry = registry
        self.tool_registry = tool_registry
        self.session_repo = SessionRepository(db)
        self.message_repo = MessageRepository(db)
        self.skill_loader = SkillLoader(config.workspace_root)
        self.exporter = SessionExporter()
        self._pending_confirmations: dict[str, asyncio.Future[bool]] = {}
        self.manager = None
        self._shared_executor = None
        self._session_executors: dict[str, PromptExecutor] = {}

    def reload_config(self) -> None:
        from config.loader import load_config
        from providers.registry import ProviderRegistry
        self.config = load_config()
        self.registry = ProviderRegistry.from_config(self.config.providers, self.config.active_provider)
        self.skill_loader = SkillLoader(self.config.workspace_root)

    async def dispatch(self, ws: WebSocket, method: str, rid, params: dict, session_id: str | None) -> str | None:
        handlers = {
            "session.create": lambda: self._session_create(ws, rid, params),
            "session.list": lambda: self._session_list(ws, rid),
            "session.resume": lambda: self._session_resume(ws, rid, params),
            "session.export": lambda: self._session_export(ws, rid, params, session_id),
            "prompt.send": lambda: self._prompt(ws, rid, params, session_id),
            "provider.validate": lambda: self._provider_validate(ws, rid, params),
            "provider.models": lambda: self._provider_models(ws, rid, params),
            "tools.list": lambda: self._tools_list(ws, rid, params),
            "workspace.status": lambda: self._workspace_status(ws, rid),
            "workspace.diff": lambda: self._workspace_diff(ws, rid, params),
            "workspace.log": lambda: self._workspace_log(ws, rid, params),
            "workspace.repo_map": lambda: self._workspace_repo_map(ws, rid, params),
            "health": lambda: ws.send_text(make_response(rid, {"status": "ok"})),
            "confirmation.response": lambda: self._confirmation_response(params),
            "plan.approve": lambda: self._plan_approve(ws, rid, session_id),
            "plan.reject": lambda: self._plan_reject(ws, rid, session_id),
        }
        handler = handlers.get(method)
        if handler:
            result = await handler()
            return result if isinstance(result, str) else session_id
        await ws.send_text(make_error_response(rid, -32601, f"Method not found: {method}"))
        return session_id

    async def _session_create(self, ws, rid, params) -> str:
        session = Session(title=params.get("title", "New Session"))
        await self.session_repo.create(session)
        await ws.send_text(make_response(rid, session.model_dump(mode="json")))
        return session.id

    async def _session_list(self, ws, rid) -> None:
        sessions = await self.session_repo.list_active()
        await ws.send_text(make_response(rid, [s.model_dump(mode="json") for s in sessions]))

    async def _session_resume(self, ws, rid, params) -> str | None:
        sid = params.get("session_id", "")
        session = await self.session_repo.get(sid)
        if not session:
            await ws.send_text(make_error_response(rid, -32602, "Session not found"))
            return None
        messages = await self.message_repo.get_by_session(sid)
        replayed = 0
        if self.manager:
            self.manager.register(sid, ws)
            replayed = await self.manager.replay_events(sid, ws)
        await ws.send_text(make_response(rid, {
            "session": session.model_dump(mode="json"),
            "messages": [m.model_dump(mode="json") for m in messages],
            "events_replayed": replayed,
        }))
        return sid

    async def _session_export(self, ws, rid, params, session_id) -> None:
        if not session_id:
            await ws.send_text(make_error_response(rid, -32602, "No active session"))
            return
        session = await self.session_repo.get(session_id)
        if not session:
            await ws.send_text(make_error_response(rid, -32602, "Session not found"))
            return
        messages = await self.message_repo.get_by_session(session_id)
        try:
            filepath = self.exporter.export(session, messages, params.get("output_dir", "zenith_exports"))
            markdown = self.exporter.export_to_string(session, messages)
            await ws.send_text(make_response(rid, {"filepath": filepath, "markdown": markdown}))
        except Exception as e:
            await ws.send_text(make_error_response(rid, -32603, f"Export failed: {e}"))

    async def _prompt(self, ws, rid, params, session_id) -> str | None:
        from .prompt import PromptExecutor
        content = params.get("content", "") or params.get("prompt", "")
        provider_name = params.get("provider", "") or self.config.active_provider
        logger.info(
            "PROMPT.RECEIVED provider=%s mode=%s session=%s content_len=%d content_preview=%r",
            provider_name, params.get("mode", "build"), session_id, len(content), content[:200],
        )
        if not content.strip():
            await ws.send_text(make_error_response(rid, -32602, "Empty prompt"))
            return session_id
        if not session_id:
            # If build mode with no session, try to find latest session with a plan
            if params.get("mode") == "build":
                plan_session = await self.session_repo.find_latest_with_plan()
                if plan_session:
                    session_id = plan_session.id
                    logger.info("Reusing plan session %s for build (plan_output=%d chars)",
                                session_id, len(plan_session.plan_output))
            if not session_id:
                session = Session(title=content[:50])
                await self.session_repo.create(session)
                session_id = session.id
        user_msg = Message(session_id=session_id, role="user", content=content)
        await self.message_repo.create(user_msg)

        provider = self.registry.get(provider_name)
        if not provider:
            logger.warning(
                "Provider '%s' not in registry (available=%s), attempting hot-reload",
                provider_name, self.registry.list_providers(),
            )
            self.reload_config()
            provider = self.registry.get(provider_name)

        if not provider:
            available = list((self.config.providers or {}).keys())
            await ws.send_text(make_error_response(
                rid, -32602,
                f"Provider '{provider_name}' not available. Configured: {available}",
            ))
            return session_id

        model = getattr(provider, 'model', '?')
        logger.info("PROMPT.RESOLVED provider=%s model=%s", provider_name, model)

        await ws.send_text(make_response(rid, {"session_id": session_id, "status": "processing"}))

        try:
            executor = self._session_executors.get(session_id)
            if executor:
                executor.cancel_active()
            executor = PromptExecutor(self.config, provider, self.tool_registry, self.session_repo, self.message_repo, self.skill_loader)
            self._session_executors[session_id] = executor
            executor.run(
                session_id, content,
                mode=params.get("mode", "build"),
                handlers=self,
                manager=self.manager,
            )
        except Exception:
            logger.exception("Prompt execution failed for session %s", session_id)
        return session_id

    async def _provider_validate(self, ws, rid, params) -> None:
        provider = self.registry.get(params.get("provider", self.config.active_provider))
        valid = await provider.validate() if provider else False
        await ws.send_text(make_response(rid, {"valid": valid}))

    async def _provider_models(self, ws, rid, params) -> None:
        provider = self.registry.get(params.get("provider", self.config.active_provider))
        models = await provider.list_models() if provider else []
        await ws.send_text(make_response(rid, {"models": models}))

    async def _tools_list(self, ws, rid, params) -> None:
        schemas = self.tool_registry.get_schemas_for_mode(params.get("mode", "build"))
        await ws.send_text(make_response(rid, {"tools": schemas}))

    async def _workspace_status(self, ws, rid) -> None:
        from workspace.git import GitOps
        await ws.send_text(make_response(rid, GitOps(self.config.workspace_root).status()))

    async def _workspace_diff(self, ws, rid, params) -> None:
        from workspace.git import GitOps
        git = GitOps(self.config.workspace_root)
        diff = git.diff_staged() if params.get("staged", False) else git.diff(params.get("path"))
        await ws.send_text(make_response(rid, {"diff": diff}))

    async def _workspace_log(self, ws, rid, params) -> None:
        from workspace.git import GitOps
        log = GitOps(self.config.workspace_root).log(params.get("count", 10))
        await ws.send_text(make_response(rid, {"log": log}))

    async def _workspace_repo_map(self, ws, rid, params) -> None:
        from workspace.repo_map import RepoMap
        repo = RepoMap(self.config.workspace_root)
        await ws.send_text(make_response(rid, {
            "structure": repo.get_structure(params.get("depth", 3)),
            "summary": repo.get_summary(),
            "keyFiles": repo.get_key_files(),
        }))

    async def _confirmation_response(self, params) -> None:
        confirmation_id = params.get("confirmation_id", "")
        future = self._pending_confirmations.pop(confirmation_id, None)
        if future and not future.done():
            future.set_result(params.get("approved", False))

    async def _plan_approve(self, ws, rid, session_id: str | None) -> None:
        if not session_id:
            await ws.send_text(make_error_response(rid, -32602, "No active session"))
            return
        session = await self.session_repo.get(session_id)
        if not session:
            await ws.send_text(make_error_response(rid, -32602, "Session not found"))
            return
        if not session.plan_output:
            await ws.send_text(make_error_response(rid, -32602, "No plan to approve"))
            return
        from datetime import datetime
        session.plan_approved_at = datetime.now()
        session.state = "approved"
        await self.session_repo.update(session)
        logger.info("Plan approved for session %s", session_id)
        await ws.send_text(make_response(rid, {"status": "approved"}))

    async def _plan_reject(self, ws, rid, session_id: str | None) -> None:
        if not session_id:
            await ws.send_text(make_error_response(rid, -32602, "No active session"))
            return
        session = await self.session_repo.get(session_id)
        if not session:
            await ws.send_text(make_error_response(rid, -32602, "Session not found"))
            return
        if not session.plan_output:
            await ws.send_text(make_error_response(rid, -32602, "No plan to reject"))
            return
        session.plan_output = ""
        session.plan_approved_at = None
        session.state = "active"
        await self.session_repo.update(session)
        logger.info("Plan rejected for session %s", session_id)
        await ws.send_text(make_response(rid, {"status": "rejected"}))

    async def request_confirmation(self, session_id: str, tool_name: str, reason: str, risk_level: str, manager) -> bool:
        confirmation_id = f"confirm_{uuid.uuid4().hex[:8]}"
        future: asyncio.Future[bool] = asyncio.get_event_loop().create_future()
        self._pending_confirmations[confirmation_id] = future
        event = Event(
            kind=EventKind.CONFIRMATION_REQUEST,
            data={"confirmation_id": confirmation_id, "tool": tool_name, "reason": reason, "risk_level": risk_level,
                  "message": f"Tool '{tool_name}' wants to execute a {risk_level}-risk operation: {reason}"},
            session_id=session_id,
        )
        await manager.send_event(session_id, event)
        try:
            return await asyncio.wait_for(future, timeout=120)
        except TimeoutError:
            self._pending_confirmations.pop(confirmation_id, None)
            return False
