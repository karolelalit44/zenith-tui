# Context and Token Optimization — Risks, Debt, and Decisions

## Key complications

- Tokenizers and provider accounting differ; local counts are estimates until reconciled.
- Retrieval may return outdated decisions or poisoned tool content.
- Summaries can omit negative constraints, pending failures, or who made a decision.
- Project memory may leak information between unrelated workspaces if scoping is weak.
- Prefix caching reduces billed input only for some providers and request shapes.

## Existing debt

- Summary state is attached to a runtime object rather than persisted by session/version.
- Repo-map and memory caches lack robust invalidation semantics.
- Recent-tail selection stops at the first over-budget message and can underuse remaining budget.
- Tool output is represented as formatted message text rather than structured references.
- Frontend token totals mix provider usage and local event estimates.

## Decisions

- Durable history is immutable; pruning changes only a context plan.
- FTS plus structured memory is the default retrieval strategy.
- Cross-session memory requires explicit workspace scoping and user controls.
- Protected facts must be structured and source-linked, not entrusted only to free-form summaries.
- Context plans and summaries are versioned artifacts.
- Provider-reported usage is authoritative for billing; estimates remain visible for planning and diagnostics.

## Failure handling

- Retrieval unavailable: use summary plus recent complete turns.
- Summary generation fails: keep raw history and reduce optional context; never overwrite the prior valid summary.
- Count uncertainty near limit: apply a larger safety margin.
- Conflicting memories: prefer latest explicit user decision, mark older items superseded, and surface ambiguity if material.
