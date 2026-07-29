"""Context window manager — builds message lists within token budget and detects when summarization is needed."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from config.settings import AppSettings
from core.message import Message
from db.repository import load_catalog
from providers.token_counter import TokenCounter

logger = logging.getLogger(__name__)

SUMMARY_FRAMING_TOKENS = 4


def _prompt_buffer(system_prompt: str) -> int:
    """Dynamic prompt buffer: proportional to system prompt size, minimum 200."""
    estimated = max(200, len(system_prompt) // 10)
    return min(estimated, 2000)


def _get_model_context_window(model: str, fallback: int = 128000) -> int:
    """Resolve per-model context window from provider_catalog.json."""
    try:
        cat = load_catalog()
        for prov in cat.get("providers", {}).values():
            for m in prov.get("models", []):
                if m["id"] == model:
                    return m.get("context_window", fallback)
    except Exception:
        pass
    return fallback


def _adaptive_reserve(model: str, context_window: int) -> int:
    """Adaptive response reserve: 20K buffer for 200K+ models, 20% of context for smaller."""
    if context_window >= 200000:
        return min(20000, context_window // 10)
    return max(4096, context_window // 5)


def _adaptive_summary_threshold(model: str, context_window: int) -> float:
    """Adaptive summary threshold: 0.85 for large models, 0.75 for small models."""
    if context_window >= 200000:
        return 0.85
    if context_window >= 32000:
        return 0.80
    return 0.75


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

    def _resolve_context_window(self, model: str) -> int:
        """Get context window for a model, capped by global config."""
        from_catalog = _get_model_context_window(model)
        return min(from_catalog, self.config.max_context_tokens)

    def build_messages(
        self,
        history: list[Message],
        system_prompt: str,
        new_prompt: str,
        model: str,
        summary: str | None = None,
        plan_block: str | None = None,
        use_system_prompt: bool = True,
    ) -> list[dict]:
        """Build the messages list for the LLM, staying within context budget.

        Priority: system_prompt (if use_system_prompt) + plan_block (exempt from truncation) + summary + most recent history + new_prompt.
        Older history is dropped first when approaching the limit.
        The plan_block is injected with high priority so it is never truncated.

        When use_system_prompt=False (e.g. o1/o3 reasoning models that don't support system role),
        the system content is merged into the first user message.
        """
        max_tokens = self._resolve_context_window(model)
        reserve = _adaptive_reserve(model, max_tokens)
        budget = max_tokens - reserve

        messages: list[dict] = []
        pbuf = _prompt_buffer(system_prompt)

        # 1. System prompt (skipped for models that don't support system role)
        if use_system_prompt:
            system_tokens = self.token_counter.count(system_prompt, model)
            messages.append({"role": "system", "content": system_prompt})
            used = system_tokens
        else:
            used = 0

        # 2. Plan block (injected as system message — exempt from truncation, high priority)
        if plan_block:
            plan_tokens = self.token_counter.count(plan_block, model)
            if used + plan_tokens + pbuf <= budget:
                messages.append({
                    "role": "system",
                    "content": f"<plan_to_execute>\n{plan_block}\n</plan_to_execute>\n\nYou MUST execute the plan above exactly. Create every file listed, implement every component, and follow the architecture decisions described."
                })
                used += plan_tokens
                logger.info("Plan block injected into context: %d chars, %d tokens", len(plan_block), plan_tokens)
            else:
                logger.warning("Plan block too large to inject (%d tokens, budget %d)", plan_tokens, budget)

        # 3. Summary (if provided, takes precedence over old history)
        if summary:
            summary_tokens = self.token_counter.count(summary, model)
            if used + summary_tokens <= budget:
                messages.append({"role": "user", "content": f"[Previous conversation summary]\n{summary}"})
                messages.append({"role": "assistant", "content": "Understood."})
                used += summary_tokens + SUMMARY_FRAMING_TOKENS

        # 4. History — skip empty assistant messages and dedup consecutive duplicates
        history_msgs: list[dict] = []
        last_key: tuple[str, str] | None = None
        for msg in history:
            if msg.role == "assistant" and not msg.content:
                continue
            key = (msg.role, msg.content)
            if key == last_key:
                continue
            last_key = key
            entry = {"role": msg.role, "content": msg.content}
            entry_tokens = self.token_counter.count(msg.content, model)
            history_msgs.append((entry, entry_tokens))

        included: list[dict] = []
        for entry, tokens in reversed(history_msgs):
            if used + tokens + pbuf > budget:
                break
            included.insert(0, entry)
            used += tokens

        messages.extend(included)

        # 5. New prompt (always included)
        if not use_system_prompt:
            new_entry = {"role": "user", "content": f"{system_prompt}\n\n{new_prompt}"}
        else:
            new_entry = {"role": "user", "content": new_prompt}

        # Dedup: skip if the last history message has the same content
        if not messages or messages[-1].get("content") != new_entry.get("content"):
            messages.append(new_entry)

        return messages

    def should_summarize(self, messages: list[dict], model: str) -> bool:
        """Check if messages exceed the adaptive summary threshold."""
        total = self.token_counter.count_messages(messages, model)
        max_tokens = self._resolve_context_window(model)
        threshold = max_tokens * _adaptive_summary_threshold(model, max_tokens)
        return total > threshold

    def get_token_info(self, messages: list[dict], model: str) -> TokenInfo:
        """Get token usage information for a message list."""
        used = self.token_counter.count_messages(messages, model)
        total = self._resolve_context_window(model)
        remaining = max(0, total - used)
        percent = used / total if total > 0 else 0.0
        return TokenInfo(used=used, remaining=remaining, total=total, percent=percent)

    def count_tokens(self, text: str, model: str) -> int:
        """Count tokens in a single text string."""
        return self.token_counter.count(text, model)
