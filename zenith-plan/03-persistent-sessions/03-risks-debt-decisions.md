# Persistent Sessions — Risks, Debt, and Decisions

## Risks

- Replaying events after a reconnect can duplicate UI effects or tool side effects.
- Snapshots may be inconsistent if written while a streamed turn is active.
- Existing databases may contain partially persisted messages or legacy JSON shapes.
- Large tool results can make SQLite slow and backups unwieldy.
- Session deletion and workspace deletion have different retention expectations.

## Decisions

- Persist state before publishing replayable events.
- Use monotonic per-session sequences and idempotency keys.
- Never re-execute a tool during restoration; recover its recorded status or mark it interrupted.
- Snapshot only at turn/tool/checkpoint boundaries; active work is represented by the append-only tail.
- Keep raw records until export/retention policy explicitly removes them.

## Debt register

- Frontend `SessionSummary` omits provider/model/cost/context/error fields.
- Session service has a broad interface with legacy methods that should converge behind snapshot/query services.
- `metadata_json` serialization must be canonical JSON, not Python `str(dict)`.
- Event payload schemas require versioning and validation.
