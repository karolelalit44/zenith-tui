# Session State

## Overview

How a session (conversation) is modeled, persisted, and resumed, and how its state (busy/idle) is tracked.

### How opencode does it

- `Session { id, messages, parts, metadata, time, title, agent, model, ... }`.
- Messages with Parts stored append-style in a store (JSONL/file-backed).
- Status is a simple in-memory map (`status.ts`): busy / idle.
- `MessageV2` helpers: `latest`, `page`, `filterCompactedEffect`.
- Resume/replay from the store. `getUsage` accumulates token/cost.
- Forking clones the message frontier into a new session.

### How codex does it

- `StateSaver` snapshots state after each turn step.
- `persist_rollout_items` writes JSONL per thread for replay.
- Session is a durable, reconstructable log.

### What zenith has today

**Files:**
- `server/domain/session.py` â€” `Session` pydantic model with a **state machine** (`_VALID_TRANSITIONS` map, `transition()` method). States: created/initializing/active/resumed/completed/summarized/paused/exported/archived/draft/error/checkpointing.
- `server/sessions/service.py` â€” `SessionService` / `DefaultSessionService` with create/get/require/list/initialize/complete/pause/resume/archive/delete/duplicate/checkpoint/export/sync-events, publishing EventBus events on transitions.
- `server/storage/session_store.py` â€” `FileSessionRepository`, `FileMessageRepository`, `FileCheckpointRepository`, `FileSyncEventRepository`. Append-only JSONL per session.
- `server/agents/run_state.py` â€” `SessionRunState` / `RunStep`, persisted in `session.metadata["run_state"]`.
- `server/agents/session_workspace.py` â€” `SessionFileRecord` tracking paths/hashes/writes/edits/reads, replay-blocking, read-cache, heavy-output store.

### What is correct

- Append-only JSONL storage (matches opencode/codex).
- Session has a status.

### What is wrong / over-engineered / incorrect / missing

**Over-engineered:**
- The **state machine** with many states and transitions (`_VALID_TRANSITIONS`) â€” opencode/codex use a simple status (busy/idle) + persisted messages.
- `session_workspace.py` â€” tracking file writes/hashes for replay-blocking and read-caching is not in the reference. This caused the "file_write blocked this turn" breakage.
- `run_state` persisted into session metadata and elaborate session-service transition events.

**Missing:**
- Clean resume/replay from the append log.
- Session title derivation (opencode derives "New session - <timestamp>" / fork titles).

## What we will do

- Slim the session to: id, messages/parts, metadata, time, status (busy/idle).
- Keep append-only JSONL persistence and resume/replay.
- Drop the state machine and the session-workspace file-tracking.

## What we will REMOVE
- The state machine (`_VALID_TRANSITIONS`) and excess SessionStates.
- `session_workspace.py` entirely (replay-blocking, read-cache, heavy-output, file tracking).
- `run_state` persisted into session metadata (fold into a simple status).

## Regex audit
| Regex | opencode/codex uses it? | Action |
|---|---|---|
| `SESSION_STATE_HASH_PREFIX_LEN` | No | Remove |
| (session_workspace hashing) | No | Remove |

## Verification / signoff
- [x] Simple session status (busy/idle) — additive RunStatus added
- [~] Append-only store, resume/replay — existing; status contract additive for module 21
- [~] No state machine, no session_workspace file tracking — Phase 3 removals (2/phase)
- [x] ruff + pytest for additive change pass

## Status: Interface-Locked (Phase 1 additive); state-machine + session_workspace removal pending Phase 3

### Decision (2026-08-31) — phased execution (Mars, module 07 owner)

Per `progress.md` §11, Phase 1 is **additive interface-lock only; no removal yet**. Today the
state machine (`_VALID_TRANSITIONS`), `run_state`, and `session_workspace.py` are still consumed
by the loop/service. So module 07 has:
- **ADDED (interface-lock) in `server/domain/session.py`:**
  - `RunStatus` enum — ``busy / idle`` (opencode ``status.ts``).
  - `Session.run_status` field (defaults IDLE) + ``mark_busy()`` / ``mark_idle()`` and a
    ``status`` property returning ``<value>``.
- **NOT removed yet (Phase 3, coordinated):** `_VALID_TRANSITIONS` state machine,
  `session_workspace.py` (file-write/hash/read-cache tracking), `run_state` persisted into
  metadata. These collapse onto the simple status/append-log only once module 21 storage and
  01 loop adopt the new shape. Do NOT delete them during Phase 1.

### Step-2 adoption (Jupiter, module 01) — 2026-08-31

The executor (`server/agents/prompt_executor.py`) now drives `RunStatus` on every turn: marks the
session `BUSY` (and persists via `FileSessionRepository.update`) once the turn is executing, and
marks it `IDLE` last — after all run-state/assistant/workspace persistence has settled — mirroring
opencode `status.ts` (a session is busy while a turn is in flight and returns to idle once it
resolves). `PATCH_EXCLUDE` does not exclude `run_status`, so the status survives reload. This is the
module-21 storage consumer coupling that unblocks Mars's session_workspace/state-machine collapse
(Phase 3). Verified: ruff clean, 189 loop/executor/session tests green (incl. new
`TestRunStatusAdoption` with a mid-turn BUSY observation).

---

## Module report (§9 template)

```
Module: 07 session_state
Status change: Pending → Interface-Locked (Phase 1 additive)
WHAT: Added RunStatus (busy/idle) + Session.run_status + mark_busy/mark_idle/status in
      server/domain/session.py.
WHY: opencode model (status.ts) uses a simple busy/idle status, not zenith's 12-state machine;
      gives module 21 storage a stable, persistable status contract to resume/replay from.
FILES: server/domain/session.py, server/tests/test_session_status.py (NEW),
      agent_engine_redesign/session_state/feature.md
KEPT/REMOVED: additive RunStatus added; _VALID_TRANSITIONS + session_workspace.py + run_state
      kept for Phase 3 (consumers 01 loop / 21 storage must adopt simple status first).
EXPECTED BEHAVIOUR: any Session now carries a simple busy/idle run_status alongside the legacy
      state machine; no behavioral change to existing flows.
OUTCOME / TEST EVIDENCE: G1 PASS (4 new tests); G2 targeted-PASS (session tests green incl.
      legacy test_session_workspace 21 pass); G3 ruff clean; G4 interface declared in feature doc;
      G5 no transport/event change; G6 additive only; G7 no CCS-shared-file lock needed (session.py
      is module-07 owned; session_store.py left for module 21 — not touched); G8 self-contained.
SHARED-FILE IMPACT: none (server/storage/session_store.py is module 21's; not edited here).
DEPENDENCIES: provides busy/idle status contract to module 21 storage (unblocks its interface-lock)
      and to 01 loop; Phase 3 removes state machine/workspace under coordination.
```

Next: Phase 2 wires consumers onto run_status; Phase 3 removes the state machine + session_workspace.
