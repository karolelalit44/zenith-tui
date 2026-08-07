# Automatic Compaction — Validation and Rollout

## Tests

- Trigger at soft/proactive/hard thresholds across model window sizes.
- Preserve protected facts, tool-call ordering, pending approvals, and current task.
- Provider context error recovery compacts once and retries without duplicate tool effects.
- Compaction cancellation leaves the prior snapshot usable.
- Repeated compaction remains semantically stable against source fixtures.
- Restart during summary generation or persistence recovers from checkpoint.

## Evaluation

- Tokens before/after and compaction cost.
- Task success and exact-constraint retention versus full-history baseline.
- Summary drift and retrieval hit rate over repeated compactions.
- p95 compaction latency and user-visible interruption time.

Roll out in observe-only mode, then automatic read-only compaction, then mutating workflows after recovery and correctness gates pass.
