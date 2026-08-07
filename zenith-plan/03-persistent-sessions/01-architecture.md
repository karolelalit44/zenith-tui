# Persistent Sessions — Architecture

## Source of truth

Use an append-oriented record of user messages, assistant messages, tool invocations/results, lifecycle events, token usage, checkpoints, summaries, memory, and clarification records. Derived counters and snapshots are rebuildable projections.

## Snapshot contract

```text
SessionSnapshot
  schema_version, session, messages[], turns[], executions[]
  context_state, summaries[], memory[], clarification?
  statistics, latest_sequence, restored_from_checkpoint?
```

`messages` preserves display order. `turns` groups one prompt and all streamed/tool activity. `executions` provides a queryable timeline without forcing the UI to decode arbitrary event payloads.

## Restoration flow

1. Validate session ownership/workspace and load metadata.
2. Register the websocket/event subscription before replay.
3. Load the latest valid snapshot/checkpoint.
4. Apply the append-only tail after the snapshot sequence.
5. Rebuild derived context and runtime state; mark interrupted runs as recoverable/aborted according to their last durable status.
6. Return the complete versioned snapshot plus latest sequence.
7. Frontend replaces its local projection atomically and begins incremental event application.

## Database concerns

Add normalized tables for `turn_runs`, `tool_invocations`, `tool_results`, `context_snapshots`, `context_summaries`, `memory_items`, and clarification state. Keep large content in blob storage with checksums, previews, and retention metadata. Add composite indexes by session and sequence/time.

## Statistics

Compute authoritative aggregates from token usage and execution records; cache them on sessions only as rebuildable projections. Distinguish prompt, completion, reasoning, cache, estimated, retry, and billed totals.
