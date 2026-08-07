# Platform Production Readiness — Validation and Rollout

## Test matrix

- Unit and integration tests for every policy, transition, retry, timeout, and redaction rule.
- Property tests for event sequence/idempotency and migration round trips.
- Security tests for path traversal, shell injection, permission bypass, secret leakage, poisoned MCP/web content, and oversized payloads.
- Failure injection for provider outage, websocket drop, process kill, database lock/corruption, compaction interruption, and partial writes.
- Load tests for long sessions, large repositories, concurrent tool calls, reconnect storms, and background jobs.

## Operational targets

Define and measure p50/p95 first acknowledgement, first useful token, total turn latency, restore latency, tool latency, compaction latency, event loss/duplication, error/retry rate, token/cost variance, and memory/disk growth.

## Rollout

1. Add observability in shadow mode.
2. Enable migrations with automatic backup and rollback validation.
3. Gate new runtime paths by feature flags and retain a bounded fallback.
4. Promote after golden scenarios, security checks, and resource budgets pass.
5. Maintain a release report containing test results, schema version, migration status, metrics, known debt, and rollback instructions.

## Exit criteria

No unbounded resource path, no unauthorized mutation in adversarial tests, successful backup/restore, reproducible diagnostics, and documented SLO/resource limits for supported local environments.
