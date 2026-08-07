# Zenith Plan — Priority, Dependencies, and Execution Sequence

This document defines the order in which the seven Zenith workstreams should be audited, designed, implemented, and validated. The order is based on architectural dependency, data ownership, risk, and user value.

## Priority model

| Priority | Workstream | Why this priority |
|---|---|---|
| P0 | Foundation and production-readiness controls | Every other workstream needs stable contracts, observability, migration safety, limits, and validation gates. |
| P1 | Persistent sessions | Sessions are the durable source of truth for messages, runs, tools, context, clarification, and UI restoration. |
| P1 | Context and token optimization | The agent runtime and compaction pipeline need a deterministic context budget and retrieval contract. |
| P1 | Tool orchestration | Automatic tool selection is the core product behavior and depends on turn/run persistence and context budgeting. |
| P2 | Automatic compaction | Compaction depends on durable summaries, context plans, checkpoints, and token accounting. |
| P2 | Intelligent clarification | Clarification depends on persisted turn state, event contracts, and execution gating, but can be developed in parallel after contracts are defined. |
| P3 | UI/UX modernization | The UI should project stable backend snapshots/events; large-scale UI work before those contracts would be repeatedly rewritten. |

Detailed workstream books:

- [Tool orchestration](01-tool-orchestration/00-overview.md)
- [Context and token optimization](02-context-token-optimization/00-overview.md)
- [Persistent sessions](03-persistent-sessions/00-overview.md)
- [Automatic compaction](04-automatic-compaction/00-overview.md)
- [Intelligent clarification](05-intelligent-clarification/00-overview.md)
- [UI/UX modernization](06-ui-ux-modernization/00-overview.md)
- [Platform production readiness](07-platform-production-readiness/00-overview.md)

## Dependency graph

```text
P0 Foundation / contracts / observability / migration safety
                    |
                    v
P1 Persistent sessions -----> P1 Context and token optimization
          |                              |
          |                              v
          +-----------------------> P1 Tool orchestration
                                         |
                                         v
                                  P2 Automatic compaction
                                         |
P1 session/event contracts --------------+
          |
          v
   P2 Intelligent clarification
          |
          v
   P3 UI/UX modernization
```

### Hard dependencies

1. **All work depends on P0 contracts and safeguards.** Define versioned event payloads, `SessionSnapshot`, `TurnRun`, `ToolInvocation`, `ContextPlan`, idempotency, tracing IDs, migration/export procedures, and validation gates first.
2. **Context optimization depends on persistent identity.** Retrieval, summaries, memory, and usage records need stable session/turn/message IDs and durable storage.
3. **Tool orchestration depends on both sessions and context.** Tool selection, schema budgets, invocation records, replay, and result references require those contracts.
4. **Automatic compaction depends on context and sessions.** It must checkpoint and version summaries against durable message ranges.
5. **Clarification depends on sessions and execution policy.** Questions/answers must survive reconnects and block tools through server-side gating.
6. **UI modernization depends on snapshot/event contracts.** The frontend should consume authoritative state rather than duplicate backend logic.

## Execution sequence

### Phase 0 — Baseline and architecture lock

1. Verify the existing backend/frontend test, lint, typecheck, and startup baseline.
2. Map current startup, websocket dispatch, agent loop, tool registry, repositories, session service, and TUI stores.
3. Define versioned contracts for session snapshots, events, turns, invocations, context plans, and clarification.
4. Add correlation IDs, structured logs, feature flags, migration backups, and a release checklist.
5. Record the competitor research matrix and distinguish verified behavior from inference.

**Exit gate:** contracts are reviewed, existing data can be exported, and baseline failures are classified as product regressions or environment issues.

### Phase 1 — Durable session foundation

1. Add normalized turn/run, invocation/result, snapshot, summary, memory, and clarification persistence models.
2. Build migration adapters from existing sessions/messages/events/checkpoints/token records.
3. Implement server-generated `SessionSnapshot` and monotonic sync replay.
4. Make prompt/tool/approval/cancel writes idempotent and durable before event publication.
5. Hydrate the TUI from the snapshot on resume.

**Exit gate:** restart/reconnect/resume restores messages, executions, pending state, and statistics without duplicate side effects.

### Phase 2 — Context and token architecture

1. Implement model-specific budget resolution and request-scoped usage accounting.
2. Extract a deterministic `ContextAssembler` and persist `ContextPlan` metadata.
3. Add complete-turn history selection, omission reasons, FTS retrieval, and provenance.
4. Add structured memory items and versioned rolling summaries.
5. Benchmark full-history, recent-tail, summary, and hybrid retrieval strategies.

**Exit gate:** requests remain below provider limits, old relevant decisions are retrievable, and input-token/cost reduction is measured without task-quality regression.

### Phase 3 — Automatic tool orchestration

1. Inventory and annotate all built-in, MCP, LSP, job, and sub-agent tools.
2. Implement capability catalog and intent router.
3. Add request-specific lazy schema loading and provider compatibility mode.
4. Add scheduler, policy, approval, timeout, cancellation, retry, concurrency, and child-agent budgets.
5. Persist and render invocation/result timelines.

**Exit gate:** general prompts use no unnecessary tools; coding prompts automatically discover appropriate tools; unauthorized or hallucinated calls cannot execute.

### Phase 4 — Automatic compaction

1. Add model-aware soft/proactive/hard thresholds.
2. Implement compaction locks, checkpoints, protected facts, structured summaries, and source ranges.
3. Store oversized tool outputs as searchable blob references.
4. Replace process-local summary state with session-loaded summary versions.
5. Unify manual and automatic compact commands through the backend pipeline.

**Exit gate:** long sessions compact before hard limits, preserve goals/constraints/files/tests/pending work, and recover after interruption or restart.

### Phase 5 — Intelligent clarification

1. Implement preflight intent decisions and deterministic missing-information checks.
2. Add persisted clarification threads, questions, answers, validation, expiry, and cancellation.
3. Gate mutating tools until required answers reach `READY_TO_EXECUTE`.
4. Replace the global question callback with a session-scoped workflow adapter.
5. Add answer reuse, editing, supersession, and conflict handling.

**Exit gate:** incomplete requests ask focused questions; required clarification cannot be bypassed; fully specified prompts proceed without unnecessary friction.

### Phase 6 — UI/UX implementation

1. Introduce one typed event reducer and snapshot-backed `SessionViewModel`.
2. Fix resume hydration and remove synthetic local-only compaction state.
3. Add execution timeline, tool/approval/test/artifact views, context/cost details, and clarification cards.
4. Standardize loading, error, retry, cancel, focus, keyboard, resize, contrast, and reduced-motion behavior.
5. Run scenario-based usability and competitor-parity review.

**Exit gate:** users can see what the agent is doing, what it changed, what it needs, how much context/cost was used, and recover/resume without hidden state.

### Phase 7 — Hardening and release

1. Run security, failure-injection, migration, load, and long-session tests.
2. Validate SQLite WAL/backup/integrity/recovery and bounded background jobs.
3. Measure SLOs: acknowledgement, first useful token, total turn, restore, tool, compaction, and event-replay latency.
4. Review dead code, duplicate persistence APIs, obsolete compatibility paths, and known environment-specific failures.
5. Publish release report, known debt, rollback instructions, and next hosted-scale ADRs.

## Work that can proceed independently

These efforts can be developed without waiting for the full feature sequence, provided they do not change shared contracts unexpectedly:

### Fully independent or low-coupling

- Competitor research and UX audit inventory.
- Accessibility review, keyboard map cleanup, visual consistency audit, and copy/status improvements.
- Tool metadata inventory and schema-token benchmarking.
- Provider capability catalog research and adapter contract tests.
- SQLite backup/export/import tooling and integrity diagnostics.
- Security review of path validation, shell execution, MCP isolation, and secret redaction.
- Load/latency benchmark harnesses and synthetic long-conversation fixtures.
- Dead-code and duplicate-logic audit (deletion waits for reference/test verification).

### Parallel after Phase 0 contracts

- Session repository/schema implementation.
- Context assembler and token ledger implementation.
- Capability catalog/router prototype.
- Clarification state machine/backend persistence.
- UI reducer and snapshot fixtures.

### Must wait for upstream work

- Automatic compaction must wait for durable sessions and context plans.
- Mutating tool routing must wait for invocation persistence, policy, and idempotency.
- Clarification UI must wait for the versioned clarification event/snapshot contract.
- Final UI timeline and statistics must wait for authoritative run/invocation/usage models.
- Removing legacy repositories/events/models must wait for migrations, exports, parity tests, and rollback proof.

## Cross-workstream completion checklist

- Contract version and migration impact documented.
- Configuration/constants added through centralized modules.
- Raw history and user data remain recoverable.
- Permissions, cancellation, retries, and failure modes tested.
- Metrics cover latency, tokens, cost, errors, and resource growth.
- Backend and frontend projections agree after reconnect/resume.
- Required validation pipeline and runtime observation completed.
- Code-quality review completed; obsolete code removed only with evidence.
- Follow-up debt and next priority are recorded in the relevant workstream book.
