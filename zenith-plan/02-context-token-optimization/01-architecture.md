# Context and Token Optimization — Architecture

## Context layers

Allocate tokens in priority order:

1. Non-negotiable system, safety, and mode policy.
2. Current user prompt and required output reserve.
3. Active task/plan, approvals, and unresolved clarification state.
4. Recent complete turns and in-flight tool groups.
5. Structured rolling summary.
6. Retrieved session/project memory and relevant historical evidence.
7. Repository map and attached file excerpts.
8. Optional enrichment that may be dropped under pressure.

## Components

- `ModelBudgetResolver`: resolves effective context, output reserve, tokenizer, and provider overhead.
- `ContextAssembler`: produces a deterministic `ContextPlan`.
- `HistoryRetriever`: queries FTS initially and optional embeddings later.
- `MemoryExtractor`: creates structured facts with provenance, scope, confidence, and lifecycle.
- `SummaryRepository`: versions hierarchical summaries and covered message ranges.
- `UsageLedger`: records estimates, reported tokens, cache usage, reasoning tokens, latency, and cost.

## Contracts

```text
ContextPlan
  id, session_id, turn_run_id, model, budget
  estimated_tokens, reserve_tokens
  included_items[], omitted_items[], summary_version

ContextItem
  source_type, source_id, priority, estimated_tokens
  inclusion_reason, truncation, provenance

MemoryItem
  id, workspace_id, session_id?, kind
  content, source_message_ids[], confidence
  pinned, superseded_by?, created_at, last_used_at
```

## Retrieval

- Query recent prompt, active task, mentioned symbols/files, current errors, and pending work.
- Filter by workspace and session before ranking.
- Rank by textual relevance, recency, explicit pinning, decision/task importance, and prior successful reuse.
- Retrieve small evidence passages, not entire messages or files by default.
- Attach source IDs so the runtime can fetch full evidence if needed.
- Add embeddings only behind a `HistoryRetriever` adapter and only after benchmarked improvement over FTS/hybrid ranking.

## Predictability

- Reserve output/tool-loop capacity before adding optional context.
- Apply per-layer soft and hard budgets.
- Cache stable prefixes where provider support is verified.
- Record estimated versus actual usage per request and continuously calibrate overhead.
