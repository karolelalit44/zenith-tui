from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from server.config.constants import (
    BUILD_MODE,
    CHARS_PER_TOKEN,
    DEFAULT_CONTEXT_WINDOW,
    HARD_STOP_USAGE_RATIO,
    LARGE_CONTEXT_WINDOW,
    MIN_OUTPUT_RESERVE_TOKENS,
    SESSION_STATE_MARKER,
    SUMMARY_FRAMING_TOKENS,
)
from server.config.settings import AppSettings
from server.domain.message import Message
from server.providers.token_counter import TokenCounter
from server.storage import load_catalog

logger = logging.getLogger(__name__)

_E2E_INSTRUMENT = bool(os.environ.get("ZENITH_E2E_INSTRUMENT", ""))

_req_seq = 0

def _instrument(messages: list[dict], model: str) -> None:
    """When enabled, log the exact model request for e2e verification.

    Used only by scripts/backend_e2e_signoff.py; off by default so production
    logs stay unchanged.
    """
    if not _E2E_INSTRUMENT:
        return
    global _req_seq
    _req_seq += 1
    for i, msg in enumerate(messages):
        logger.info(
            "E2E_REQUEST[%d] role=%s len=%d preview=%s",
            _req_seq,
            msg.get("role", "?"),
            len(str(msg.get("content", ""))),
            str(msg.get("content", ""))[:120].replace("\n", "\\n"),
        )


def _prompt_buffer(system_prompt: str) -> int:
    estimated = max(200, len(system_prompt) // 10)
    return min(estimated, 2000)


def _lookup_model_context_window(model: str) -> int | None:
    """Return the model's catalog context window, or ``None`` when unknown.

    A ``None`` result means the window is an *estimate* (the caller falls back to
    ``DEFAULT_CONTEXT_WINDOW``) and must never be presented as authoritative.
    """
    try:
        cat = load_catalog()
        for prov in cat.get("providers", {}).values():
            for m in prov.get("models", []):
                if m["id"] == model:
                    val = m.get("context_window", 0)
                    return int(val) if val else None
    except Exception:
        pass
    return None


def _get_model_context_window(model: str, fallback: int = DEFAULT_CONTEXT_WINDOW) -> int:
    val = _lookup_model_context_window(model)
    return fallback if val is None else val


def _adaptive_reserve(model: str, context_window: int) -> int:
    if context_window >= LARGE_CONTEXT_WINDOW:
        reserve = min(20000, context_window // 10)
    else:
        reserve = max(4096, context_window // 5)
    if context_window >= DEFAULT_CONTEXT_WINDOW:
        return max(MIN_OUTPUT_RESERVE_TOKENS, reserve)
    return min(reserve, max(0, context_window - 500))


@dataclass
class TokenBreakdown:
    """Deterministic token accounting for a composed message list."""

    system: int = 0
    summary: int = 0
    instructions: int = 0
    history: int = 0
    user: int = 0
    tools: int = 0

    @property
    def volatile(self) -> int:
        return self.summary + self.instructions + self.history

    @property
    def total(self) -> int:
        return self.system + self.volatile + self.user + self.tools

    def to_dict(self) -> dict[str, int]:
        return {
            "system": self.system,
            "summary": self.summary,
            "instructions": self.instructions,
            "history": self.history,
            "user": self.user,
            "tools": self.tools,
        }


@dataclass
class TokenInfo:
    used: int
    remaining: int
    total: int
    percent: float
    window_estimated: bool = False


class ContextManager:
    def __init__(self, config: AppSettings) -> None:
        self.config = config
        self.token_counter = TokenCounter()
        self._aux_tokens = 0
        self._last_t0_len = 0
        self._window_estimated = False
        self._repo_map_cache: str | None = None

    def set_aux_tokens(self, tokens: int) -> None:
        self._aux_tokens = max(0, int(tokens))

    @property
    def context_window_estimated(self) -> bool:
        """True when the active model's window is unknown and a fallback is used."""
        return self._window_estimated

    def _resolve_context_window(self, model: str) -> int:
        from_catalog = _lookup_model_context_window(model)
        if from_catalog is None:
            self._window_estimated = True
            return min(DEFAULT_CONTEXT_WINDOW, self.config.max_context_tokens)
        self._window_estimated = False
        return min(from_catalog, self.config.max_context_tokens)

    def _resolve_repo_map_tokens(self, model: str) -> int:
        explicit = getattr(self.config, "repo_map_tokens", None)
        if explicit is not None:
            return int(explicit)
        context_window = self._resolve_context_window(model)
        return min(1024, max(100, int(context_window * 0.05)))

    def get_repo_map(self, model: str = "", force_refresh: bool = False) -> str:
        if not getattr(self.config, "repo_map_enabled", True):
            return ""
        if self._repo_map_cache is not None and not force_refresh:
            return self._repo_map_cache
        from server.workspace.repo_map import RepoMap

        tokens = self._resolve_repo_map_tokens(model)
        repo = RepoMap(self.config.workspace_root)
        self._repo_map_cache = repo.get_repo_map(max_tokens=tokens, force_refresh=force_refresh)
        return self._repo_map_cache

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
        session_id: str | None = None,
        mode: str = BUILD_MODE,
    ) -> list[dict]:
        max_tokens = self._resolve_context_window(model)
        reserve = _adaptive_reserve(model, max_tokens)
        budget = max_tokens - reserve
        self._last_t0_len = 1 if use_system_prompt else 0
        messages: list[dict] = []
        pbuf = _prompt_buffer(system_prompt)
        if repo_map is None:
            if getattr(self.config, "repo_map_enabled", True) and bool(history):
                repo_map = self.get_repo_map(model)
            else:
                repo_map = ""

        if use_system_prompt:
            system_tokens = self.token_counter.count(system_prompt, model)
            messages.append({"role": "system", "content": system_prompt})
            used = system_tokens
            if repo_map and bool(history):
                map_content = f"<repo_map>\n{repo_map}\n</repo_map>"
                map_tokens = self.token_counter.count(map_content, model)
                messages.append({"role": "system", "content": map_content})
                used += map_tokens
        else:
            used = 0
        if plan_block:
            plan_tokens = self.token_counter.count(plan_block, model)
            if used + plan_tokens + pbuf <= budget:
                messages.append(
                    {
                        "role": "system",
                        "content": f"<plan_to_execute>\n{plan_block}\n</plan_to_execute>\n\nYou MUST execute the plan above exactly. Create every file listed, implement every component, and follow the architecture decisions described. The user's latest message is the authoritative intent: if it conflicts with this plan, follow the latest message and say what you changed.",
                    }
                )
                used += plan_tokens
                logger.info(
                    "Plan block injected into context: %d chars, %d tokens",
                    len(plan_block),
                    plan_tokens,
                )
            else:
                logger.warning(
                    "Plan block too large to inject (%d tokens, budget %d)", plan_tokens, budget
                )
        if summary:
            summary_tokens = self.token_counter.count(summary, model)
            if used + summary_tokens + pbuf <= budget:
                messages.append(
                    {"role": "system", "content": f"[Previous conversation summary]\n{summary}"}
                )
                used += summary_tokens + SUMMARY_FRAMING_TOKENS
        history_entries: list[tuple[dict, int, bool]] = []
        last_key: tuple[str, str] | None = None
        for msg in history:
            if msg.role == "assistant" and not msg.content and not msg.tool_calls:
                continue
            key = (msg.role, msg.content)
            if key == last_key:
                continue
            last_key = key
            entry_dict: dict[str, Any] = {"role": msg.role, "content": msg.content}
            if msg.tool_calls:
                entry_dict["tool_calls"] = [
                    tc.model_dump() if hasattr(tc, "model_dump") else tc for tc in msg.tool_calls
                ]
            entry_tokens = self.token_counter.count(str(msg.content or ""), model)
            # A tool result arrives two ways in persisted history: the live form
            # (role=user, content prefixed ``[Tool:``) and the legacy form
            # (role="tool"). Both are tool outputs. A ``role="tool"``/``[Tool:``
            # entry that follows an assistant tool-call stays paired with it;
            # user prompts and assistant messages are preserved chronologically.
            history_entries.append((entry_dict, entry_tokens, msg.has_tool_calls))
        retained: list[tuple[dict, int, bool]] = []
        index = len(history_entries) - 1
        while index >= 0:
            entry, entry_tokens, owns_tool_calls = history_entries[index]
            owner_index = index - 1
            owner = history_entries[owner_index] if owner_index >= 0 else None
            is_tool_result = entry["role"] == "tool" or (
                entry["role"] == "user" and str(entry["content"]).startswith("[Tool:")
            )
            if is_tool_result and owner is not None and owner[2]:
                pair_tokens = owner[1] + entry_tokens
                if used + pair_tokens + pbuf <= budget:
                    retained.extend(((entry, entry_tokens, owns_tool_calls), owner))
                    used += pair_tokens
                index -= 2
                continue
            if used + entry_tokens + pbuf <= budget:
                retained.append((entry, entry_tokens, owns_tool_calls))
                used += entry_tokens
            index -= 1
        retained.reverse()
        messages.extend(entry for entry, _tokens, _owns_tool_calls in retained)
        if not use_system_prompt:
            parts = [system_prompt]
            if repo_map and bool(history):
                parts.append(f"<repo_map>\n{repo_map}\n</repo_map>")
            parts.append(new_prompt)
            new_entry = {"role": "user", "content": "\n\n".join(parts)}
        else:
            new_entry = {"role": "user", "content": new_prompt}
        last_is_user_prompt = (
            bool(messages)
            and messages[-1].get("role") == "user"
            and not str(messages[-1].get("content") or "").startswith("[Tool:")
        )
        if not last_is_user_prompt:
            messages.append(new_entry)
        else:
            messages[-1] = new_entry
        _instrument(messages, model)
        return messages

    def required_prefix_length(self) -> int:
        return self._last_t0_len

    def should_summarize(self, messages: list[dict], model: str) -> bool:
        used = self.usage_tokens(messages, model)
        max_tokens = self._resolve_context_window(model)
        watermark = max_tokens * self.config.context_compaction_threshold
        reserve = _adaptive_reserve(model, max_tokens)
        return used >= watermark or used >= max_tokens - reserve

    def is_context_exhausted(self, messages: list[dict], model: str) -> bool:
        total = self._resolve_context_window(model)
        if total <= 0:
            return False
        used = self.usage_tokens(messages, model)
        return used >= total * HARD_STOP_USAGE_RATIO

    def get_token_info(self, messages: list[dict], model: str) -> TokenInfo:
        used = self.usage_tokens_composed(messages, model)
        total = self._resolve_context_window(model)
        remaining = max(0, total - used)
        percent = used / total if total > 0 else 0.0
        return TokenInfo(
            used=used,
            remaining=remaining,
            total=total,
            percent=percent,
            window_estimated=self._window_estimated,
        )

    def usage_tokens(self, messages: list[dict], model: str) -> int:
        """Composed-context occupancy (alias of :meth:`usage_tokens_composed`)."""
        return self.usage_tokens_composed(messages, model)

    def usage_tokens_composed(self, messages: list[dict], model: str) -> int:
        """Deterministic composed-context occupancy in tokens.

        Counts the actual message list with the local token counter plus the
        aux (tool-schema) budget. Never includes cumulative provider usage.
        """
        return self.token_counter.count_messages(messages, model) + self._aux_tokens

    def count_tokens(self, text: str, model: str) -> int:
        return self.token_counter.count(text, model)

    def token_breakdown(self, messages: list[dict]) -> TokenBreakdown:
        """Deterministic token accounting for required fragments and history."""
        breakdown = TokenBreakdown()
        t0 = self._last_t0_len
        prev_was_summary = False
        for i, msg in enumerate(messages):
            content = str(msg.get("content") or "")
            tokens = max(1, len(content) // CHARS_PER_TOKEN) + SUMMARY_FRAMING_TOKENS
            if i < t0:
                breakdown.system += tokens
                prev_was_summary = False
            elif content.startswith("[Previous conversation summary]"):
                # Detected by content marker so it is attributed correctly
                # whether injected as a user (legacy) or system (current) block.
                breakdown.summary += tokens
                prev_was_summary = True
            elif msg.get("role") == "system":
                if content.startswith(SESSION_STATE_MARKER):
                    breakdown.instructions += tokens
                prev_was_summary = False
            elif content.startswith("[Tool:"):
                breakdown.tools += tokens
                prev_was_summary = False
            elif msg.get("role") == "user":
                breakdown.user += tokens
                prev_was_summary = False
            elif prev_was_summary:
                breakdown.summary += tokens
                prev_was_summary = False
            else:
                breakdown.history += tokens
        return breakdown
