# Automatic Compaction — Architecture

## Trigger policy

Resolve model-specific effective window and reserve. Default soft warning is 70%, proactive compaction 80%, mandatory compaction near 90% or before the next request cannot fit. Provider context errors trigger one bounded recovery compaction and retry.

## Pipeline

1. Acquire a per-session compaction lock and emit start event.
2. Save a checkpoint and context plan.
3. Choose complete historical turn groups outside the protected recent tail.
4. Extract structured protected facts and unresolved work.
5. Generate a schema-constrained summary referencing source message ranges.
6. Extract/supersede memory items and trim oversized tool results into blob references.
7. Persist `compaction_run`, summary version, snapshot, and covered range atomically.
8. Rebuild context through `ContextAssembler`; append live tail if any.
9. Emit end event with before/after usage, saved tokens, and summary IDs.

## Summary schema

```text
objective, constraints, decisions, current_state,
files_changed, commands_and_tests, failures,
pending_actions, approvals, user_preferences,
open_questions, source_message_ids
```

Summaries are hierarchical: turn summaries feed a session summary; only a bounded session summary enters normal context.
