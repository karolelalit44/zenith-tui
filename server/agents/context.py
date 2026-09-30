from __future__ import annotations

import json
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
    MIN_MENTIONED_SYMBOL_LEN,
    MIN_OUTPUT_RESERVE_TOKENS,
    REPO_MAP_MAX_TOKENS,
    REPO_MAP_MIN_TOKENS,
    SESSION_STATE_MARKER,
    SUMMARY_FRAMING_TOKENS,
)
from server.config.settings import AppSettings
from server.domain.message import Message
from server.providers.token_counter import ContextUsage, TokenCounter, UsageAnchor
from server.storage import load_catalog

logger = logging.getLogger(__name__)

# How much of the tail to scan for mentioned symbols. Bounded so a long session
# does not turn map rendering into a text scan, and recent enough that the map
# tracks what the model is doing now rather than what it did an hour ago.
_MENTION_SCAN_MESSAGES = 12

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


def _call_arguments(call: Any) -> dict:
    """Argument dict of one tool call, whatever shape it was stored in.

    Four shapes occur in this codebase's history: the ``ToolCall`` model the
    domain layer actually uses (a pydantic object with an ``arguments`` dict),
    a local ``params`` dict, the OpenAI ``function.arguments`` JSON string, and a
    flat pair. Returns ``{}`` rather than raising — a malformed call is not worth
    failing a ranking signal over, and an empty contribution is the correct
    answer for one.
    """
    if isinstance(call, dict):
        raw = call.get("params")
        if raw is None:
            fn = call.get("function")
            raw = fn.get("arguments") if isinstance(fn, dict) else None
        if raw is None:
            raw = call.get("arguments")
    else:
        raw = getattr(call, "arguments", None)
        if raw is None:
            raw = getattr(call, "params", None)
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return {}
    return raw if isinstance(raw, dict) else {}


def mentioned_paths(history: list[Message], limit: int = 64) -> list[str]:
    """Paths the conversation has referred to, most recent first.

    Read from structured tool-call arguments only. Scanning message text for
    anything that looks path-shaped also returns ``and/or`` and ``1.2.3``, which
    is harmless here — the ranker resolves every candidate against the files it
    actually tracks and drops what it cannot match — but it is noise in a signal
    that does not need any.
    """
    seen: set[str] = set()
    found: list[str] = []

    def _add(path_str: str) -> None:
        if not path_str or len(found) >= limit:
            return
        norm = path_str.replace("\\", "/").removeprefix("./").strip("`'\" \t\r\n")
        if (
            norm
            and norm not in seen
            and not norm.startswith(("http:", "https:", "file:"))
        ):
            seen.add(norm)
            found.append(norm)

    for msg in reversed(history):
        if len(found) >= limit:
            break
        for call in getattr(msg, "tool_calls", None) or []:
            args = _call_arguments(call)
            for key in ("path", "filepath", "target", "file"):
                value = args.get(key)
                if isinstance(value, str):
                    _add(value)
            files_list = args.get("files")
            if isinstance(files_list, list):
                for entry in files_list:
                    if isinstance(entry, str):
                        _add(entry)

    return found


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
    usage_source: str = "estimated"


def _identifiers_in(value: str) -> set[str]:
    """Identifier-shaped words inside an arbitrary string."""
    cleaned = "".join(ch if (ch.isalnum() or ch == "_") else " " for ch in value)
    return {t for t in cleaned.split() if len(t) >= MIN_MENTIONED_SYMBOL_LEN and t.isidentifier()}


# Tool-call argument keys whose values name a *symbol* rather than a file or a
# sentence. A `grep(pattern=...)` or a symbol lookup is the model asking for a
# definition by name; that is the signal the ranker wants.
_SYMBOL_PARAM_KEYS = ("symbol", "name", "pattern", "query", "search", "term", "class", "func", "function", "method", "ref", "reference")


class ContextManager:
    def __init__(self, config: AppSettings) -> None:
        self.config = config
        self.token_counter = TokenCounter()
        self._aux_tokens = 0
        self._last_t0_len = 0
        self._window_estimated = False
        self._repo_map_cache: str | None = None
        self._repo_map_cache_key: int | None = None
        self._repo_map: Any | None = None
        self._repo_map_history: list[Message] = []
        # Provider-reported occupancy of a prefix of the message list currently
        # being composed. Cleared by build_messages, because a rebuilt list
        # shares no prefix with the one the provider last saw.
        self._usage_anchor: UsageAnchor | None = None

    def set_aux_tokens(self, tokens: int) -> None:
        """Set the token cost of the request parts that are not messages.

        This is the tool-schema block: it occupies the context window on every
        request yet appears in no message, so without it every occupancy figure
        is a lower bound. Callers should refresh it whenever the offered tool
        set changes.
        """
        self._aux_tokens = max(0, int(tokens))

    @property
    def aux_tokens(self) -> int:
        return self._aux_tokens

    def record_usage_anchor(self, message_count: int, tokens: int) -> None:
        """Anchor occupancy on a provider-reported request.

        ``message_count`` is the length of the list that request was built from.
        Everything before it is billed by the provider; everything after is this
        turn's own growth and is estimated on top. The current tool-schema budget
        is recorded with it so the schema block is not billed twice.
        """
        tokens = int(tokens or 0)
        if tokens <= 0:
            return
        self._usage_anchor = UsageAnchor(
            index=max(0, int(message_count)),
            tokens=tokens,
            aux_tokens=self._aux_tokens,
        )

    def clear_usage_anchor(self) -> None:
        self._usage_anchor = None

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
        # Share of the window, bounded. The map is the cheapest way to stop the
        # model opening the wrong file, and its value is in symbol density, so it
        # is worth scaling with the room available — but not linearly: past a few
        # thousand tokens the tree stops adding information and only costs
        # prefix-cache for a map nothing reads to the end of.
        context_window = self._resolve_context_window(model)
        return max(REPO_MAP_MIN_TOKENS, min(context_window // 8, REPO_MAP_MAX_TOKENS))

    def _mentioned_symbols(self, history: list[Message]) -> set[str]:
        """Identifiers the conversation has recently asked for by name.

        A file defining the symbol just named is the file the model is about to
        need, and this costs nothing to compute.

        Sourced from **structured tool-call arguments only**, not from prose.
        Harvesting every word out of the assistant's recent text looks like the
        same signal and is not: ordinary English words of eight characters or more
        — "something", "component", "handling" — all qualify, and each was worth
        a boost large enough to outrank structural centrality, so the map filled
        with whatever module happened to define a common noun. A tool call names
        the symbol deliberately; a sentence does not.
        """
        if not history:
            return set()
        found: set[str] = set()
        for msg in history[-_MENTION_SCAN_MESSAGES:]:
            for call in getattr(msg, "tool_calls", None) or []:
                args = _call_arguments(call)
                for key in _SYMBOL_PARAM_KEYS:
                    value = args.get(key)
                    if isinstance(value, str):
                        found |= _identifiers_in(value)
        return found

    def get_repo_map(
        self,
        model: str = "",
        chat_files: list[str] | None = None,
        force_refresh: bool = False,
    ) -> str:
        if not getattr(self.config, "repo_map_enabled", True):
            return ""
        if self._repo_map is None:
            from server.workspace.repo_map import RepoMap

            # Held for the manager's lifetime: a fresh instance per call threw
            # away the parsed symbol graph and the file list, so every miss paid
            # for a full tree-sitter pass over the tree.
            self._repo_map = RepoMap(self.config.workspace_root)
        repo = self._repo_map

        tokens = self._resolve_repo_map_tokens(model)
        # Keyed on the budget, not on the conversation. The map is an artefact of
        # the tree; the ranking inputs only choose its ordering. Keying on them
        # meant a miss on every turn that mentioned a new path — which is every
        # turn — so the cache this was meant to add never once hit and every
        # build_messages re-derived up to REPO_MAP_MAX_TOKENS of map.
        # `is_stale` is what re-derives on a real change: a fingerprint, a TTL,
        # or a budget change.
        if (
            not force_refresh
            and self._repo_map_cache is not None
            and self._repo_map_cache_key == tokens
            and not repo.is_stale()
        ):
            return self._repo_map_cache

        self._repo_map_cache = repo.get_repo_map(
            max_tokens=tokens,
            chat_files=chat_files,
            mentioned=self._mentioned_symbols(self._repo_map_history),
            force_refresh=force_refresh,
        )
        self._repo_map_cache_key = tokens
        repo.note_rendered()
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
        # A freshly composed list shares no prefix with whatever the provider
        # last billed, so any prior anchor is stale by construction.
        self._usage_anchor = None
        messages: list[dict] = []
        pbuf = _prompt_buffer(system_prompt)
        if repo_map is None:
            # The map is the model's only orientation on a repository it has never
            # seen, which is the first turn more than any other. It used to be
            # withheld until history existed, on the reasoning that it cost
            # tokens — but the turn that needs it most is the one with no
            # history to spend them on.
            if getattr(self.config, "repo_map_enabled", True):
                self._repo_map_history = history
                repo_map = self.get_repo_map(model, chat_files=mentioned_paths(history))
            else:
                repo_map = ""

        if use_system_prompt:
            system_tokens = self.token_counter.count(system_prompt, model)
            messages.append({"role": "system", "content": system_prompt})
            used = system_tokens
            if repo_map:
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
            if repo_map:
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
        """Whether the composed context is at or past the compaction watermark.

        Thin alias over :meth:`needs_compaction`, kept because callers and tests
        read better with this name and because the one threshold this system has
        should be reachable under one name.
        """
        return self.needs_compaction(messages, model)

    def needs_compaction(self, messages: list[dict], model: str) -> bool:
        """The single compaction predicate.

        Fires on either of two conditions, and both are needed:

        * the configured share of the window is used — the ordinary watermark;
        * the remaining headroom has fallen below what the next step needs — the
          backstop, which fires first on a small window where the share is
          generous but the absolute room is not.

        Having one predicate matters because compaction used to be triggered from
        two places that had drifted: this one tested both conditions, while the
        loop's per-iteration check tested only the share. On a small window that
        difference is the difference between compacting in time and failing the
        turn.
        """
        info = self.get_token_info(messages, model)
        if info.total <= 0:
            return False
        reserve = _adaptive_reserve(model, info.total)
        return info.used >= info.total * self.config.context_compaction_threshold or (
            info.used >= info.total - reserve
        )

    def is_context_exhausted(self, messages: list[dict], model: str) -> bool:
        total = self._resolve_context_window(model)
        if total <= 0:
            return False
        used = self.usage_tokens(messages, model)
        return used >= total * HARD_STOP_USAGE_RATIO

    def get_token_info(self, messages: list[dict], model: str) -> TokenInfo:
        usage = self.measure(messages, model)
        total = self._resolve_context_window(model)
        remaining = max(0, total - usage.tokens)
        percent = usage.tokens / total if total > 0 else 0.0
        return TokenInfo(
            used=usage.tokens,
            remaining=remaining,
            total=total,
            percent=percent,
            window_estimated=self._window_estimated,
            usage_source=usage.source,
        )

    def usage_tokens(self, messages: list[dict], model: str) -> int:
        """Composed-context occupancy in tokens."""
        return self.measure(messages, model).tokens

    def measure(self, messages: list[dict], model: str) -> ContextUsage:
        """Occupancy of one composed message list.

        Deterministic given the same inputs: the provider anchor, when one
        exists, describes a specific prefix of this exact list, and everything
        else is counted locally. Cumulative per-turn provider usage is never
        consulted — it bills every step of a turn against one number and
        describes no single message list, so using it as occupancy would make
        the threshold fire on tokens the window never held.
        """
        return self.token_counter.measure_messages(
            messages,
            model,
            anchor=self._usage_anchor,
            aux_tokens=self._aux_tokens,
        )

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
