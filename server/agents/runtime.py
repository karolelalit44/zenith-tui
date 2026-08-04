
from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any
from server.domain.domain import AgentState
from server.domain.events import Event
from server.domain.message import Message
from server.providers.base import BaseProvider
from server.toolkit.registry import ToolRegistry

logger = logging.getLogger(__name__)


class AgentRuntime(ABC):

    @abstractmethod
    async def process_prompt(self, prompt: str, session_id: str, history: list[Message], mode: str = "build", skills_section: str = "", confirm_callback: Any | None = None, plan_context: str = "", model_override: str | None = None, repo_map: str | None = None) -> AsyncIterator[Event]:
        ...

    @abstractmethod
    def cancel(self) -> None:
        ...

    @abstractmethod
    def get_state(self) -> AgentState:
        ...

    @property
    @abstractmethod
    def summary(self) -> str | None:
        ...

    @abstractmethod
    def set_summary(self, summary: str | None) -> None:
        ...


class DefaultAgentRuntime(AgentRuntime):

    def __init__(self, config: Any, provider: BaseProvider, tool_registry: ToolRegistry | None = None) -> None:
        from server.agents.context import ContextManager
        from server.agents.loop import AgentLoop

        self._config = config
        self._provider = provider
        self._tool_registry = tool_registry
        self._loop = AgentLoop(config, provider, ContextManager(config), tool_registry)
        self._state = AgentState.IDLE

    async def process_prompt(self, prompt: str, session_id: str, history: list[Message], mode: str = "build", skills_section: str = "", confirm_callback: Any | None = None, plan_context: str = "", model_override: str | None = None, repo_map: str | None = None) -> AsyncIterator[Event]:
        self._state = AgentState.RUNNING
        try:
            async for event in self._loop.process_prompt(prompt, session_id, history, mode, skills_section=skills_section, confirm_callback=confirm_callback, plan_context=plan_context, model_override=model_override, repo_map=repo_map):
                yield event
        finally:
            self._state = AgentState.IDLE

    def cancel(self) -> None:
        self._loop.cancel()

    def get_state(self) -> AgentState:
        return self._state

    @property
    def summary(self) -> str | None:
        return self._loop.summary

    def set_summary(self, summary: str | None) -> None:
        self._loop.set_summary(summary)
