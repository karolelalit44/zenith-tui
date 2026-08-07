# Platform Production Readiness — Risks, Debt, and Decisions

## Risks

- Local SQLite locking and long-running subprocesses can block the event loop.
- Provider retries can duplicate charges or side effects.
- Logs and exports can leak source code, credentials, or private prompts.
- Unbounded output, memory, or child agents can exhaust local resources.
- Broad refactors may conflict with the repository’s existing uncommitted changes.

## Decisions

- Preserve user data before schema cleanup through migration/export.
- Treat provider usage and billing as externally reported facts; mark estimates explicitly.
- Default to deny for destructive/network/credential operations until policy grants access.
- All background jobs have ownership, timeout, retry, cancellation, and cleanup rules.
- Use additive/versioned event and snapshot contracts even though internal implementation may be redesigned.

## Debt register

- Overlapping persistence/repository APIs and legacy dead-code clusters need staged removal.
- Some known tests depend on persisted environment state and Windows MCP subprocess behavior; classify these separately from product regressions.
- Raw FTS SQL remains an intentional bounded exception and needs dedicated migration/integrity tests.
