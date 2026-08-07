# Persistent Sessions — Validation and Rollout

## Tests

- Create, prompt, stream, tool execute, cancel, checkpoint, close, restart, and resume.
- Resume during each lifecycle state, including pending approval, clarification, compaction, retry, and failed tool.
- Reconnect with missing, duplicate, and out-of-order sync events.
- Snapshot checksum/version failure falls back to a prior checkpoint plus event tail.
- Existing database migration and export/import round trips preserve IDs, order, content, and timestamps.
- Large artifacts remain retrievable while UI payloads stay bounded.

## Metrics and gates

- Restore latency by session size and snapshot age.
- Replay count, duplicate-event suppression, interrupted-run recovery rate.
- Snapshot size, creation latency, checksum failures, and migration failures.
- No loss or reorder of messages in golden snapshot comparisons.

Roll out snapshot hydration behind a protocol version flag, compare old/new resume projections, then make the new snapshot authoritative after parity is proven.
