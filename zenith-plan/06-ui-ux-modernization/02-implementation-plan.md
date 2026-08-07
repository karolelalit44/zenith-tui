# UI/UX Modernization — Implementation Plan

1. Inventory screens/components and map all websocket events to a typed reducer.
2. Add `SessionSnapshot` hydration and replace local-only resume/compact behavior.
3. Standardize status, error, loading, empty, cancellation, and retry components.
4. Build execution timeline rows for tool calls/results, approvals, compaction, retries, and tests.
5. Add session detail statistics and artifact panels with bounded output and expand/load actions.
6. Implement clarification cards and pending-work indicators.
7. Improve streaming stability, scroll anchoring, resize behavior, and perceived latency feedback.
8. Apply keyboard navigation, focus states, contrast, reduced-motion, and readable fallback text.
9. Conduct scenario-based usability review and prioritize quick wins before visual redesign.

## Priority roadmap

- Quick wins: consistent statuses, resume hydration, execution visibility, context meter accuracy, error recovery text.
- Medium term: session detail, searchable timeline, artifacts/diffs, clarification cards, token/cost drill-down.
- Long term: richer workspace explorer/editor/preview surfaces only after product scope and performance budgets are approved.
