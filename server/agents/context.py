"""Context window manager — builds message lists within token budget and detects when summarization is needed."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from server.config.settings import AppSettings
from server.domain.message import Message
from server.persistence.repositories import load_catalog
from server.providers.token_counter import TokenCounter

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
        self._repo_map_cache: str | None = None
        self._memory_cache: str | None = None

    def _resolve_context_window(self, model: str) -> int:
        """Get context window for a model, capped by global config."""
        from_catalog = _get_model_context_window(model)
        return min(from_catalog, self.config.max_context_tokens)

    def get_repo_map(self, chat_files: list[str] | None = None) -> str:
        """Build a token-budgeted, ranked repo map (Aider-style), cached per instance.

        Returns an empty string when disabled or unavailable, so callers can
        safely inject the result into the system prompt.
        """
        if not self.config.repo_map_enabled:
            return ""
        if self._repo_map_cache is not None:
            return self._repo_map_cache
        try:
            from server.workspace.repo_map import RepoMap
            repo = RepoMap(self.config.workspace_root)
            self._repo_map_cache = repo.get_repo_map(
                chat_files=chat_files,
                max_tokens=self.config.repo_map_tokens,
            )
        except Exception as e:
            logger.warning("Failed to build repo map: %s", e)
            self._repo_map_cache = ""
        return self._repo_map_cache

    def get_memory(self) -> str:
        """Load durable workspace memory (`memory/*.md`), cached per instance.

        Returns an empty string when disabled or unavailable.
        """
        if not self.config.memory_enabled:
            return ""
        if self._memory_cache is not None:
            return self._memory_cache
        try:
            from server.sessions.memory import MemoryStore
            self._memory_cache = MemoryStore(self.config.workspace_root).load()
        except Exception as e:
            logger.warning("Failed to load memory: %s", e)
            self._memory_cache = ""
        return self._memory_cache

    def build_messages(
        self,
        history: list[Message],
        system_prompt: str,
        new_prompt: str,
        model: str,
        summary: str | None = None,
        plan_block: str | None = None,
        use_system_prompt: bool = True,
        repo_map: str | None = None,
        memory: str | None = None,
    ) -> list[dict]:
        """Build the messages list for the LLM, staying within context budget.

        Priority: system_prompt (if use_system_prompt) + repo_map + memory + plan_block (exempt from truncation) + summary + most recent history + new_prompt.
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

        # Repo map block — bounded by config.repo_map_tokens, injected right
        # after the system prompt (Aider-style) so the model sees the repo
        # structure before instructions/history.
        repo_map_text = repo_map if repo_map is not None else self.get_repo_map()
        repo_map_block = f"<repo_map>\n{repo_map_text}\n</repo_map>" if repo_map_text.strip() else ""
        repo_map_tokens = self.token_counter.count(repo_map_block, model) if repo_map_block else 0

        # Durable memory block (HP-7) — workspace facts from memory/*.md.
        memory_text = memory if memory is not None else self.get_memory()
        memory_block = f"<memory>\n{memory_text}\n</memory>" if memory_text.strip() else ""
        memory_tokens = self.token_counter.count(memory_block, model) if memory_block else 0

        # 1. System prompt (skipped for models that don't support system role)
        if use_system_prompt:
            system_tokens = self.token_counter.count(system_prompt, model)
            messages.append({"role": "system", "content": system_prompt})
            used = system_tokens
        else:
            used = 0

        # 1b. Repo map + memory (system messages when the model supports them;
        # otherwise folded into the merged user message below)
        if use_system_prompt:
            if repo_map_block:
                messages.append({"role": "system", "content": repo_map_block})
                used += repo_map_tokens
                logger.info("Repo map injected into context: %d chars, %d tokens", len(repo_map_text), repo_map_tokens)
            if memory_block:
                messages.append({"role": "system", "content": memory_block})
                used += memory_tokens
                logger.info("Memory injected into context: %d chars, %d tokens", len(memory_text), memory_tokens)
        else:
            used += repo_map_tokens + memory_tokens

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
            parts = [system_prompt]
            if repo_map_block:
                parts.append(repo_map_block)
            if memory_block:
                parts.append(memory_block)
            parts.append(new_prompt)
            new_entry = {"role": "user", "content": "\n\n".join(parts)}
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
