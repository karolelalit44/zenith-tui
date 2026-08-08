from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from server.config.constants import BUILD_MODE
from server.config.settings import AppSettings
from server.domain.errors import ProviderError, ZenithError
from server.domain.events import Event, EventKind
from server.domain.message import Message
from server.providers.base import BaseProvider
from server.toolkit.registry import ToolRegistry

from .context import ContextManager
from .loop import AgentLoop

logger = logging.getLogger(__name__)


class RecoverableAgentLoop:
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
        mode: str = BUILD_MODE,
        skills_section: str = "",
        plan_context: str = "",
        model_override: str | None = None,
        repo_map: str | None = None,
    ) -> AsyncIterator[Event]:
        self._last_error = None
        try:
            async for event in self.agent.process_prompt(
                prompt,
                session_id,
                history,
                mode,
                skills_section=skills_section,
                plan_context=plan_context,
                model_override=model_override,
                repo_map=repo_map,
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
                data={"message": str(e), "code": e.code, "recoverable": e.recoverable},
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
