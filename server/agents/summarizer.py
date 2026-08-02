"""Anchored, structured conversation summarizer (P1.5-P1.6).

Compaction summaries follow a stable Markdown template (opencode
SUMMARY_TEMPLATE) so each summary has the same shape, and new summaries
anchor on the previous one (pi UPDATE pattern) so knowledge accumulates
across compactions instead of being regenerated from scratch. Summaries are
phrased in the first person (aider style) and never mention the compaction
process.
"""

from __future__ import annotations

import asyncio
import inspect
import logging

from server.config.settings import AppSettings
from server.domain.message import Message
from server.providers.base import BaseProvider

logger = logging.getLogger(__name__)

SUMMARY_TEMPLATE = """Objective
- {Objective}

Important Details
- {Important Details}

Work State
- {Work State}

Next Move
- {Next Move}

Relevant Files
- {Relevant Files}"""

_SUMMARY_RULES = """Rules:
- Use terse bullet points, not prose.
- Preserve concrete details: file paths, function/symbol names, error messages, decisions, and the user's intent.
- Phrase the summary in the first person from the assistant's perspective (e.g. "I asked you to ...", "I am implementing ...").
- Never use fenced code blocks.
- Do not mention the summary process, compaction, or that this is a summary."""


class ConversationSummarizer:
    """Summarize (or update) a conversation with a stable, anchored structure."""

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
        """Summarize `messages`, anchored on `previous_summary` when present.

        The summarization request is isolated from the main loop (a single
        user message, run on the configured weak_model in a background thread)
        so it neither reuses nor pollutes the live conversation context.
        """
        if not messages:
            return ""
        conversation = "\n".join(f"[{m.role}]: {m.content}" for m in messages if m.content)
        prompt = self._build_prompt(conversation, previous_summary)
        try:
            kwargs = {}
            if self.config.weak_model and "model" in inspect.signature(self.provider.complete).parameters:
                kwargs["model"] = self.config.weak_model
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    asyncio.run,
                    self.provider.complete(
                        [{"role": "user", "content": prompt}],
                        **kwargs,
                    ),
                ),
                timeout=30.0,
            )
        except TimeoutError:
            logger.warning("Summarization timed out, using fallback")
            result = self._fallback(messages)
        except Exception as e:
            logger.warning("Summarization failed: %s", e)
            result = self._fallback(messages)
        return (result or "").strip()

    def _build_prompt(self, conversation: str, previous_summary: str | None) -> str:
        if previous_summary:
            return (
                "Update the anchored summary below with the new conversation. "
                "Preserve still-true details, remove stale details, and merge in the new facts.\n\n"
                "<previous-summary>\n"
                + previous_summary
                + "\n</previous-summary>\n\n"
                "New conversation:\n"
                + conversation
                + "\n\nUse this Markdown template:\n"
                + SUMMARY_TEMPLATE
                + "\n"
                + _SUMMARY_RULES
            )
        return (
            "Create a short summary of the conversation below.\n\n"
            "Conversation:\n"
            + conversation
            + "\n\nUse this Markdown template:\n"
            + SUMMARY_TEMPLATE
            + "\n"
            + _SUMMARY_RULES
        )

    @staticmethod
    def _fallback(messages: list[Message]) -> str:
        recent = [m for m in messages[-5:] if m.content]
        if not recent:
            return "Objective\n- Continue the prior conversation\n\nWork State\n- No prior context available."
        lines = "\n".join(f"- [{m.role}] {m.content[:200]}" for m in recent)
        return (
            "Objective\n- Continue the prior conversation\n\n"
            "Important Details\n"
            + lines
        )
