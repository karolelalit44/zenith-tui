"""Chat history manager — summarization and history trimming."""

from __future__ import annotations

import logging

from zenith.providers.base import BaseProvider
from zenith.config.settings import AppSettings
from zenith.core.message import Message

logger = logging.getLogger(__name__)


class HistoryManager:
    """Manages conversation history: summarization, trimming, and retrieval."""

    def __init__(self, config: AppSettings, provider: BaseProvider) -> None:
        self.config = config
        self.provider = provider

    async def summarize(self, messages: list[Message], model: str) -> str:
        """Summarize a list of messages using the LLM provider.

        Returns a concise summary preserving key decisions, context, and user intent.
        """
        if not messages:
            return ""

        conversation = "\n".join(f"[{m.role}]: {m.content}" for m in messages)
        summary_prompt = (
            "Summarize this conversation concisely. "
            "Preserve key decisions, context, user intent, and any important technical details.\n\n"
            f"{conversation}"
        )

        try:
            return await self.provider.complete(
                [{"role": "user", "content": summary_prompt}]
            )
        except Exception as e:
            logger.warning("Summarization failed: %s", e)
            # Fallback: use the last N messages as a "summary"
            return self._fallback_summary(messages)

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
