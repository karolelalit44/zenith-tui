"""Agent runtime — ABC and default implementation wrapping the existing AgentLoop."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from core.domain import AgentState
from core.events import Event
from core.message import Message
from providers.base import BaseProvider
from tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class AgentRuntime(ABC):
    """Abstract agent runtime — processes prompts through LLM + tool loop."""

    @abstractmethod
    async def process_prompt(
        self,
        prompt: str,
        session_id: str,
        history: list[Message],
        mode: str = "build",
        skills_section: str = "",
        confirm_callback: Any | None = None,
    ) -> AsyncIterator[Event]:
        """Process a user prompt through the agent loop."""
        ...

    @abstractmethod
    def cancel(self) -> None:
        """Cancel the current run."""
        ...

    @abstractmethod
    def get_state(self) -> AgentState:
        """Return current agent state."""
        ...

    @property
    @abstractmethod
    def summary(self) -> str | None:
        """Current conversation summary, if any."""
        ...

    @abstractmethod
    def set_summary(self, summary: str | None) -> None:
        """Set the conversation summary."""
        ...


class DefaultAgentRuntime(AgentRuntime):
    """Default runtime wrapping the existing AgentLoop."""

    def __init__(
        self,
        config: Any,
        provider: BaseProvider,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        from agent.context import ContextManager
        from agent.loop import AgentLoop

        self._config = config
        self._provider = provider
        self._tool_registry = tool_registry
        self._loop = AgentLoop(config, provider, ContextManager(config), tool_registry)
        self._state = AgentState.IDLE

    async def process_prompt(
        self,
        prompt: str,
        session_id: str,
        history: list[Message],
        mode: str = "build",
        skills_section: str = "",
        confirm_callback: Any | None = None,
    ) -> AsyncIterator[Event]:
        self._state = AgentState.RUNNING
        try:
            async for event in self._loop.process_prompt(
                prompt, session_id, history, mode,
                skills_section=skills_section,
                confirm_callback=confirm_callback,
            ):
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
