"""Error recovery — wraps agent loop with recoverable error handling."""

from __future__ import annotations

import logging
from typing import AsyncIterator, Callable

from config.settings import AppSettings
from core.errors import ZenithError, ProviderError
from core.events import Event, EventKind
from core.message import Message
from providers.base import BaseProvider
from tools.registry import ToolRegistry
from .loop import AgentLoop
from .context import ContextManager

logger = logging.getLogger(__name__)


class RecoverableAgentLoop:
    """Wraps AgentLoop with error recovery: saves state, yields recoverable errors."""

    def __init__(
        self,
        config: AppSettings,
        provider: BaseProvider,
        context_manager: ContextManager | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self.agent = AgentLoop(config, provider, context_manager, tool_registry)
        self.config = config
        self.provider = provider
        self._last_error: str | None = None

    @property
    def summary(self) -> str | None:
        return self.agent.summary

    def set_summary(self, summary: str | None) -> None:
        self.agent.set_summary(summary)

    @property
    def last_error(self) -> str | None:
        return self._last_error

    async def process_prompt(
        self,
        prompt: str,
        session_id: str,
        history: list[Message],
        mode: str = "build",
        skills_section: str = "",
        confirm_callback: Callable | None = None,
        plan_context: str = "",
    ) -> AsyncIterator[Event]:
        """Process prompt with error recovery.

        Catches errors from the inner agent loop and tracks them.
        Error events already contain recoverable flag for UI retry buttons.
        """
        self._last_error = None

        try:
            async for event in self.agent.process_prompt(
                prompt, session_id, history, mode,
                skills_section=skills_section,
                confirm_callback=confirm_callback,
                plan_context=plan_context,
            ):
                if event.kind == EventKind.ERROR:
                    self._last_error = event.data.get("message", "Unknown error")
                yield event

        except ProviderError as e:
            self._last_error = str(e)
            logger.error("Provider error (recoverable=%s): %s", e.recoverable, e)

            yield Event(
                kind=EventKind.ERROR,
                data={
                    "message": str(e),
                    "code": e.code,
                    "recoverable": e.recoverable,
                    "provider": e.provider,
                },
                session_id=session_id,
            )

        except ZenithError as e:
            self._last_error = str(e)
            logger.error("Zenith error: %s", e)

            yield Event(
                kind=EventKind.ERROR,
                data={
                    "message": str(e),
                    "code": e.code,
                    "recoverable": e.recoverable,
                },
                session_id=session_id,
            )

        except Exception as e:
            self._last_error = str(e)
            logger.exception("Unexpected error in agent loop")

            yield Event(
                kind=EventKind.ERROR,
                data={
                    "message": f"Unexpected error: {e}",
                    "code": "UNEXPECTED",
                    "recoverable": False,
                },
                session_id=session_id,
            )
