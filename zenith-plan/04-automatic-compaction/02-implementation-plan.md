# Automatic Compaction — Implementation Plan

1. Extract threshold/reserve calculation into a policy object with model overrides and configuration validation.
2. Add compaction locks, durable run records, checkpoints, source ranges, and summary versions.
3. Implement protected-fact extraction and schema-constrained summary generation.
4. Replace process-local loop summary with session-loaded summary state.
5. Make tool-output trimming produce durable artifact references and searchable previews.
6. Unify automatic and manual compact commands so both call the same backend pipeline.
7. Add progress/cancellation/recovery events and resume behavior for interrupted compaction.
8. Add retention and rebuild commands for summaries/memory from raw history.
