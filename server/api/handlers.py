from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import WebSocket

import server.providers.responder as r
from server.config.constants import BUILD_MODE
from server.config.settings import AGENT_MODES
from server.domain.message import Message
from server.persistence.connection import Database
from server.persistence.repositories import MessageRepository, SessionRepository
from server.sessions.export import SessionExporter
from server.sessions.service import DefaultSessionService, SessionService
from server.skills.loader import SkillLoader
from server.toolkit.resolver import SchemaResolver, build_mode_tool_seed

from .protocol import make_error_response, make_response

if TYPE_CHECKING:
    from server.config.settings import AppSettings
    from server.providers.registry import ProviderRegistry
    from server.toolkit.registry import ToolRegistry

    from ..agents.prompt_executor import PromptExecutor
logger = logging.getLogger(__name__)


def _normalize_attachments(raw) -> list[dict]:
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    result: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        path = (item.get("path") or "").strip()
        if not path:
            continue
        if path in seen:
            continue
        seen.add(path)
        normalized = {"path": path}
        if item.get("name"):
            normalized["name"] = str(item["name"])
        if item.get("content") is not None:
            normalized["content"] = item["content"]
        result.append(normalized)
        if len(result) >= 25:
            break
    return result


class MethodHandlers:
    def __init__(
        self,
        config: AppSettings,
        db: Database,
        registry: ProviderRegistry,
        tool_registry: ToolRegistry,
        session_service: SessionService | None = None,
    ) -> None:
        self.config = config
        self.registry = registry
        self.tool_registry = tool_registry
        self.session_repo = SessionRepository(db)
        self.message_repo = MessageRepository(db)
        self.skill_loader = SkillLoader(config.workspace_root)
        self.exporter = SessionExporter()
        self.manager = None
        self._session_executors: dict[str, PromptExecutor] = {}
        self._session_service = session_service

    def reload_config(self) -> None:
        from server.config.loader import load_config
        from server.providers.registry import ProviderRegistry

        self.config = load_config()
        self.registry = ProviderRegistry.from_config(
            self.config.providers, self.config.active_provider
        )
        self.skill_loader = SkillLoader(self.config.workspace_root)

    async def dispatch(
        self, ws: WebSocket, method: str, rid, params: dict, session_id: str | None
    ) -> str | None:
        handlers = {
            "session.create": lambda: self._session_create(ws, rid, params),
            "session.list": lambda: self._session_list(ws, rid),
            "session.list_all": lambda: self._session_list_all(ws, rid, params),
            "session.summaries": lambda: self._session_summaries(ws, rid, params),
            "session.resume": lambda: self._session_resume(ws, rid, params),
            "session.update": lambda: self._session_update(ws, rid, params, session_id),
            "session.pause": lambda: self._session_pause(ws, rid, session_id),
            "session.archive": lambda: self._session_archive(ws, rid, session_id),
            "session.delete": lambda: self._session_delete(ws, rid, params),
            "session.checkpoint": lambda: self._session_checkpoint(ws, rid, session_id),
            "session.duplicate": lambda: self._session_duplicate(ws, rid, params),
            "session.restore": lambda: self._session_restore(ws, rid, params),
            "session.export": lambda: self._session_export(ws, rid, params, session_id),
            "session.sync": lambda: self._session_sync(ws, rid, params, session_id),
            "session.search": lambda: self._session_search(ws, rid, params, session_id),
            "prompt.send": lambda: self._prompt(ws, rid, params, session_id),
            "prompt.cancel": lambda: self._cancel_prompt(ws, rid, session_id),
            "context.compact": lambda: self._context_compact(ws, rid, session_id),
            "context.clear_tools": lambda: self._context_clear_tools(ws, rid, session_id),
            "provider.validate": lambda: self._provider_validate(ws, rid, params),
            "provider.models": lambda: self._provider_models(ws, rid, params),
            "tools.list": lambda: self._tools_list(ws, rid, params),
            "workspace.status": lambda: self._workspace_status(ws, rid),
            "workspace.diff": lambda: self._workspace_diff(ws, rid, params),
            "workspace.log": lambda: self._workspace_log(ws, rid, params),
            "workspace.repo_map": lambda: self._workspace_repo_map(ws, rid, params),
            "health": lambda: ws.send_text(make_response(rid, {"status": "ok"})),
        }
        handler = handlers.get(method)
        if handler:
            try:
                result = await handler()
                return result if isinstance(result, str) else session_id
            except Exception as e:
                logger.exception("Handler error for method '%s'", method)
                if rid is not None:
                    await ws.send_text(
                        make_error_response(
                            rid, -32603, f"Internal error executing {method}: {e!s}"
                        )
                    )
                return session_id
        await ws.send_text(make_error_response(rid, -32601, f"Method not found: {method}"))
        return session_id

    async def _session_create(self, ws, rid, params) -> str:
        svc = self._resolve_service()
        from server.domain.domain import ScenarioMode

        session = await svc.create(
            title=params.get("title", "New Session"),
            mode=params.get("mode", ScenarioMode.BUILD),
            provider=params.get("provider"),
            model=params.get("model"),
            workspace_root=params.get("workspace_root"),
        )
        if self.manager:
            await self.manager.schedule_session_event(
                session.id, "session.created", {"session_id": session.id, "title": session.title}
            )
        await ws.send_text(make_response(rid, session.model_dump(mode="json")))
        return session.id

    async def _session_list(self, ws, rid) -> None:
        svc = self._resolve_service()
        sessions = await svc.list_active()
        await ws.send_text(make_response(rid, [s.to_summary_dict() for s in sessions]))

    async def _session_list_all(self, ws, rid, params) -> None:
        svc = self._resolve_service()
        sessions = await svc.list_sessions(
            limit=params.get("limit", 50),
            offset=params.get("offset", 0),
            include_archived=params.get("include_archived", False),
            search=params.get("search"),
            state_filter=params.get("state_filter"),
        )
        await ws.send_text(make_response(rid, [s.to_summary_dict() for s in sessions]))

    async def _session_summaries(self, ws, rid, params) -> None:
        svc = self._resolve_service()
        summaries = await svc.list_summaries(
            limit=params.get("limit", 10), include_archived=params.get("include_archived", False)
        )
        await ws.send_text(make_response(rid, summaries))

    async def _session_resume(self, ws, rid, params) -> str | None:
        svc = self._resolve_service()
        sid = params.get("session_id", "")
        session = await svc.get(sid)
        if not session:
            await ws.send_text(make_error_response(rid, -32602, "Session not found"))
            return None
        try:
            session = await svc.resume(sid)
        except ValueError:
            pass
        messages = await svc.get_history(sid)
        replayed = 0
        if self.manager:
            await self.manager.register(sid, ws)
            replayed = await self.manager.replay_events(sid, ws)
        since = params.get("since_sequence", 0)
        sync_events = await svc.get_sync_events(sid, since_sequence=since)
        await ws.send_text(
            make_response(
                rid,
                {
                    "session": session.model_dump(mode="json"),
                    "messages": [m.model_dump(mode="json") for m in messages],
                    "events_replayed": replayed,
                    "sync_events": sync_events,
                    "latest_sequence": await svc.get_latest_sync_sequence(sid),
                },
            )
        )
        return sid

    async def _session_update(self, ws, rid, params, session_id) -> None:
        svc = self._resolve_service()
        target = params.get("session_id", session_id)
        if not target:
            await ws.send_text(make_error_response(rid, -32602, "No session_id provided"))
            return
        session = await svc.require(target)
        if "title" in params:
            session = await svc.update_title(target, params["title"])
        if "context_used" in params or "context_window" in params:
            used = params.get("context_used", session.context_used or 0)
            window = params.get("context_window", session.context_window or 0)
            session = await svc.update_context(target, used, window)
        if "tokens" in params or "cost" in params:
            tokens = params.get("tokens", 0)
            cost = params.get("cost", 0.0)
            session = await svc.add_tokens(target, tokens, cost)
        await ws.send_text(make_response(rid, session.model_dump(mode="json")))

    async def _session_pause(self, ws, rid, session_id) -> None:
        if not session_id:
            await ws.send_text(make_error_response(rid, -32602, "No active session"))
            return
        svc = self._resolve_service()
        session = await svc.pause(session_id)
        if self.manager:
            await self.manager.schedule_session_event(
                session_id, "session.paused", {"session_id": session_id}
            )
        await ws.send_text(make_response(rid, session.model_dump(mode="json")))

    async def _session_archive(self, ws, rid, session_id) -> None:
        if not session_id:
            await ws.send_text(make_error_response(rid, -32602, "No active session"))
            return
        svc = self._resolve_service()
        session = await svc.archive(session_id)
        await ws.send_text(make_response(rid, session.model_dump(mode="json")))

    async def _session_delete(self, ws, rid, params) -> None:
        sid = params.get("session_id", "")
        if not sid:
            await ws.send_text(make_error_response(rid, -32602, "No session_id provided"))
            return
        svc = self._resolve_service()
        await svc.delete(sid)
        if self.manager:
            self.manager.drop_buffer(sid)
        await ws.send_text(make_response(rid, {"status": "deleted"}))

    async def _session_checkpoint(self, ws, rid, session_id) -> None:
        if not session_id:
            await ws.send_text(make_error_response(rid, -32602, "No active session"))
            return
        svc = self._resolve_service()
        try:
            cid = await svc.checkpoint(session_id, checkpoint_type="manual")
            await ws.send_text(make_response(rid, {"checkpoint_id": cid}))
        except Exception as e:
            await ws.send_text(make_error_response(rid, -32603, f"Checkpoint failed: {e}"))

    async def _session_duplicate(self, ws, rid, params) -> None:
        sid = params.get("session_id", "")
        if not sid:
            await ws.send_text(make_error_response(rid, -32602, "No session_id provided"))
            return
        svc = self._resolve_service()
        try:
            new_session = await svc.duplicate(sid, new_title=params.get("title"))
            if self.manager:
                await self.manager.schedule_session_event(
                    new_session.id,
                    "session.duplicated",
                    {"session_id": new_session.id, "original_id": sid},
                )
            await ws.send_text(make_response(rid, new_session.model_dump(mode="json")))
        except Exception as e:
            await ws.send_text(make_error_response(rid, -32603, f"Duplicate failed: {e}"))

    async def _session_restore(self, ws, rid, params) -> None:
        sid = params.get("session_id", "")
        if not sid:
            await ws.send_text(make_error_response(rid, -32602, "No session_id provided"))
            return
        svc = self._resolve_service()
        try:
            session = await svc.restore_from_archive(sid)
            await ws.send_text(make_response(rid, session.model_dump(mode="json")))
        except Exception as e:
            await ws.send_text(make_error_response(rid, -32603, f"Restore failed: {e}"))

    async def _session_export(self, ws, rid, params, session_id) -> None:
        sid = params.get("session_id", session_id)
        if not sid:
            await ws.send_text(make_error_response(rid, -32602, "No active session"))
            return
        svc = self._resolve_service()
        try:
            markdown = await svc.export_markdown(sid)
            await ws.send_text(make_response(rid, {"markdown": markdown}))
        except Exception as e:
            await ws.send_text(make_error_response(rid, -32603, f"Export failed: {e}"))

    async def _session_sync(self, ws, rid, params, session_id) -> None:
        sid = params.get("session_id", session_id)
        if not sid:
            await ws.send_text(make_error_response(rid, -32602, "No session_id provided"))
            return
        svc = self._resolve_service()
        since = params.get("since_sequence", 0)
        events = await svc.get_sync_events(sid, since_sequence=since)
        latest = await svc.get_latest_sync_sequence(sid)
        await ws.send_text(make_response(rid, {"events": events, "latest_sequence": latest}))

    async def _session_search(self, ws, rid, params, session_id) -> None:
        from server.persistence.search import SearchRepository

        query = (params.get("query", "") or "").strip()
        if not query:
            await ws.send_text(make_error_response(rid, -32602, "query is required"))
            return
        sid = params.get("session_id", session_id)
        limit = int(params.get("limit", 20))
        repo = SearchRepository(self.session_repo.db)
        try:
            hits = await repo.search(query, limit=limit, session_id=sid)
            parity = await repo.index_parity()
        except Exception as e:
            logger.warning("Search failed: %s", e)
            await ws.send_text(make_error_response(rid, -32603, f"Search failed: {e}"))
            return
        await ws.send_text(
            make_response(
                rid, {"query": query, "hits": hits, "count": len(hits), "index_parity": parity}
            )
        )

    @staticmethod
    async def _validate_override_number(
        ws,
        rid,
        raw,
        *,
        convert,
        min_value,
        max_value,
        parse_error_msg,
        range_error_msg,
    ):
        """Validate a numeric prompt override (temperature / max_tokens).

        Returns ``(value, ok)``; when ``raw`` is None returns ``(None, True)``.
        On validation failure sends a JSON-RPC error and returns ``(None, False)``.
        """
        if raw is None:
            return None, True
        try:
            value = convert(raw)
        except (TypeError, ValueError):
            await ws.send_text(make_error_response(rid, -32602, parse_error_msg))
            return None, False
        if not min_value <= value <= max_value:
            await ws.send_text(make_error_response(rid, -32602, range_error_msg))
            return None, False
        return value, True

    async def _ensure_prompt_session(self, ws, rid, params, session_id, content) -> str | None:
        """Validate a prompt and resolve the session it should run against.

        Returns the session id to use, or None when the prompt was rejected
        (an error response has already been sent to the client).
        """
        if not content.strip():
            await ws.send_text(make_error_response(rid, -32602, "Empty prompt"))
            return None
        if not session_id:
            if params.get("mode") == BUILD_MODE:
                plan_session = await self.session_repo.find_latest_with_plan()
                if plan_session:
                    session_id = plan_session.id
                    logger.info(
                        "Reusing plan session %s for build (plan_output=%d chars)",
                        session_id,
                        len(plan_session.plan_output),
                    )
            if not session_id:
                svc = self._resolve_service()
                session = await svc.create(title=content[:50])
                session_id = session.id
        return session_id

    async def _resolve_provider_for_prompt(self, ws, rid, provider_name):
        """Resolve a provider, hot-reloading the config once if it is missing."""
        provider = self.registry.get(provider_name)
        if not provider:
            logger.warning(
                "Provider '%s' not in registry (available=%s), attempting hot-reload",
                provider_name,
                self.registry.list_providers(),
            )
            self.reload_config()
            provider = self.registry.get(provider_name)
        if not provider:
            available = list((self.config.providers or {}).keys())
            await ws.send_text(
                make_error_response(
                    rid,
                    -32602,
                    f"Provider '{provider_name}' not available. Configured: {available}",
                )
            )
            return None
        return provider

    async def _persist_model_override(self, session_id, model_override) -> None:
        try:
            session = await self.session_repo.get(session_id)
            if session:
                session.model = model_override
                session.metadata = dict(session.metadata or {})
                session.metadata["last_model"] = model_override
                await self.session_repo.update(session)
        except Exception:
            logger.warning("Failed to persist model override for session %s", session_id)

    async def _prompt(self, ws, rid, params, session_id) -> str | None:
        from ..agents.prompt_executor import PromptExecutor

        content = params.get("content", "") or params.get("prompt", "")
        provider_name = params.get("provider", "") or self.config.active_provider
        model_override = (params.get("model") or "").strip() or None
        temperature, ok = await self._validate_override_number(
            ws,
            rid,
            params.get("temperature"),
            convert=float,
            min_value=0,
            max_value=2,
            parse_error_msg="temperature must be a number in 0..2",
            range_error_msg="temperature must be in 0..2",
        )
        if not ok:
            return session_id
        max_tokens, ok = await self._validate_override_number(
            ws,
            rid,
            params.get("max_tokens"),
            convert=int,
            min_value=1,
            max_value=1_000_000_000,
            parse_error_msg="max_tokens must be an integer >= 1",
            range_error_msg="max_tokens must be an integer >= 1",
        )
        if not ok:
            return session_id
        attachments = _normalize_attachments(params.get("attachments"))
        logger.info(
            "PROMPT.RECEIVED provider=%s mode=%s session=%s content_len=%d model=%s temperature=%s max_tokens=%s attachments=%d content_preview=%r",
            provider_name,
            params.get("mode", BUILD_MODE),
            session_id,
            len(content),
            model_override,
            temperature,
            max_tokens,
            len(attachments),
            content[:200],
        )
        resolved_session = await self._ensure_prompt_session(ws, rid, params, session_id, content)
        if resolved_session is None:
            return session_id
        session_id = resolved_session
        user_msg = Message(session_id=session_id, role="user", content=content)
        if model_override:
            user_msg.metadata["model"] = model_override
        if attachments:
            user_msg.metadata["attachment_paths"] = [a["path"] for a in attachments]
        await self.message_repo.create(user_msg)
        provider = await self._resolve_provider_for_prompt(ws, rid, provider_name)
        if provider is None:
            return session_id
        model = model_override or getattr(provider, "model", "?")
        logger.info("PROMPT.RESOLVED provider=%s model=%s", provider_name, model)
        if model_override:
            await self._persist_model_override(session_id, model_override)
        await ws.send_text(make_response(rid, {"session_id": session_id, "status": "processing"}))
        try:
            executor = self._session_executors.get(session_id)
            if executor:
                executor.cancel_active()
            executor = PromptExecutor(
                self.config,
                provider,
                self.tool_registry,
                self.session_repo,
                self.message_repo,
                self.skill_loader,
            )
            self._session_executors[session_id] = executor
            executor.run(
                session_id,
                content,
                mode=params.get("mode", BUILD_MODE),
                handlers=self,
                manager=self.manager,
                model_override=model_override,
                temperature=temperature,
                max_tokens=max_tokens,
                attachments=attachments,
            )
        except Exception:
            logger.exception("Prompt execution failed for session %s", session_id)
        return session_id

    async def _cancel_prompt(self, ws, rid, session_id) -> str | None:
        if not session_id:
            await ws.send_text(make_response(rid, {"cancelled": False}))
            return None
        executor = self._session_executors.get(session_id)
        cancelled = bool(executor)
        if executor:
            executor.cancel_active()
            logger.info("Prompt cancel requested for session %s", session_id)
        await ws.send_text(make_response(rid, {"cancelled": cancelled}))
        return session_id

    async def _context_compact(self, ws, rid, session_id) -> str | None:
        if not session_id:
            await ws.send_text(make_error_response(rid, -32602, "No active session"))
            return None
        svc = self._resolve_service()
        provider = self.registry.get(self.config.active_provider)
        if not provider:
            await ws.send_text(make_error_response(rid, -32602, "No active provider configured"))
            return session_id
        session = await svc.require(session_id)
        history = await svc.get_history(session_id)
        model = getattr(provider, "model", "?")
        if self.manager:
            await self.manager.send_event(
                session_id, r.context_compaction_started(session_id, "manual")
            )
        try:
            from server.agents.summarizer import ConversationSummarizer

            previous = (session.metadata or {}).get("summary") or ""
            summary = await ConversationSummarizer(self.config, provider).summarize(
                history, model, session_id=session_id, previous_summary=previous
            )
            session.metadata["summary"] = summary
            await svc.update(session)
            await self.message_repo.delete_by_session(session_id)
            if self.manager:
                await self.manager.send_event(
                    session_id,
                    r.context_compaction_ended(
                        session_id, "manual", tokens_saved=0, summary_chars=len(summary)
                    ),
                )
            await ws.send_text(make_response(rid, {"summary": summary, "cleared": len(history)}))
        except Exception as e:
            logger.exception("Manual compact failed for session %s", session_id)
            await ws.send_text(make_error_response(rid, -32603, f"Compaction failed: {e}"))
        return session_id

    async def _context_clear_tools(self, ws, rid, session_id) -> None:
        if not session_id:
            await ws.send_text(make_error_response(rid, -32602, "No active session"))
            return
        try:
            removed_rows = await self.message_repo.delete_tool_results(session_id)
            stripped = await self.message_repo.strip_tool_events(session_id)
            total = removed_rows + stripped
            if self.manager and total > 0:
                await self.manager.send_event(
                    session_id,
                    r.warning(f"Cleared tool output from {total} message(s)", session_id),
                )
            await ws.send_text(
                make_response(rid, {"removed": total, "rows": removed_rows, "stripped": stripped})
            )
        except Exception as e:
            logger.exception("clear_tools failed for session %s", session_id)
            await ws.send_text(make_error_response(rid, -32603, f"clear_tools failed: {e}"))

    async def _provider_validate(self, ws, rid, params) -> None:
        provider = self.registry.get(params.get("provider", self.config.active_provider))
        valid = await provider.validate() if provider else False
        await ws.send_text(make_response(rid, {"valid": valid}))

    async def _provider_models(self, ws, rid, params) -> None:
        provider = self.registry.get(params.get("provider", self.config.active_provider))
        models = await provider.list_models() if provider else []
        await ws.send_text(make_response(rid, {"models": models}))

    async def _tools_list(self, ws, rid, params) -> None:
        mode = params.get("mode", BUILD_MODE)
        mode_config = AGENT_MODES.get(mode)
        allowed_mcp = mode_config.allowed_mcp if mode_config else None
        seed = build_mode_tool_seed(mode_config.allowed_tools if mode_config else None)
        resolver = SchemaResolver(self.tool_registry, seed=seed)
        await ws.send_text(
            make_response(rid, {"tools": resolver.schemas(mode, allowed_mcp=allowed_mcp)})
        )

    async def _workspace_status(self, ws, rid) -> None:
        from server.workspace.git import GitOps

        await ws.send_text(make_response(rid, GitOps(self.config.workspace_root).status()))

    async def _workspace_diff(self, ws, rid, params) -> None:
        from server.workspace.git import GitOps

        git = GitOps(self.config.workspace_root)
        diff = git.diff_staged() if params.get("staged", False) else git.diff(params.get("path"))
        await ws.send_text(make_response(rid, {"diff": diff}))

    async def _workspace_log(self, ws, rid, params) -> None:
        from server.workspace.git import GitOps

        log = GitOps(self.config.workspace_root).log(params.get("count", 10))
        await ws.send_text(make_response(rid, {"log": log}))

    async def _workspace_repo_map(self, ws, rid, params) -> None:
        from server.workspace.repo_map import RepoMap

        repo = RepoMap(self.config.workspace_root)
        await ws.send_text(
            make_response(
                rid,
                {
                    "structure": repo.get_structure(params.get("depth", 3)),
                    "summary": repo.get_summary(),
                    "keyFiles": repo.get_key_files(),
                },
            )
        )

    def _resolve_service(self) -> SessionService:
        if self._session_service is not None:
            return self._session_service
        return DefaultSessionService(session_repo=self.session_repo, message_repo=self.message_repo)
