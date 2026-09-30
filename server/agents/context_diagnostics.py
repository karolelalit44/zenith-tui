"""Per-turn measurement of how context is actually being spent.

Every number here exists because it can change a decision. A metric nobody
acts on is instrumentation debt, so this module is deliberately short and every
field answers one of three questions:

* **Is compaction saving anything, or just moving the cost?** ``reinvocation_rate``
  is the check. Compressing a tool result that the model then re-runs buys
  nothing: the tokens come back plus a second round trip. Static truncation has
  been measured *increasing* total tokens for exactly this reason, and a
  pass/fail score cannot see it.
* **Where are the tokens going?** ``ladder_saved_tokens`` and
  ``dedup_saved_tokens`` attribute savings to the mechanism that produced them,
  so a change that trades one against the other is visible rather than inferred.
* **Can we trust the occupancy number?** ``usage_source`` and ``tool_tokens``
  say whether occupancy was measured or estimated and what the tool-schema block
  contributed. A gauge that silently excludes the schema block reads low and
  cannot be compared across changes.

This module is the *producer*: it accumulates one turn and hands the deltas to
the caller. The consumer that folds them across a session lives with the rows it
reads, in ``server.storage.usage_store``, so that storage never has to import
the agent layer to interpret what the agent layer wrote.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ContextDiagnostics:
    """Accumulates one turn's context measurements.

    One instance per turn. The session-level view is assembled from persisted
    rows, so nothing here needs to outlive the turn that produced it.
    """

    tool_calls: int = 0
    reinvocations: int = 0
    ladder_saved_tokens: int = 0
    dedup_saved_tokens: int = 0
    folds: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    prompt_tokens: int = 0
    _signatures: set[tuple[str, str]] = field(default_factory=set, repr=False)

    def record_tool_call(self, tool_name: str, signature: str) -> bool:
        """Count one executed tool call; report whether it repeated earlier work.

        The signature set is deliberately *not* invalidated the way the loop's
        duplicate-suppression set is. That set forgets search and shell calls on
        a mutation so a re-run after a change stays allowed; a diagnostic that
        forgot the same calls could not see the re-runs it exists to count.
        """
        self.tool_calls += 1
        key = (tool_name, signature)
        repeated = key in self._signatures
        if repeated:
            self.reinvocations += 1
        self._signatures.add(key)
        return repeated

    def record_ladder_savings(self, tokens: int) -> None:
        self.ladder_saved_tokens += max(0, int(tokens or 0))

    def record_dedup_savings(self, tokens: int) -> None:
        self.dedup_saved_tokens += max(0, int(tokens or 0))

    def record_fold(self) -> None:
        self.folds += 1

    def record_cache_usage(self, cumulative: dict[str, Any] | None) -> None:
        """Snapshot the provider's cumulative cache counters for the turn."""
        if not isinstance(cumulative, dict):
            return
        self.cache_read_tokens = int(cumulative.get("cached_tokens", 0) or 0)
        self.cache_write_tokens = int(cumulative.get("cache_creation_tokens", 0) or 0)
        self.prompt_tokens = int(cumulative.get("prompt_tokens", 0) or 0)

    @property
    def reinvocation_rate(self) -> float:
        if self.tool_calls <= 0:
            return 0.0
        return round(self.reinvocations / self.tool_calls, 4)

    @property
    def cache_hit_rate(self) -> float:
        """Share of billed prompt tokens the provider served from cache.

        Cache reads count against the context window, so a low rate here is a
        direct cost, not just a cost — it is the number that tells you whether
        the layout's stable prefix is actually stable.
        """
        if self.prompt_tokens <= 0:
            return 0.0
        return round(self.cache_read_tokens / self.prompt_tokens, 4)

    def as_dict(self) -> dict[str, Any]:
        """The subset worth persisting on a usage row.

        Cumulative-per-turn values are recorded here and re-derived across rows
        by the session view, so what is stored has to be a *delta*, not a
        running total. Storing the total would make a session-wide sum wrong.
        """
        return {
            "tool_calls": self.tool_calls,
            "reinvocations": self.reinvocations,
            "ladder_saved_tokens": self.ladder_saved_tokens,
            "dedup_saved_tokens": self.dedup_saved_tokens,
            "folds": self.folds,
            "cache_hit_rate": self.cache_hit_rate,
        }
