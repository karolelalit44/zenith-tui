"""Coordinator — orchestrates sessions, prompts, and agent spawning."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from core.domain import AgentRole, ScenarioMode
from core.events import Event
from core.message import Message
from core.session import Session
from session.service import SessionService
from .runtime import AgentRuntime

logger = logging.getLogger(__name__)


class CoordinatorService(ABC):
    """Abstract orchestrator — manages session lifecycle and prompt handling."""

    @abstractmethod
    async def create_session(self, title: str | None = None) -> Session: ...

    @abstractmethod
    async def list_sessions(self) -> list[Session]: ...

    @abstractmethod
    async def resume_session(self, session_id: str) -> Session: ...

    @abstractmethod
    async def handle_prompt(
        self,
        session_id: str,
        prompt: str,
        mode: ScenarioMode,
        role: AgentRole = AgentRole.CODER,
    ) -> AsyncIterator[Event]: ...

    @abstractmethod
    def cancel_current(self) -> None: ...

    @abstractmethod
    async def get_agent_status(self, session_id: str) -> dict[str, Any]: ...


class DefaultCoordinator(CoordinatorService):
    """Default coordinator wiring SessionService + AgentRuntime."""

    def __init__(
        self,
        session_service: SessionService,
        runtime: AgentRuntime,
    ) -> None:
        self._sessions = session_service
        self._runtime = runtime

    async def create_session(self, title: str | None = None) -> Session:
        return await self._sessions.create(title=title)

    async def list_sessions(self) -> list[Session]:
        return await self._sessions.list_active()

    async def resume_session(self, session_id: str) -> Session:
        session = await self._sessions.require(session_id)
        self._runtime.set_summary(getattr(session, "summary", None))
        return session

    async def handle_prompt(
        self,
        session_id: str,
        prompt: str,
        mode: ScenarioMode,
        role: AgentRole = AgentRole.CODER,
    ) -> AsyncIterator[Event]:
        await self._sessions.require(session_id)

        # Persist user message
        user_msg = Message(role="user", content=prompt, session_id=session_id)
        await self._sessions.add_message(session_id, user_msg)

        # Get history
        history = await self._sessions.get_history(session_id)

        # Run agent loop
        async for event in self._runtime.process_prompt(
            prompt=prompt,
            session_id=session_id,
            history=history,
            mode=mode.value if hasattr(mode, "value") else str(mode),
        ):
            yield event

        # Persist assistant response if message event was yielded
        summary = self._runtime.summary
        if summary:
            session_obj = await self._sessions.get(session_id)
            if session_obj and hasattr(session_obj, "summary"):
                session_obj.summary = summary  # type: ignore[attr-defined]

    def cancel_current(self) -> None:
        self._runtime.cancel()

    async def get_agent_status(self, session_id: str) -> dict[str, Any]:
        return {
            "session_id": session_id,
            "state": self._runtime.get_state().value,
            "summary": self._runtime.summary,
        }
