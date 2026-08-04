
from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any
from server.domain.domain import AgentRole, ScenarioMode
from server.domain.events import Event
from server.domain.message import Message
from server.domain.session import Session
from server.sessions.service import SessionService
from .runtime import AgentRuntime

logger = logging.getLogger(__name__)


class CoordinatorService(ABC):

    @abstractmethod
    async def create_session(self, title: str | None = None) -> Session: ...

    @abstractmethod
    async def list_sessions(self) -> list[Session]: ...

    @abstractmethod
    async def resume_session(self, session_id: str) -> Session: ...

    @abstractmethod
    async def handle_prompt(self, session_id: str, prompt: str, mode: ScenarioMode, role: AgentRole = AgentRole.CODER, plan_context: str = "") -> AsyncIterator[Event]: ...

    @abstractmethod
    def cancel_current(self) -> None: ...

    @abstractmethod
    async def get_agent_status(self, session_id: str) -> dict[str, Any]: ...


class DefaultCoordinator(CoordinatorService):

    def __init__(self, session_service: SessionService, runtime: AgentRuntime) -> None:
        self._sessions = session_service
        self._runtime = runtime

    async def create_session(self, title: str | None = None) -> Session:
        return await self._sessions.create(title=title)

    async def list_sessions(self) -> list[Session]:
        return await self._sessions.list_active()

    async def resume_session(self, session_id: str) -> Session:
        session = await self._sessions.require(session_id)
        self._runtime.set_summary((session.metadata or {}).get("summary"))
        return session

    async def handle_prompt(self, session_id: str, prompt: str, mode: ScenarioMode, role: AgentRole = AgentRole.CODER, plan_context: str = "") -> AsyncIterator[Event]:
        await self._sessions.require(session_id)

        user_msg = Message(role="user", content=prompt, session_id=session_id)
        await self._sessions.add_message(session_id, user_msg)

        history = await self._sessions.get_history(session_id)

        async for event in self._runtime.process_prompt(prompt=prompt, session_id=session_id, history=history, mode=mode.value if hasattr(mode, "value") else str(mode), plan_context=plan_context):
            yield event

        summary = self._runtime.summary
        if summary:
            session_obj = await self._sessions.get(session_id)
            if session_obj:
                session_obj.metadata["summary"] = summary
                await self._sessions.update(session_obj)

    def cancel_current(self) -> None:
        self._runtime.cancel()

    async def get_agent_status(self, session_id: str) -> dict[str, Any]:
        return {"session_id": session_id, "state": self._runtime.get_state().value, "summary": self._runtime.summary}
