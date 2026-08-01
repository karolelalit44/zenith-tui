"""Chat history manager — summarization and history trimming."""

from __future__ import annotations

import asyncio
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

    async def summarize(self, messages: list[Message], model: str, session_id: str = "") -> str:
        """Summarize a list of messages using the LLM provider.

        Runs summarization in a background thread to avoid blocking the
        agent loop. Falls back to a truncated summary on failure.

        Durable facts from the compaction are appended to the workspace
        memory store (HP-7) so they survive across sessions.
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
            # Run summarization in a background thread so the main agent
            # loop isn't blocked by a slow LLM call to the same provider.
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    asyncio.run,
                    self.provider.complete(
                        [{"role": "user", "content": summary_prompt}]
                    ),
                ),
                timeout=30.0,
            )
        except TimeoutError:
            logger.warning("Summarization timed out, using fallback")
            result = self._fallback_summary(messages)
        except Exception as e:
            logger.warning("Summarization failed: %s", e)
            result = self._fallback_summary(messages)

        # Persist durable facts extracted during compaction (HP-7)
        if result and result != NO_CONTEXT_SENTINEL:
            try:
                from server.sessions.memory import MemoryStore
                MemoryStore(self.config.workspace_root).append(session_id, result)
            except Exception as e:
                logger.warning("Failed to persist durable memory: %s", e)

        return result

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
