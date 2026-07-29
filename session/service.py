"""Session service — session CRUD, history management, and summarization.

Provides a clean service interface over the existing SessionRepository
and HistoryManager, adding:
- State machine transitions
- Message count tracking
- Export functionality
- Event-driven updates via EventBus
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from core.domain import ScenarioMode, SessionState
from core.errors import SessionNotFound
from core.events import EventBus, EventKind, make_event
from core.message import Message
from core.session import Session

logger = logging.getLogger(__name__)


class SessionService:
    """Abstract session service interface."""

    async def create(self, title: str | None = None, mode: ScenarioMode = ScenarioMode.BUILD) -> Session:
        ...

    async def get(self, session_id: str) -> Session | None:
        ...

    async def require(self, session_id: str) -> Session:
        ...

    async def list_active(self) -> list[Session]:
        ...

    async def add_message(self, session_id: str, message: Message) -> None:
        ...

    async def get_history(self, session_id: str, limit: int | None = None) -> list[Message]:
        ...

    async def get_message_count(self, session_id: str) -> int:
        ...

    async def get_token_count(self, session_id: str) -> int:
        ...

    async def update_title(self, session_id: str, title: str) -> Session:
        ...

    async def archive(self, session_id: str) -> Session:
        ...

    async def delete(self, session_id: str) -> None:
        ...

    async def export_markdown(self, session_id: str) -> str:
        ...


class DefaultSessionService(SessionService):
    """Session service backed by SQLite via SessionRepository."""

    def __init__(
        self,
        session_repo: Any,  # SessionRepository
        message_repo: Any,  # MessageRepository
        event_bus: EventBus | None = None,
    ) -> None:
        self._session_repo = session_repo
        self._message_repo = message_repo
        self._event_bus = event_bus

    async def create(
        self,
        title: str | None = None,
        mode: ScenarioMode = ScenarioMode.BUILD,
    ) -> Session:
        session = Session(
            title=title or "New Session",
            mode=mode,
            state=SessionState.CREATED,
        )
        await self._session_repo.create(session)
        logger.info("Created session %s: %s", session.id, session.title)

        if self._event_bus:
            self._event_bus.publish(make_event(
                EventKind.SESSION_CREATED,
                {"session_id": session.id, "title": session.title},
                session_id=session.id,
            ))

        return session

    async def get(self, session_id: str) -> Session | None:
        return await self._session_repo.get(session_id)

    async def require(self, session_id: str) -> Session:
        session = await self._session_repo.get(session_id)
        if session is None:
            raise SessionNotFound(session_id)
        return session

    async def list_active(self) -> list[Session]:
        return await self._session_repo.list_active()

    async def add_message(self, session_id: str, message: Message) -> None:
        await self._message_repo.create(message)

        # Update session state to ACTIVE if it was CREATED
        session = await self._session_repo.get(session_id)
        if session and session.state == SessionState.CREATED:
            session.transition(SessionState.ACTIVE)
            await self._session_repo.update(session)

    async def get_history(self, session_id: str, limit: int | None = None) -> list[Message]:
        if limit is not None:
            return await self._message_repo.get_by_session(session_id, limit=limit)
        return await self._message_repo.get_by_session(session_id)

    async def get_message_count(self, session_id: str) -> int:
        messages = await self._message_repo.get_by_session(session_id, limit=10000)
        return len(messages)

    async def get_token_count(self, session_id: str) -> int:
        return await self._message_repo.count_tokens(session_id)

    async def update_title(self, session_id: str, title: str) -> Session:
        session = await self.require(session_id)
        session.title = title
        session.updated_at = datetime.now()
        return await self._session_repo.update(session)

    async def archive(self, session_id: str) -> Session:
        session = await self.require(session_id)
        session.archive()
        return await self._session_repo.update(session)

    async def delete(self, session_id: str) -> None:
        await self._session_repo.delete(session_id)
        logger.info("Deleted session %s", session_id)

    async def export_markdown(self, session_id: str) -> str:
        from session.export import SessionExporter
        session = await self.require(session_id)
        messages = await self.get_history(session_id)
        exporter = SessionExporter()
        return exporter.export_to_string(session, messages)
