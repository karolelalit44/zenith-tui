# Automatic Compaction — Risks, Debt, and Decisions

## Risks

- Over-aggressive summaries erase exact requirements or negative constraints.
- Concurrent turns can compact stale history or lose a live tool tail.
- Summary generation itself consumes tokens and may fail near the limit.
- Repeated summaries can drift from source truth.
- UI-only synthetic summaries can diverge from server state.

## Decisions

- Never delete raw messages as part of compaction.
- Compact complete user/assistant/tool groups only.
- Keep protected facts and source references outside free-form summary text.
- Checkpoint before replacement and retain the previous valid summary.
- One compaction lock per session; concurrent prompts either wait within a bounded window or receive a retryable status.

## Debt to address

- Current loop contains compaction, execution, and recovery responsibilities together.
- Existing thresholds and token accounting have duplicated defaults.
- Frontend compact behavior must stop fabricating conversation history.
