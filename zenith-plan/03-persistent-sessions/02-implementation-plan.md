# Persistent Sessions — Implementation Plan

1. Define and version `SessionSnapshot`, message/turn/execution DTOs, and sync sequence semantics.
2. Add migration/export adapters from current `sessions`, `messages`, `events_json`, checkpoints, and token tables.
3. Introduce repositories for turns, invocations, results, snapshots, and statistics.
4. Make every prompt, tool call, approval, result, cancellation, and error write an idempotent record before emitting its event.
5. Implement snapshot creation at safe boundaries and checkpoint restoration with checksum/version validation.
6. Replace resume response assembly with the snapshot builder and atomic event-tail replay.
7. Hydrate the TUI conversation/session stores from the snapshot; preserve active turn, pending question, and execution timeline.
8. Add pagination for old messages and lazy loading of large artifacts without changing logical order.
9. Add export/import and corruption diagnostics before enabling destructive schema cleanup.
