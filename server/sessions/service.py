from __future__ import annotations

import logging
import uuid as _uuid
from datetime import datetime
from typing import Any

from server.domain.enums import ScenarioMode
from server.domain.errors import SessionNotFound
from server.domain.events import EventBus, EventKind, make_event
from server.domain.message import Message
from server.domain.session import Session

logger = logging.getLogger(__name__)


def _snippet(text: str, needle: str, radius: int = 60) -> str:
    low = text.lower()
    idx = low.find(needle.lower())
    if idx < 0:
        preview = text[: radius * 2]
        return preview + ("..." if len(text) > len(preview) else "")
    start = max(0, idx - radius)
    end = min(len(text), idx + len(needle) + radius)
    prefix = "[" if start == 0 else "..."
    suffix = "]" if end == len(text) else "..."
    return f"{prefix}{text[start:end]}{suffix}"


class SessionService:
    async def create(
        self,
        title: str | None = None,
        mode: ScenarioMode = ScenarioMode.BUILD,
        provider: str | None = None,
        model: str | None = None,
        workspace_root: str | None = None,
        parent_session_id: str | None = None,
        metadata: dict | None = None,
    ) -> Session:
        raise NotImplementedError

    async def get(self, session_id: str) -> Session | None:
        raise NotImplementedError

    async def require(self, session_id: str) -> Session:
        raise NotImplementedError

    async def list_active(self) -> list[Session]:
        raise NotImplementedError

    async def list_sessions(
        self,
        limit: int = 50,
        offset: int = 0,
        include_archived: bool = False,
        search: str | None = None,
        state_filter: str | None = None,
    ) -> list[Session]:
        raise NotImplementedError

    async def list_summaries(self, limit: int = 10, include_archived: bool = False) -> list[dict]:
        raise NotImplementedError

    async def initialize(self, session_id: str) -> Session:
        raise NotImplementedError

    async def complete(self, session_id: str) -> Session:
        raise NotImplementedError

    async def pause(self, session_id: str) -> Session:
        raise NotImplementedError

    async def resume(self, session_id: str) -> Session:
        raise NotImplementedError

    async def add_message(self, session_id: str, message: Message) -> None:
        raise NotImplementedError

    async def get_history(self, session_id: str, limit: int | None = None) -> list[Message]:
        raise NotImplementedError

    async def search(
        self,
        query: str,
        session_id: str | None = None,
        limit: int = 20,
    ) -> tuple[list[dict], dict]:
        """Search session titles and message bodies for ``query``.

        Returns ``(hits, index_parity)`` where each hit is a dict with keys
        ``type`` (``session`` | ``message``), ``id``, ``session_id``, ``title``,
        ``created_at`` and ``snippet``.
        """
        raise NotImplementedError

    async def get_message_count(self, session_id: str) -> int:
        raise NotImplementedError

    async def get_token_count(self, session_id: str) -> int:
        raise NotImplementedError

    async def update_title(self, session_id: str, title: str) -> Session:
        raise NotImplementedError

    async def update(self, session: Session) -> Session:
        raise NotImplementedError

    async def update_context(self, session_id: str, used: int, window: int) -> Session:
        raise NotImplementedError

    async def add_tokens(self, session_id: str, tokens: int, cost: float = 0.0) -> Session:
        raise NotImplementedError

    async def record_error(self, session_id: str, error: str) -> Session:
        raise NotImplementedError

    async def checkpoint(self, session_id: str, checkpoint_type: str = "automatic") -> str:
        raise NotImplementedError

    async def restore_from_checkpoint(self, session_id: str) -> Session | None:
        raise NotImplementedError

    async def archive(self, session_id: str) -> Session:
        raise NotImplementedError

    async def delete(self, session_id: str) -> None:
        raise NotImplementedError

    async def duplicate(self, session_id: str, new_title: str | None = None) -> Session:
        raise NotImplementedError

    async def restore_from_archive(self, session_id: str) -> Session:
        raise NotImplementedError

    async def export_markdown(self, session_id: str) -> str:
        raise NotImplementedError

    async def create_draft(self, session_id: str, prompt: str = "", ttl_hours: int = 24) -> str:
        raise NotImplementedError

    async def promote_draft(self, session_id: str) -> Session:
        raise NotImplementedError

    async def get_status_history(self, session_id: str, limit: int = 50) -> list[dict]:
        raise NotImplementedError

    async def get_sync_events(self, session_id: str, since_sequence: int = 0) -> list[dict]:
        raise NotImplementedError

    async def get_latest_sync_sequence(self, session_id: str) -> int:
        raise NotImplementedError

    async def record_sync_event(
        self, session_id: str, event_type: str, event_data: dict, sequence: int | None = None
    ) -> str:
        raise NotImplementedError


class DefaultSessionService(SessionService):
    def __init__(
        self,
        session_repo: Any,
        message_repo: Any,
        checkpoint_repo: Any | None = None,
        sync_event_repo: Any | None = None,
        status_history_repo: Any | None = None,
        draft_repo: Any | None = None,
        event_bus: EventBus | None = None,
        hooks: Any | None = None,
    ) -> None:
        self._session_repo = session_repo
        self._message_repo = message_repo
        self._checkpoint_repo = checkpoint_repo
        self._sync_event_repo = sync_event_repo
        self._status_history_repo = status_history_repo
        self._draft_repo = draft_repo
        self._event_bus = event_bus
        from server.domain.hooks import HookRunner

        self._hook_runner = HookRunner(hooks) if hooks is not None else None

    def _publish(self, kind: EventKind, data: dict, session_id: str | None = None) -> None:
        if self._event_bus:
            self._event_bus.publish(make_event(kind, data, session_id=session_id))

    async def create(
        self,
        title: str | None = None,
        mode: ScenarioMode = ScenarioMode.BUILD,
        provider: str | None = None,
        model: str | None = None,
        workspace_root: str | None = None,
        parent_session_id: str | None = None,
        metadata: dict | None = None,
    ) -> Session:
        session = Session(
            title=title or "New Session",
            mode=mode,
            provider=provider,
            model=model,
            workspace_root=workspace_root or ".",
            metadata=metadata or {},
            parent_session_id=parent_session_id,
        )
        await self._session_repo.create(session)
        self._publish(
            EventKind.SESSION_CREATED,
            {
                "session_id": session.id,
                "title": session.title,
                "mode": session.mode.value if hasattr(session.mode, "value") else session.mode,
            },
            session_id=session.id,
        )
        logger.info("Created session %s: %s", session.id, session.title)
        await self._run_session_start(session)
        return session

    async def _run_session_start(self, session: Session) -> None:
        runner = getattr(self, "_hook_runner", None)
        if runner is None or not runner.enabled:
            return
        try:
            results = await runner.run_session_start(
                session.id,
                title=session.title,
                mode=session.mode.value if hasattr(session.mode, "value") else str(session.mode),
                provider=session.provider or "",
                workspace_root=session.workspace_root or ".",
            )
            for r in results:
                if r["exit_code"] != 0:
                    logger.warning(
                        "SessionStart hook '%s' failed (exit %s): %s",
                        r["command"],
                        r["exit_code"],
                        r["stderr"],
                    )
        except Exception as e:
            logger.warning("SessionStart hook error for '%s': %s", session.id, e)

    async def get(self, session_id: str) -> Session | None:
        return await self._session_repo.get(session_id)

    async def update(self, session: Session) -> Session:
        return await self._session_repo.update(session)

    async def require(self, session_id: str) -> Session:
        session = await self._session_repo.get(session_id)
        if session is None:
            raise SessionNotFound(session_id)
        return session

    async def list_active(self) -> list[Session]:
        return await self._session_repo.list_active()

    async def list_sessions(
        self,
        limit: int = 50,
        offset: int = 0,
        include_archived: bool = False,
        search: str | None = None,
        state_filter: str | None = None,
    ) -> list[Session]:
        return await self._session_repo.list_all(
            limit=limit,
            offset=offset,
            include_archived=include_archived,
            search=search,
            state_filter=state_filter,
        )

    async def list_summaries(self, limit: int = 10, include_archived: bool = False) -> list[dict]:
        return await self._session_repo.get_summaries(
            limit=limit, include_archived=include_archived
        )

    async def initialize(self, session_id: str) -> Session:
        session = await self.require(session_id)
        session.mark_busy()
        return await self._session_repo.update(session)

    async def complete(self, session_id: str) -> Session:
        session = await self.require(session_id)
        session.mark_idle()
        return await self._session_repo.update(session)

    async def pause(self, session_id: str) -> Session:
        session = await self.require(session_id)
        session.mark_idle()
        result = await self._session_repo.update(session)
        self._publish(EventKind.SESSION_PAUSED, {"session_id": session_id}, session_id=session_id)
        return result

    async def resume(self, session_id: str) -> Session:
        session = await self.require(session_id)
        session.mark_busy()
        result = await self._session_repo.update(session)
        self._publish(EventKind.SESSION_RESUMED, {"session_id": session_id}, session_id=session_id)
        return result

    async def add_message(self, session_id: str, message: Message) -> None:
        await self._message_repo.create(message)
        session = await self._session_repo.get(session_id)
        if session:
            session.message_count += 1
            session.mark_busy()
            await self._session_repo.update(session)

    async def get_history(self, session_id: str, limit: int | None = None) -> list[Message]:
        if limit is not None:
            return await self._message_repo.get_by_session(session_id, limit=limit)
        return await self._message_repo.get_by_session(session_id)

    async def search(
        self,
        query: str,
        session_id: str | None = None,
        limit: int = 20,
    ) -> tuple[list[dict], dict]:
        """Search session titles and message bodies for ``query``.

        Returns ``(hits, index_parity)`` where each hit is a dict with keys
        ``type`` (``session`` | ``message``), ``id``, ``session_id``, ``title``,
        ``created_at`` and ``snippet`` (messages also include ``role``).
        """
        needle = query.lower()
        hits: list[dict] = []
        sessions = await self._session_repo.list_all(limit=10_000, include_archived=True)
        if session_id:
            sessions = [session for session in sessions if session.id == session_id]
        total_messages = 0
        for session in sessions:
            title = session.title or ""
            if needle in title.lower():
                hits.append(
                    {
                        "type": "session",
                        "id": session.id,
                        "session_id": session.id,
                        "title": title,
                        "created_at": session.created_at.isoformat(),
                        "snippet": _snippet(title, needle),
                    }
                )
                if len(hits) >= limit:
                    break
            messages = await self._message_repo.get_by_session(session.id, limit=0)
            total_messages += len(messages)
            for message in messages:
                content = message.content or ""
                if needle not in content.lower():
                    continue
                hits.append(
                    {
                        "type": "message",
                        "id": message.id,
                        "session_id": session.id,
                        "title": title,
                        "role": message.role,
                        "created_at": message.created_at.isoformat(),
                        "snippet": _snippet(content, needle),
                    }
                )
                if len(hits) >= limit:
                    break
            if len(hits) >= limit:
                break
        parity = {"mode": "session-scan", "messages": total_messages, "sessions": len(sessions)}
        return hits, parity

    async def get_message_count(self, session_id: str) -> int:
        session = await self.require(session_id)
        return session.message_count

    async def get_token_count(self, session_id: str) -> int:
        return await self._message_repo.count_tokens(session_id)

    async def update_title(self, session_id: str, title: str) -> Session:
        session = await self.require(session_id)
        session.title = title
        session.updated_at = datetime.now()
        result = await self._session_repo.update(session)
        self._publish(
            EventKind.SESSION_RENAMED,
            {"session_id": session_id, "title": title},
            session_id=session_id,
        )
        return result

    async def update_context(self, session_id: str, used: int, window: int) -> Session:
        session = await self.require(session_id)
        session.update_context(used, window)
        result = await self._session_repo.update(session)
        self._publish(
            EventKind.CONTEXT_UPDATED,
            {
                "session_id": session_id,
                "context_used": used,
                "context_window": window,
                "context_percent": session.context_percent,
            },
            session_id=session_id,
        )
        return result

    async def add_tokens(self, session_id: str, tokens: int, cost: float = 0.0) -> Session:
        session = await self.require(session_id)
        session.add_tokens(tokens, cost)
        result = await self._session_repo.update(session)
        self._publish(
            EventKind.TOKEN_USAGE_RECORDED,
            {
                "session_id": session_id,
                "total_tokens": session.total_tokens,
                "total_cost": session.total_cost,
                "added_tokens": tokens,
                "added_cost": cost,
            },
            session_id=session_id,
        )
        return result

    async def record_error(self, session_id: str, error: str) -> Session:
        session = await self.require(session_id)
        session.error_count += 1
        session.last_error = error
        session.mark_idle()
        result = await self._session_repo.update(session)
        self._publish(
            EventKind.SESSION_ERROR,
            {"session_id": session_id, "error": error, "error_count": session.error_count},
            session_id=session_id,
        )
        return result

    async def checkpoint(self, session_id: str, checkpoint_type: str = "automatic") -> str:
        session = await self.require(session_id)
        if self._checkpoint_repo is None:
            raise RuntimeError("Checkpoint repository not available")
        cid = await self._checkpoint_repo.create(
            session_id=session_id,
            checkpoint_type=checkpoint_type,
            step_index=session.message_count,
            snapshot_data=session.model_dump_for_db(),
            token_count=session.total_tokens,
            message_count=session.message_count,
        )
        self._publish(
            EventKind.SESSION_CHECKPOINT_CREATED,
            {"session_id": session_id, "checkpoint_id": cid, "checkpoint_type": checkpoint_type},
            session_id=session_id,
        )
        return cid

    async def restore_from_checkpoint(self, session_id: str) -> Session | None:
        if self._checkpoint_repo is None:
            raise RuntimeError("Checkpoint repository not available")
        checkpoint = await self._checkpoint_repo.get_latest(session_id)
        if not checkpoint:
            return None
        snapshot = checkpoint["snapshot_data"]
        session = Session(**snapshot)
        session.mark_idle()
        await self._session_repo.update(session)
        self._publish(
            EventKind.SESSION_RESTORED,
            {"session_id": session_id, "checkpoint_id": checkpoint["id"]},
            session_id=session_id,
        )
        return session

    async def archive(self, session_id: str) -> Session:
        session = await self.require(session_id)
        session.archive()
        result = await self._session_repo.update(session)
        self._publish(EventKind.SESSION_ARCHIVED, {"session_id": session_id}, session_id=session_id)
        return result

    async def delete(self, session_id: str) -> None:
        await self._session_repo.delete(session_id)
        self._publish(EventKind.SESSION_DELETED, {"session_id": session_id}, session_id=session_id)

    async def duplicate(self, session_id: str, new_title: str | None = None) -> Session:
        original = await self.require(session_id)
        new_session = Session(
            title=new_title or f"{original.title} (copy)",
            mode=original.mode,
            provider=original.provider,
            model=original.model,
            workspace_root=original.workspace_root,
            metadata=original.metadata,
            parent_session_id=original.parent_session_id,
        )
        await self._session_repo.create(new_session)
        messages = await self.get_history(session_id)
        for msg in messages:
            msg.id = str(_uuid.uuid4())
            msg.session_id = new_session.id
            msg.created_at = datetime.now()
            await self._message_repo.create(msg)
        if self._status_history_repo:
            await self._status_history_repo.record(
                new_session.id, None, "created", f"Duplicated from {session_id}"
            )
        self._publish(
            EventKind.SESSION_DUPLICATED,
            {"session_id": new_session.id, "original_id": session_id},
            session_id=new_session.id,
        )
        return new_session

    async def restore_from_archive(self, session_id: str) -> Session:
        session = await self.require(session_id)
        session.is_active = True
        session.mark_idle()
        result = await self._session_repo.update(session)
        self._publish(EventKind.SESSION_RESTORED, {"session_id": session_id}, session_id=session_id)
        return result

    async def export_markdown(self, session_id: str) -> str:
        from server.sessions.export import SessionExporter

        session = await self.require(session_id)
        messages = await self.get_history(session_id)
        exporter = SessionExporter()
        result = exporter.export_to_string(session, messages)
        session.export_format = "markdown"
        session.exported_at = datetime.now()
        await self._session_repo.update(session)
        self._publish(
            EventKind.SESSION_EXPORTED,
            {"session_id": session_id, "format": "markdown"},
            session_id=session_id,
        )
        return result

    async def create_draft(self, session_id: str, prompt: str = "", ttl_hours: int = 24) -> str:
        if self._draft_repo is None:
            raise RuntimeError("Draft repository not available")
        did = await self._draft_repo.save(session_id, prompt=prompt, ttl_hours=ttl_hours)
        return did

    async def promote_draft(self, session_id: str) -> Session:
        session = await self.require(session_id)
        session.mark_busy()
        return await self._session_repo.update(session)

    async def get_status_history(self, session_id: str, limit: int = 50) -> list[dict]:
        if self._status_history_repo is None:
            return []
        return await self._status_history_repo.get_history(session_id, limit=limit)

    async def get_sync_events(self, session_id: str, since_sequence: int = 0) -> list[dict]:
        if self._sync_event_repo is None:
            return []
        return await self._sync_event_repo.get_since(session_id, sequence=since_sequence)

    async def get_latest_sync_sequence(self, session_id: str) -> int:
        if self._sync_event_repo is None:
            return 0
        return await self._sync_event_repo.get_latest_sequence(session_id)

    async def record_sync_event(
        self, session_id: str, event_type: str, event_data: dict, sequence: int | None = None
    ) -> str:
        if self._sync_event_repo is None:
            raise RuntimeError("Sync event repository not available")
        return await self._sync_event_repo.record(
            session_id, event_type, event_data, sequence=sequence
        )
