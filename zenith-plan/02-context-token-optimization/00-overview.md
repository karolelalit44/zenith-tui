# Context and Token Optimization — Overview

## Objective

Keep long conversations accurate while making per-request context bounded, relevant, explainable, and cost-predictable.

## Current state

- `ContextManager` computes model windows, reserves output capacity, injects system/project/memory blocks, and takes recent history until the budget fills.
- Token counting supports provider usage with local estimation fallback.
- Repo-map and memory injection exist, as do FTS-backed message/session search primitives.
- The active summary lives on an agent loop instance and is not a complete durable context snapshot.
- History selection is primarily recent-tail inclusion; older relevant decisions are not systematically retrieved.
- Context composition decisions and omissions are not persisted for audit or reproducibility.

## Scope

- Durable raw history separated from ephemeral model context.
- Layered context assembly, token budgets, retrieval, memory, summaries, and provenance.
- Predictable cost/latency controls and model-specific accounting.
- Interfaces consumed by orchestration, compaction, sessions, clarification, and UI.

## Success criteria

- Every provider request stays within its effective context and output reserve.
- Old but relevant goals, decisions, files, and failures can return through retrieval.
- The system explains what context was included, summarized, retrieved, or omitted.
- Raw conversation remains intact regardless of request pruning.
- Token/cost estimates reconcile with provider-reported usage and identify estimation uncertainty.
