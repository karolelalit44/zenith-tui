
from __future__ import annotations
import logging
from server.config.settings import AppSettings
from server.domain.message import Message
from server.providers.base import BaseProvider

logger = logging.getLogger(__name__)

NO_CONTEXT_SENTINEL = "No prior context available."


class HistoryManager:

    def __init__(self, config: AppSettings, provider: BaseProvider) -> None:
        self.config = config
        self.provider = provider

    async def summarize(self, messages: list[Message], model: str, session_id: str = "", previous_summary: str | None = None) -> str:
        from server.agents.summarizer import ConversationSummarizer

        return await ConversationSummarizer(self.config, self.provider).summarize(messages, model, session_id=session_id, previous_summary=previous_summary)

    @staticmethod
    def _fallback_summary(messages: list[Message], max_messages: int = 5) -> str:
        recent = messages[-max_messages:] if len(messages) > max_messages else messages
        lines = [f"[{m.role}]: {m.content[:200]}" for m in recent if m.content]
        return "\n".join(lines) if lines else "No prior context available."

    @staticmethod
    def get_recent_messages(messages: list[Message], count: int = 20) -> list[Message]:
        return messages[-count:] if len(messages) > count else messages
