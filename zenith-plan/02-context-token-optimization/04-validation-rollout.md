# Context and Token Optimization — Validation and Rollout

## Test scenarios

- Short chat with no retrieval overhead.
- Hundreds of turns with an early constraint referenced near the end.
- Decision changed multiple times; only the latest valid decision should drive execution.
- Large shell/test outputs stored by reference with relevant failure lines retrievable.
- Tool-call groups near a context boundary remain protocol-valid.
- Different model windows and output reserves produce valid plans.
- Corrupt/missing summary falls back without losing raw history.
- Workspace isolation prevents memory leakage.

## Quality evaluation

- Exact fact and constraint retention.
- Correct current-task and pending-action reconstruction.
- Retrieval precision/recall on tagged fixtures.
- End-task success compared with full-history reference runs.
- Summary drift after repeated compactions.

## Operational metrics

- Input tokens by context layer.
- Estimated-versus-reported token error.
- Retrieval latency and hit/use rate.
- Summary generation latency, cost, and failure rate.
- Cache read/write tokens and effective savings.
- Context budget rejections and provider context-limit errors.

## Rollout and gates

1. Persist context plans in observation mode while existing assembly remains authoritative.
2. Enable layered budgets and complete-turn selection.
3. Enable session-scoped FTS retrieval.
4. Enable structured memory injection with user visibility.
5. Enable cross-session workspace memory only after isolation and forget tests.

Release requires lower median input tokens with no material regression in long-session task success, bounded p95 assembly latency, and zero cross-workspace retrieval in isolation tests.
