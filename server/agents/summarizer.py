from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from server.config.environment import ZENITH_SUMMARIZER_TIMEOUT
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
        focus: str | None = None,
        event_sink: Callable[[str, str], Awaitable[None]] | None = None,
    ) -> str:
        if not messages:
            return ""
        conversation = self._serialize(messages)
        prompt = self._build_prompt(conversation, previous_summary, focus)
        try:
            result = await self._complete_isolated(prompt, model)
        except TimeoutError:
            logger.warning("Summarization timed out, using fallback")
            await self._report_degraded(event_sink, session_id)
            result = self._fallback(messages)
        except Exception as e:
            logger.warning("Summarization failed: %s", e)
            await self._report_degraded(event_sink, session_id)
            result = self._fallback(messages)
        return (result or "").strip()

    async def _complete_isolated(self, prompt: str, model: str) -> str:
        """Run the fold as a standalone request that cannot disturb the turn.

        Three things make this safe rather than merely convenient:

        * **Same model as the turn.** The summary is the only record of the tool
          state and reasoning that produced the current work. A cheaper model
          loses exactly the details a later turn needs, so the fold runs on
          ``model`` and constrains the output length instead.
        * **Its own prompt.** The fold prompt is not a prefix of the agent
          prompt, so it can never *read* the turn's cached prefix, and it is
          short enough that the provider will not retain a reusable entry for
          it. A cache write here is pure waste on a cache that never hits.
        * **Turn usage preserved.** ``complete()`` resets the provider's
          cumulative ledger; left alone that would zero the running turn's
          spend and under-report every total at the end of it.
        """
        provider: Any = self.provider
        accepts_model = "model" in inspect.signature(provider.complete).parameters
        kwargs: dict[str, Any] = {"model": model} if accepts_model else {}
        request = [{"role": "user", "content": prompt}]

        async def _call() -> str:
            guard = getattr(provider, "preserve_usage_ledger", None)
            if guard is None:
                return await provider.complete(request, **kwargs)
            with guard():
                return await provider.complete(request, **kwargs)

        return await asyncio.wait_for(_call(), timeout=ZENITH_SUMMARIZER_TIMEOUT)

    def _serialize(self, messages: list[Message]) -> str:
        """Flatten messages into the transcript the fold prompt embeds.

        Tool-call structure is not preserved here. The fold's job is to carry
        *state* forward, and it reads that state from the work_state and
        decisions it returns, not from a transcript it cannot act on.
        """
        return "\n".join(f"[{m.role}]: {m.content}" for m in messages if m.content)

    @staticmethod
    async def _report_degraded(
        event_sink: Callable[[str, str], Awaitable[None]] | None, session_id: str
    ) -> None:
        # Surfaces a degraded summary to the user instead of failing silently.
        # The fallback still returns a usable (reduced) summary so the session
        # continues, but context continuity is weaker than a real one.
        if event_sink is None:
            return
        await event_sink(
            "Context summarization was degraded by a provider error; the saved "
            "summary may be incomplete and continuity across turns is reduced.",
            "SUMMARIZATION_DEGRADED",
        )

    def _build_prompt(
        self, conversation: str, previous_summary: str | None, focus: str | None = None
    ) -> str:
        focus_block = ""
        if focus and focus.strip():
            focus_block = (
                "\n\nUser-specified focus: " + focus.strip() + "\n"
                "Keep details that relate to this focus even if they are minor, and "
                "prioritise them over unrelated details."
            )
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
                + focus_block
            )
        return (
            "Create a short summary of the conversation below.\n\nConversation:\n"
            + conversation
            + "\n\nUse this Markdown template:\n"
            + SUMMARY_TEMPLATE
            + "\n"
            + _SUMMARY_RULES
            + focus_block
        )

    @staticmethod
    def _fallback(messages: list[Message]) -> str:
        # Deterministic degradation (AGENT_RELIABILITY_PLAN P2.1): the objective
        # is derived from the actual conversation (most recent user message) —
        # never canned boilerplate that misrepresents the request.
        recent = [m for m in messages[-5:] if m.content]
        objective = ""
        for message in reversed(messages):
            content = str(getattr(message, "content", "") or "").strip()
            if getattr(message, "role", "") == "user" and content:
                objective = content
                break
        sections = ["Objective\n- " + (objective[:200] if objective else "(unavailable)")]
        if recent:
            sections.append(
                "Important Details\n" + "\n".join(f"- [{m.role}] {m.content[:200]}" for m in recent)
            )
        else:
            sections.append("Work State\n- No prior context available.")
        return "\n\n".join(sections)
