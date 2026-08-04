"""Chat history manager — summarization and history trimming."""

from __future__ import annotations

import logging

from server.config.settings import AppSettings
from server.domain.message import Message
from server.providers.base import BaseProvider

logger = logging.getLogger(__name__)

NO_CONTEXT_SENTINEL = "No prior context available."


class HistoryManager:
    """Manages conversation history: summarization, trimming, and retrieval."""

    def __init__(self, config: AppSettings, provider: BaseProvider) -> None:
        self.config = config
        self.provider = provider

    async def summarize(
        self,
        messages: list[Message],
        model: str,
        session_id: str = "",
        previous_summary: str | None = None,
    ) -> str:
        """Summarize a list of messages using the anchored ConversationSummarizer.

        The summarization runs on the configured weak_model in a background
        thread so the main agent loop is never blocked by the same provider.
        Falls back to a truncated summary on failure.
        """
        from server.agents.summarizer import ConversationSummarizer

        return await ConversationSummarizer(self.config, self.provider).summarize(
            messages,
            model,
            session_id=session_id,
            previous_summary=previous_summary,
        )

    @staticmethod
    def _fallback_summary(messages: list[Message], max_messages: int = 5) -> str:
        """Fallback summary when LLM summarization fails — last N messages as context."""
        recent = messages[-max_messages:] if len(messages) > max_messages else messages
        lines = [f"[{m.role}]: {m.content[:200]}" for m in recent if m.content]
        return "\n".join(lines) if lines else "No prior context available."

    @staticmethod
    def get_recent_messages(messages: list[Message], count: int = 20) -> list[Message]:
        """Return the last `count` messages from history."""
        return messages[-count:] if len(messages) > count else messages
