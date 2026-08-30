from __future__ import annotations

# Architecture decision (Phase 8): Arch 1 — Rolling window + running summary.
# T0 (static system prompt + minimal tool schemas, ~2991 sys + ~3600 schemas),
# T2 (running summary ≤ 1K), T4 (rolling window ≤ 2.4K, last 2–3 turns),
# T5 (user prompt verbatim ~200). Bounded at ≤ 6.6K worst-case continuation
# tokens on a 128K window. Alternatives (Arch 2–4) considered and rejected.
import logging
import math
import os
from dataclasses import dataclass

from server.config.constants import (
    BUILD_MODE,
    CHARS_PER_TOKEN,
    DEFAULT_CONTEXT_WINDOW,
    FILE_READ_TOOL,
    HARD_STOP_USAGE_RATIO,
    LARGE_CONTEXT_WINDOW,
    MIN_OUTPUT_RESERVE_TOKENS,
    MODE_BUDGET_PROFILES,
    SESSION_STATE_MARKER,
    STALE_TOKEN_MULTIPLIER,
    SUMMARY_FRAMING_TOKENS,
)
from server.config.settings import AppSettings
from server.domain.message import Message
from server.providers.token_counter import TokenCounter
from server.storage.catalog_compat import load_catalog

logger = logging.getLogger(__name__)

_E2E_INSTRUMENT = bool(os.environ.get("ZENITH_E2E_INSTRUMENT", ""))

_req_seq = 0

TIER_T0 = "T0"
TIER_T1 = "T1"
TIER_T2 = "T2"
TIER_T4 = "T4"
TIER_T5 = "T5"


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


def _extract_tool_read_path(content: str) -> str | None:
    """Extract the file path from a ``[Tool: file_read ...]`` result message.

    Returns ``None`` when the message is not a file_read tool result or when
    the path cannot be parsed.
    """
    if not content.startswith("[Tool:"):
        return None
    first_line = content.split("\n", 1)[0]
    if FILE_READ_TOOL not in first_line:
        return None
    lines = content.split("\n")
    if len(lines) >= 2:
        candidate = lines[1].strip()
        if candidate and not candidate.startswith("["):
            return candidate
    return None


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
    return reserve


@dataclass
class HistoryEntry:
    """Enriched representation of a single history message for scoring."""

    message: dict
    tokens: int
    role: str
    is_error: bool = False
    is_stale: bool = False
    is_tool_result: bool = False
    turn_index: int = 0


def score_entry(entry: HistoryEntry, current_turn: int, total_turns: int) -> float:
    """Compute an eviction fitness score for a history entry.

    Higher score = more likely to survive eviction. The formula rewards errors
    (which outlive successes) and penalises stale reads and large payloads.
    """
    score = 100.0
    recency = current_turn - entry.turn_index
    score -= recency * 4
    if entry.is_error:
        score += 40
    if entry.is_stale:
        score -= 60
    score -= math.log2(max(entry.tokens, 1)) * 3
    return score


@dataclass
class TokenBreakdown:
    """Deterministic per-tier token accounting of a composed message list.

    Buckets mirror the context tiers: ``system`` (T0 static prefix), ``state``
    (session-state block), ``summary`` (T2 pair incl. the ack message), ``handoff``
    (repo map / memory / plan volatile blocks), ``window`` (T4 history minus tool
    results), ``user`` (T5 verbatim prompt) and ``tools`` (T4 tool-result messages).

    Counts use the ``CHARS_PER_TOKEN`` heuristic plus per-message framing tokens so
    they are reproducible regardless of tiktoken availability.
    """

    system: int = 0
    state: int = 0
    summary: int = 0
    handoff: int = 0
    window: int = 0
    user: int = 0
    tools: int = 0

    @property
    def volatile(self) -> int:
        return self.state + self.summary + self.handoff + self.window

    @property
    def total(self) -> int:
        return self.system + self.volatile + self.user + self.tools

    def to_dict(self) -> dict[str, int]:
        return {
            "system": self.system,
            "state": self.state,
            "summary": self.summary,
            "handoff": self.handoff,
            "window": self.window,
            "user": self.user,
            "tools": self.tools,
        }


@dataclass
class TokenBudget:
    window: int
    reserve_output: int
    input_budget: int
    breakdown: TokenBreakdown

    @property
    def used(self) -> int:
        return self.breakdown.total


@dataclass
class TokenInfo:
    used: int
    remaining: int
    total: int
    percent: float
    window_estimated: bool = False


_REPO_MAP_INSTANCES: dict[str, object] = {}


def _get_repo_map_instance(workspace_root: str, refresh: str = "files"):
    key = f"{workspace_root}|{refresh}"
    repo = _REPO_MAP_INSTANCES.get(key)
    if repo is None:
        from server.workspace.repo_map import RepoMap

        repo = RepoMap(workspace_root, refresh=refresh)
        _REPO_MAP_INSTANCES[key] = repo
    return repo


class ContextManager:
    def __init__(self, config: AppSettings) -> None:
        self.config = config
        self.token_counter = TokenCounter()
        self._repo_map_cache: str | None = None
        self._aux_tokens = 0
        self._last_t0_len = 0
        self._last_tiers: list[str] = []
        self._last_stale_count = 0
        self._window_estimated = False

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
        if self.config.repo_map_tokens is not None:
            return self.config.repo_map_tokens
        ctx = self._resolve_context_window(model)
        return min(1024, max(400, ctx // 32))

    def get_repo_map(self, chat_files: list[str] | None = None, model: str = "cl100k_base") -> str:
        if not self.config.repo_map_enabled:
            return ""
        if self._repo_map_cache is not None:
            return self._repo_map_cache
        try:
            repo = _get_repo_map_instance(self.config.workspace_root, refresh="files")
            self._repo_map_cache = repo.get_repo_map(
                chat_files=chat_files, max_tokens=self._resolve_repo_map_tokens(model)
            )
        except Exception as e:
            logger.warning("Failed to build repo map: %s", e)
            self._repo_map_cache = ""
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
        # Mode-aware tier budgets (Gap #8): the history tier gets a per-mode
        # share of the input budget so investigation modes retain more
        # conversation context and read-only mode trims the tool-schema spend.
        profile = MODE_BUDGET_PROFILES.get(mode, MODE_BUDGET_PROFILES[BUILD_MODE])
        history_budget = int(budget * profile["history_pct"])
        self._last_t0_len = 1 if use_system_prompt else 0
        self._last_tiers = []
        messages: list[dict] = []
        pbuf = _prompt_buffer(system_prompt)
        repo_map_text = repo_map if repo_map is not None else ""
        repo_map_block = (
            f"<repo_map>\n{repo_map_text}\n</repo_map>" if repo_map_text.strip() else ""
        )
        repo_map_tokens = self.token_counter.count(repo_map_block, model) if repo_map_block else 0
        if use_system_prompt:
            system_tokens = self.token_counter.count(system_prompt, model)
            messages.append({"role": "system", "content": system_prompt})
            self._last_tiers.append(TIER_T0)
            used = system_tokens
        else:
            used = 0
        # Message 1 (fresh session bucket): outbound is exactly T0 (static) +
        # T5 (verbatim prompt). No repo map, no memory, no plan, no summary,
        # no history, no session state. A resumed session (history or summary
        # present) keeps the volatile blocks (design §3.1).
        is_fresh = not history and not summary
        if use_system_prompt:
            if repo_map_block and not is_fresh:
                messages.append({"role": "system", "content": repo_map_block})
                self._last_tiers.append(TIER_T1)
                used += repo_map_tokens
                logger.info(
                    "Repo map injected into context: %d chars, %d tokens",
                    len(repo_map_text),
                    repo_map_tokens,
                )
        else:
            if not is_fresh:
                used += repo_map_tokens
        if plan_block and not is_fresh:
            plan_tokens = self.token_counter.count(plan_block, model)
            if used + plan_tokens + pbuf <= budget:
                messages.append(
                    {
                        "role": "system",
                        "content": f"<plan_to_execute>\n{plan_block}\n</plan_to_execute>\n\nYou MUST execute the plan above exactly. Create every file listed, implement every component, and follow the architecture decisions described. The user's latest message is the authoritative intent: if it conflicts with this plan, follow the latest message and say what you changed.",
                    }
                )
                self._last_tiers.append(TIER_T1)
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
            if used + summary_tokens <= budget:
                # Inject as a system block (not a fake assistant "Understood."
                # turn) so it neither pollutes the transcript/history nor breaks
                # user/assistant role alternation before the real user prompt.
                messages.append(
                    {"role": "system", "content": f"[Previous conversation summary]\n{summary}"}
                )
                self._last_tiers.append(TIER_T2)
                used += summary_tokens + SUMMARY_FRAMING_TOKENS
        history_entries: list[HistoryEntry] = []
        last_key: tuple[str, str] | None = None
        stale_count = 0
        turn_counter = 0
        # Map a tool result to the turn of its owning assistant tool-call
        # message (the most recent preceding assistant entry with tool_calls).
        # A tool result whose owner is evicted is an orphan and must be dropped.
        owner_turn_by_entry: dict[int, int | None] = {}
        _last_assistant_toolcall_turn: int | None = None
        for msg in history:
            if msg.role == "assistant" and (not msg.content) and (not msg.has_tool_calls):
                continue
            if msg.role == "user" and not str(msg.content or "").startswith("[Tool:"):
                continue
            key = (msg.role, msg.content)
            if key == last_key:
                continue
            last_key = key
            entry_dict = {"role": msg.role, "content": msg.content}
            entry_tokens = self.token_counter.count(msg.content, model)
            # A tool result arrives two ways in persisted history: the live form
            # (role=user, content prefixed ``[Tool:``) and the legacy form
            # (role="tool"). Both are tool outputs. A ``role="tool"``/``[Tool:``
            # entry that follows a plain user prompt (no assistant tool-call
            # in between) is kept as-is; only those whose owning assistant
            # tool-call message is evicted are dropped.
            is_tool = msg.role == "tool" or (
                msg.role == "user"
                and isinstance(msg.content, str)
                and msg.content.startswith("[Tool:")
            )
            if msg.role == "assistant" and msg.has_tool_calls:
                _last_assistant_toolcall_turn = turn_counter + 1
            is_stale = False
            is_error = msg.role == "tool" or (
                msg.role == "user"
                and isinstance(msg.content, str)
                and "Status: ERROR" in msg.content
            )
            if session_id and is_tool:
                path = _extract_tool_read_path(msg.content)
                if path:
                    from server.agents.session_workspace import is_stale as _is_stale

                    if _is_stale(session_id, path):
                        entry_tokens *= STALE_TOKEN_MULTIPLIER
                        is_stale = True
                        stale_count += 1
            turn_counter += 1
            owner_turn_by_entry[turn_counter] = _last_assistant_toolcall_turn
            history_entries.append(
                HistoryEntry(
                    message=entry_dict,
                    tokens=entry_tokens,
                    role=msg.role,
                    is_error=is_error,
                    is_stale=is_stale,
                    is_tool_result=is_tool,
                    turn_index=turn_counter,
                )
            )
        self._last_stale_count = stale_count
        if stale_count:
            logger.info(
                "Staleness detection: %d stale file reads in history (penalty applied)", stale_count
            )
        total_turns = max(turn_counter, 1)
        current_turn = total_turns
        for he in history_entries:
            he._score = score_entry(he, current_turn, total_turns)
        scored = sorted(history_entries, key=lambda e: e._score, reverse=True)
        included: list[HistoryEntry] = []
        evicted_count = 0
        evicted_tokens = 0
        for entry in scored:
            if used + entry.tokens + pbuf > history_budget:
                # Budget eviction (P6.3): counted and logged so per-turn prompt
                # token changes are explainable instead of silent.
                evicted_count += 1
                evicted_tokens += entry.tokens
                continue
            included.append(entry)
            used += entry.tokens
        if evicted_count:
            logger.info(
                "Context budget eviction: %d history entr%s (%d tokens) excluded by score",
                evicted_count,
                "y" if evicted_count == 1 else "ies",
                evicted_tokens,
            )
        included.sort(key=lambda e: e.turn_index)
        # Drop tool results whose owning assistant tool-call message was evicted
        # (they are meaningless on their own and mislead the model). Tool results
        # without a tool-call owner (e.g. following a plain user prompt) are kept.
        owner_included = {e.turn_index for e in included}
        emitted: list[HistoryEntry] = []
        for entry in included:
            owner = owner_turn_by_entry.get(entry.turn_index)
            if entry.is_tool_result and owner is not None and owner not in owner_included:
                logger.info(
                    "Dropping orphaned tool result (owning assistant tool-call evicted): turn %d",
                    entry.turn_index,
                )
                continue
            emitted.append(entry)
        messages.extend(e.message for e in emitted)
        self._last_tiers.extend([TIER_T4] * len(emitted))
        if not use_system_prompt:
            parts = [system_prompt]
            if repo_map_block:
                parts.append(repo_map_block)
            parts.append(new_prompt)
            new_entry = {"role": "user", "content": "\n\n".join(parts)}
        else:
            new_entry = {"role": "user", "content": new_prompt}
        if not messages or not (
            messages[-1].get("role") == "user"
            and messages[-1].get("content") == new_entry.get("content")
        ):
            messages.append(new_entry)
            self._last_tiers.append(TIER_T5)
        _instrument(messages, model)
        return messages

    def t0_len(self) -> int:
        """Number of leading messages forming the byte-stable T0 prefix.

        T0 holds only the static system prompt; volatile blocks (repo map,
        memory, plan, summary, history, session state) live strictly after it.
        """
        return self._last_t0_len

    def tiers(self) -> list[str]:
        """Tier label per message from the last ``build_messages`` call.

        Ordering guarantee: every non-T0 tier sits after the cache boundary
        (index ``t0_len()``), and the final entry is T5 — the verbatim user
        prompt. Repo map, memory, plan, summary and session-state blocks are
        all tagged volatile and therefore never part of the T0 prefix.
        """
        return list(self._last_tiers)

    def tier_boundaries(self) -> dict[str, int]:
        """Index where each tier ends (exclusive) in the message array.

        Keys: ``t0_end``, ``t1_end``, ``t2_end``, ``t4_end``.
        A value of 0 means the tier is absent.
        """
        tiers = self._last_tiers
        boundaries: dict[str, int] = {"t0_end": 0, "t1_end": 0, "t2_end": 0, "t4_end": 0}
        last_seen: dict[str, int] = {}
        for i, t in enumerate(tiers):
            last_seen[t] = i + 1
        boundaries["t0_end"] = last_seen.get(TIER_T0, 0)
        boundaries["t1_end"] = last_seen.get(TIER_T1, 0)
        boundaries["t2_end"] = last_seen.get(TIER_T2, 0)
        boundaries["t4_end"] = last_seen.get(TIER_T4, 0)
        return boundaries

    def should_summarize(self, messages: list[dict], model: str, provider=None) -> bool:
        used = self.usage_tokens(messages, model, provider)
        max_tokens = self._resolve_context_window(model)
        watermark = max_tokens * self.config.context_compaction_threshold
        reserve = _adaptive_reserve(model, max_tokens)
        return used >= watermark or used >= max_tokens - reserve

    def is_context_exhausted(self, messages: list[dict], model: str, provider=None) -> bool:
        total = self._resolve_context_window(model)
        if total <= 0:
            return False
        used = self.usage_tokens(messages, model, provider)
        return used >= total * HARD_STOP_USAGE_RATIO

    def get_token_info(self, messages: list[dict], model: str, provider=None) -> TokenInfo:
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

    def usage_tokens(self, messages: list[dict], model: str, provider=None) -> int:
        """Composed-context occupancy (alias of :meth:`usage_tokens_composed`).

        The ``provider`` argument is accepted for call-site compatibility but is
        intentionally ignored: cumulative provider usage is *run/API usage*, not
        context occupancy, and must never drive compaction or the context gauge.
        """
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
        """Deterministic per-tier token accounting for a composed message list.

        Bucketing is content-marker driven so it stays correct even when a block
        (e.g. session state) is injected after ``build_messages`` has returned.
        """
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
                    breakdown.state += tokens
                else:
                    breakdown.handoff += tokens
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
                breakdown.window += tokens
        return breakdown

    def get_token_budget(self, messages: list[dict], model: str) -> TokenBudget:
        window = self._resolve_context_window(model)
        reserve = _adaptive_reserve(model, window)
        return TokenBudget(
            window=window,
            reserve_output=reserve,
            input_budget=max(0, window - reserve),
            breakdown=self.token_breakdown(messages),
        )
