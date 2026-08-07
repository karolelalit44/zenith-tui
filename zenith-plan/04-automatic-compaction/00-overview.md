# Automatic Compaction — Overview

## Objective

Keep long-running sessions usable without manual intervention while preserving goals, constraints, decisions, changed files, test outcomes, errors, approvals, and pending work.

## Current state

- The backend has adaptive thresholds, summarization, tool-output trimming, context events, and retry-after-context-error logic.
- The loop keeps a process-local summary and rebuilds messages after compaction.
- The TUI manual compact action replaces local turns with a synthetic display turn and calls a backend endpoint, creating divergent state.
- Compaction records and protected facts are not yet a complete durable pipeline.

## Scope

Trigger policy, protected-state extraction, hierarchical summaries, tool-output references, checkpoints, notifications, cancellation/recovery, and compaction metrics.

## Success

Compaction starts before hard limits, preserves task correctness on benchmark sessions, is visible but non-disruptive, and can be inspected or recovered after restart.
