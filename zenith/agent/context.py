"""Context window manager — builds message lists within token budget and detects when summarization is needed."""

from __future__ import annotations

from dataclasses import dataclass

from zenith.config.settings import AppSettings
from zenith.core.message import Message
from zenith.providers.token_counter import TokenCounter

RESPONSE_RESERVE_RATIO = 0.7
PROMPT_BUFFER_TOKENS = 500
SUMMARY_FRAMING_TOKENS = 4


@dataclass
class TokenInfo:
    used: int
    remaining: int
    total: int
    percent: float


class ContextManager:
    """Manages context window: builds message lists within token limits, tracks usage, detects when to summarize."""

    def __init__(self, config: AppSettings) -> None:
        self.config = config
        self.token_counter = TokenCounter()

    def build_messages(
        self,
        history: list[Message],
        system_prompt: str,
        new_prompt: str,
        model: str,
        summary: str | None = None,
    ) -> list[dict]:
        """Build the messages list for the LLM, staying within context budget.

        Priority: system_prompt + summary (if any) + most recent history + new_prompt.
        Older history is dropped first when approaching the limit.
        """
        max_tokens = self.config.max_context_tokens
        budget = int(max_tokens * RESPONSE_RESERVE_RATIO)

        messages: list[dict] = []

        # 1. System prompt (always included)
        system_tokens = self.token_counter.count(system_prompt, model)
        messages.append({"role": "system", "content": system_prompt})
        used = system_tokens

        # 2. Summary (if provided, takes precedence over old history)
        if summary:
            summary_tokens = self.token_counter.count(summary, model)
            if used + summary_tokens <= budget:
                messages.append({"role": "user", "content": f"[Previous conversation summary]\n{summary}"})
                messages.append({"role": "assistant", "content": "Understood."})
                used += summary_tokens + SUMMARY_FRAMING_TOKENS

        # 3. History — add most recent first, drop oldest when budget exceeded
        history_msgs: list[dict] = []
        for msg in history:
            entry = {"role": msg.role, "content": msg.content}
            entry_tokens = self.token_counter.count(msg.content, model)
            history_msgs.append((entry, entry_tokens))

        included: list[dict] = []
        for entry, tokens in reversed(history_msgs):
            if used + tokens + PROMPT_BUFFER_TOKENS > budget:
                break
            included.insert(0, entry)
            used += tokens

        messages.extend(included)

        # 4. New prompt (always included)
        messages.append({"role": "user", "content": new_prompt})

        return messages

    def should_summarize(self, messages: list[dict], model: str) -> bool:
        """Check if messages exceed the summary threshold."""
        total = self.token_counter.count_messages(messages, model)
        threshold = self.config.max_context_tokens * self.config.summary_threshold
        return total > threshold

    def get_token_info(self, messages: list[dict], model: str) -> TokenInfo:
        """Get token usage information for a message list."""
        used = self.token_counter.count_messages(messages, model)
        total = self.config.max_context_tokens
        remaining = max(0, total - used)
        percent = used / total if total > 0 else 0.0
        return TokenInfo(used=used, remaining=remaining, total=total, percent=percent)

    def count_tokens(self, text: str, model: str) -> int:
        """Count tokens in a single text string."""
        return self.token_counter.count(text, model)
