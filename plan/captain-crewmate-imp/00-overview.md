# Multi-Agent Orchestration — Production Plan

**Date**: 2026-08-02  
**Status**: Draft  
**Version**: 1.0  

---

## Executive Summary

This plan describes a production-grade multi-agent architecture for Zenith, a terminal-based AI coding assistant. The system is designed around a single **Captain Agent** that orchestrates specialized **Crew Agents**, with explicit state management, event-driven communication, and a mode-aware TUI that supports both calm and detailed views.

The architecture reuses and extends the existing plan/build split, session persistence, and sub-agent handoff patterns already present in the codebase rather than introducing a distributed system prematurely.

---

## Goals

1. **Single orchestrator pattern** — Captain Agent owns all user interaction and orchestration decisions
2. **Isolated workers** — Crew Agents are stateless-with-context workers with explicit scopes
3. **Transparent execution** — Real-time visibility into agent lifecycle, progress, and failures
4. **Resilient operation** — Explicit retries, recovery, and graceful degradation
5. **Mode-aware UX** — Calm mode for minimal noise, detailed mode for full orchestration visibility
6. **Extensible design** — New agent types can be added without architectural changes

---

## Non-Goals

- Peer-to-peer agent coordination
- Distributed multi-server federation
- External queue systems or message brokers
- Browser-based UI (terminal-first only)
- Fully general agent mesh with arbitrary communication

---

## Architecture Anchors

The design extends these existing files rather than replacing them:

- `server/config/settings.py` — mode configuration, tool policies, sub-agent controls
- `server/agents/coordinator.py` — orchestration entry point, session lifecycle
- `server/agents/prompt_executor.py` — execution pipeline, plan gating, build transitions
- `server/agents/sub_agent.py` — clean context handoff, child-session isolation
- `server/domain/session.py` — state machine for parent/child sessions
- `server/persistence/repositories.py` — session, message, checkpoint persistence

---

## Implementation Phases

1. **Phase 1**: Orchestration contract and event schema
2. **Phase 2**: Captain orchestrator service and runtime
3. **Phase 3**: Crew agent registry and isolation
4. **Phase 4**: Execution hardening and recovery
5. **Phase 5**: TUI dashboard and agent cards
6. **Phase 6**: Calm/detailed mode and activity panel
7. **Phase 7**: Validation and signoff

---

## Documents

| Document | Purpose |
|----------|---------|
| `01-detailed-design.md` | Full architectural specification |
| `02-todo-list.md` | Implementation tasks and sequencing |
| `03-signoff-checklist.md` | Acceptance criteria for each phase |
| `04-minimum-criteria.md` | Minimum success requirements for production readiness |

---

## Key Decisions

1. **Captain as single orchestrator** — No peer-to-peer agent communication
2. **Event-driven state** — All state transitions are persisted and streamed
3. **Scoped context per task** — Minimal payload to prevent context leakage
4. **Plan/build separation** — Read-only planning, isolated build execution
5. **Terminal-first UI** — Calm and detailed modes, no browser-based visualization

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Agent drift or conflicting outputs | Strict task contracts, validation gates, conflict resolution in Captain |
| Context leakage between agents | Scoped context builder, fresh child sessions for build work |
| Retry storms | Bounded retries, context mutation, exponential backoff |
| Tool misuse in build mode | Policy allowlists, permission checks, validation hooks |
| UI overload in detailed mode | Event grouping, collapsible panels, calm mode as default |

---

## Timeline Estimate

- **Phase 1-2**: Foundation (contracts, orchestrator) — 1-2 weeks
- **Phase 3-4**: Workers and hardening — 1-2 weeks
- **Phase 5-6**: TUI integration — 1 week
- **Phase 7**: Validation and signoff — 1 week

Total: **4-6 weeks** for production-ready implementation

---

## Success Metrics

- All signoff criteria met
- All minimum criteria satisfied
- No regression in existing agent loop tests
- Successful execution of plan → build workflows
- Calm and detailed mode working correctly in TUI
- Retry and recovery tested with synthetic failures
