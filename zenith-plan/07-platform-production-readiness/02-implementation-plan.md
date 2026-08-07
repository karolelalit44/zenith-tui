# Platform Production Readiness — Implementation Plan

1. Establish baseline CI commands, deterministic fixtures, migration checks, and a release checklist.
2. Consolidate event IDs, idempotency, status transitions, retries, and cancellation across handlers/runtime/tools.
3. Harden path, shell, MCP, permission, secret-redaction, and artifact-storage boundaries.
4. Add SQLite WAL, busy-timeout, integrity checks, backup/export/import, and corruption recovery diagnostics.
5. Add structured metrics/traces and a redacted local diagnostic bundle.
6. Define resource budgets: max turn time, tool output, subprocess count, child agents, context cost, and daily/session cost.
7. Move expensive work to bounded background jobs with restart/retry semantics.
8. Run concurrency/load tests and document thresholds for local hardware.
9. Create hosted-scale ADRs for auth/tenant IDs, Postgres, object storage, and queue workers without implementing them prematurely.
