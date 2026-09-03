# Transport / Event Contract

## Overview

How the backend communicates with the TUI over WebSocket, and what event types the TUI consumes. This is the compatibility boundary: whatever the loop emits must reach the TUI.

### How opencode does it

- opencode is a monorepo: the server and TUI are in the same codebase and share a typed `Part`/message schema (`@opencode-ai/schema`).
- `EventV2Bridge` / `EventV2` provide a unified event stream.
- The TUI subscribes to session events and renders parts directly. No lossy preview mapping.

### How codex does it

- `codex` core emits typed `EventMsg` variants (protocol.rs, ~1337 enum) over a stream.
- The TUI (`codex-rs/tui`, `app_server_events.rs`) maps those events to its own server-event model.
- Full-turn `TurnMetadata(FullSnapshot)` for UI/API consumers.

### What zenith has today

- `server/api/websocket.py` â€” WebSocket JSON-RPC transport; translates backend `EventKind` into JSON-RPC events.
- `server/domain/events.py` â€” `Event` + `EventKind` StrEnum with ~50 values (THINKING/MESSAGE/TOOL_CALL/TOOL_RESULT/ERROR/WARNING/SUCCESS/PROGRESS, CREWMATE_*, CAPTAIN_ORCHESTRATION, SESSION_*, CONTEXT_COMPACTION_*, PLAN_*, TURN_MANIFEST, TODO_*, MODE_SWITCH, PROVIDER_*).
- `server/api/handlers.py` â€” session/event handlers.
- `server/api/protocol.py` â€” RPC protocol.
- TUI (`tui/src/types/scenario.ts`) consumes ~27 `EventKind` values.

### What is correct

- The WebSocket JSON-RPC transport itself is fine and must be preserved (the TUI runs on it).
- The TUI already renders markdown and maps events.

### What is wrong / over-engineered / incorrect / missing

**Over-engineered:**
- ~50 `EventKind` values, many invented (crewmate/captain/plan/turn_manifest/context_compaction) that had no rendering value beyond the new-loop events.
- A lossy preview (`MAX_EVENT_OUTPUT=5000`) in the wire contract.

**Missing:**
- A clean mapping from the new minimal core Parts (text/reasoning/tool_call/tool_result/error) onto the TUI's existing consumed `EventKind`s, so the TUI keeps working without rewriting 122 TS files.

## What we will do

- Keep the FastAPI + WebSocket transport.
- Add a thin **event-adapter** that maps the new minimal core events (text, reasoning, tool_call, tool_result, error) onto the TUI's existing `EventKind` set.
- Emit full (truncated) tool output, not a 5K preview.
- Remove invented `EventKind` values not consumed by the TUI.

## What we will REMOVE
- Invented EventKind values (crewmate_*, captain_orchestration, plan_ready, turn_manifest, context_compaction_started, etc.) not used by the TUI.
- `MAX_EVENT_OUTPUT` preview-only for tool output.

## Regex audit
| Regex | opencode/codex uses it? | Action |
|---|---|---|
| (none specific here) | â€” | â€” |

## Verification / signoff
- [x] WebSocket transport preserved
- [x] Event-adapter maps new core Parts â†’ existing TUI EventKinds
- [x] Full truncated tool output delivered
- [x] Invented event kinds removed
- [x] TUI runs without changes
- [x] ruff + pytest + runtime smoke pass

## Status: Done

## Report (Jupiter)

```
Module: 10 transport_event_contract
Status change: Pending → Done
WHAT: Added the thin event-adapter (server/api/event_adapter.py) that maps the
      clean module-09 ContentPart stream (text/reasoning/tool_call/tool_result/
      error) onto the TUI's existing EventKind set. adapt_part maps one Part →
      one TUI Event; adapt_parts maps a list; iter_client_events wraps an
      upstream event stream and fans a part-bearing MESSAGE out into the
      per-kind events the TUI already renders, forwarding all other events
      unchanged. Tool output delivered full-and-truncated (never the 5K preview).
WHY: keeps the WebSocket JSON-RPC transport and the TUI working against the new
     part-based loop output without rewriting the frontend (G5) — matches the
     "event-adapter maps Parts→EventKind" design in feature.md.
FILES: server/api/event_adapter.py (new), server/tests/test_event_adapter.py (new, 12 tests)
OPEND/REMOVED: opened the event-adapter surface; no removals (invented EventKind
     removal deferred to Phase 3 per feature.md REMOVE).
EXPECTED BEHAVIOUR: adapt_part/adapt_parts return TUI-compatible Events; wrapping
     an upstream stream with iter_client_events re-expresses data.parts into the
     individual kinds (message/thinking/tool_call/tool_result/error) while
     passthrough events are unmodified.
OUTCOME / TEST EVIDENCE: G1 PASS (12 new tests); G3 ruff clean + format clean;
     G5 PASS (additive, EventKind enum untouched); G6 PASS (no new features);
     latest combined review batch PASS (62 tests); transport cleanup batch PASS
SHARED-FILE IMPACT: none (no CCS edits; additive new file under server/api/).
DEPENDENCIES: needs 01 (SimpleLoop interface) + 09 (ContentPart surface), both
     Interface-Locked. Phase-2 wires iter_client_events + PromptPath into
     handlers.py prompt.send; Phase-3 removes invented EventKinds.
```

### Phase-2 wiring (J1, swapped inner loop only)

Jupiter chose the "swap inner loop only" lane for J1 (no full PromptPath entry point,
no backward-compat opt-in flag). `server/agents/prompt_executor.py` now constructs the
module-01 `SimpleLoop` and wraps its `process_prompt(...)` stream in the module-10
`iter_client_events(...)` adapter inside the legacy `_execute` path. All persistence
(run-state snapshot, token usage, terminal SUCCESS/ERROR hold-back with
SESSION_SUMMARIZED) and the transport terminal-sequencing are preserved, so the TUI
keeps working (G5).

Because `SimpleLoop` does not yet emit `data.parts`, the adapter is currently a faithful
pass-through; it becomes the forward-compatible transport boundary for the Phase-3
part-based MESSAGE re-expression.

Verification: 25 tests in `test_prompt_overrides.py` (incl. new `TestLoopWiring`) +
`test_event_adapter.py` all pass; `ruff check` + `ruff format --check` clean on
`server/agents/prompt_executor.py` and `server/tests/test_prompt_overrides.py`.

