from __future__ import annotations

import asyncio
import inspect
import logging

from server.config.settings import AppSettings
from server.domain.message import Message
from server.providers.base import BaseProvider

logger = logging.getLogger(__name__)
SUMMARY_TEMPLATE = "Objective\n- {Objective}\n\nImportant Details\n- {Important Details}\n\nWork State\n- {Work State}\n\nNext Move\n- {Next Move}\n\nRelevant Files\n- {Relevant Files}"
_SUMMARY_RULES = 'Rules:\n- Use terse bullet points, not prose.\n- Preserve concrete details: file paths, function/symbol names, error messages, decisions, and the user\'s intent.\n- Phrase the summary in the first person from the assistant\'s perspective (e.g. "I asked you to ...", "I am implementing ...").\n- Never use fenced code blocks.\n- Do not mention the summary process, compaction, or that this is a summary.'


class ConversationSummarizer:
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
        if not messages:
            return ""
        conversation = "\n".join(f"[{m.role}]: {m.content}" for m in messages if m.content)
        prompt = self._build_prompt(conversation, previous_summary)
        try:
            kwargs = {}
            if (
                self.config.weak_model
                and "model" in inspect.signature(self.provider.complete).parameters
            ):
                kwargs["model"] = self.config.weak_model
            result = await asyncio.wait_for(
                self.provider.complete([{"role": "user", "content": prompt}], **kwargs),
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
                "Update the anchored summary below with the new conversation. Preserve still-true details, remove stale details, and merge in the new facts.\n\n<previous-summary>\n"
                + previous_summary
                + "\n</previous-summary>\n\nNew conversation:\n"
                + conversation
                + "\n\nUse this Markdown template:\n"
                + SUMMARY_TEMPLATE
                + "\n"
                + _SUMMARY_RULES
            )
        return (
            "Create a short summary of the conversation below.\n\nConversation:\n"
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
        return "Objective\n- Continue the prior conversation\n\nImportant Details\n" + lines
