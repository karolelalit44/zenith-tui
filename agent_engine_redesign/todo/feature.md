# Todo

## Overview

The todo tool that lets the model maintain a task checklist during a turn.

### How opencode does it

- `tool/` has a `golden`/`timeline`-style **`todo` / `todowrite`** tool.
- It's a plain tool: the model calls it to write/update a markdown task list; the output is echoed back into the context.
- No dedicated todo engine/state machine. It's part of the standard tool set.
- Subagent permissions can deny `todo*` for child agents (`subagent-permissions`: canTodo â†’ allows todowrite).

### How codex does it

- No dedicated todo subsystem; task tracking is done via the agent's own messaging/planning tools (threads/`send_messages_to_thread`). Todo isn't a first-class complex system.

### What zenith has today

- `server/toolkit/tools/todo.py` â€” the `todo` tool.
- `server/agents/todo_state.py` â€” a todo **state machine** (lifecycle phases: planning/in_progress/verifying/completed, TodoLifecyclePhase).
- `TodoBoardEvent`, `TodoItem`, `TodoBoardAction` in the TUI `scenario.ts`, plus `todo_board` / `todo_test` event kinds.

### What is correct

- A `todo` tool that the model calls exists.

### What is wrong / over-engineered / incorrect / missing

**Over-engineered:**
- `todo_state.py` lifecycle state machine (planning â†’ in_progress â†’ verifying â†’ completed, with phase transitions) is more than opencode's plain todowrite tool.
- Additional `todo_board` / `todo_test` / `TodoBoardAction` event machinery that isn't in the core reference.

## What we will do

- Keep a simple `todo` tool that writes/updates a checklist and echoes it into context.
- Remove the dedicated todo lifecycle state machine unless the TUI board strictly requires it.

## What we will REMOVE
- `todo_state.py` lifecycle state machine (or reduce to plain tool output).
- Unneeded `todo_board` event machinery if the TUI doesn't need it.

## Regex audit
| Regex | opencode/codex uses it? | Action |
|---|---|---|
| (none specific here) | â€” | â€” |

## Verification / signoff
- [ ] Simple todo tool (write/update checklist)
- [ ] No lifecycle state machine
- [ ] ruff + pytest + runtime smoke pass

## Status: Review

## Report (Jupiter Worker)

```
Module: 12 todo
Status change: Pending → Review
WHAT: Reduced the todo tool to a plain checklist (write/list/remove actions) with
      a session-scoped store that echoes the board into context. Removed the
      lifecycle-phase actions (add/update/complete/fail/reopen/reorder) in favor
      of a single `write` action that replaces the whole board (opencode todowrite).
WHY: matches opencode's todowrite — a plain checklist tool, no lifecycle state
     machine, output echoed back to context.
FILES: server/toolkit/tools/todo.py, server/agents/todo_state.py, server/tests/test_todo_state.py
OPEND/REMOVED: removed the per-item mutate complexity; store simplified (eight
     actions → three), kept session-scoped store, todo.md artifact, todo_board event.
EXPECTED BEHAVIOUR: model calls todo(actions=[write|list|remove]) to replace/read
     the whole board; each write/list echoes the formatted checklist; todo_board
     event still emitted for the TUI board.
OUTCOME / TEST EVIDENCE: G1 PASS (23 tests); G2 in progress; G3 ruff clean;
     G6 PASS (no new features); G8 PASS (tests pass, run_state/explore unaffected).
SHARED-FILE IMPACT: none (no CCS edits; constants references unchanged).
DEPENDENCIES: unblocks nothing new (independent); downstream depends on module 03.
```
