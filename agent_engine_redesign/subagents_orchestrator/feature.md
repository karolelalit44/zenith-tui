# Subagents / Orchestrator

## Overview

How the agent spawns child agents / subagents (exploration, task delegation) and coordinates them.

### How opencode does it

- A **`task` tool** (`tool/task.ts`). A subagent part in a user message tells the parent to call the task tool with the subagent name.
- `handleSubtask` creates a **child session** with a prompt, runs it, and returns the result via the tool result.
- Subagent permissions: `agent/subagent-permissions.ts` â€” "Parent agent restrictions only govern the parent; the subagent's own permissions determine its capabilities."
- The subagent is just a child session + prompt â†’ result. No separate orchestration service.

### How codex does it

- `spawn_agent` + `send_messages_to_thread` tools in the `collaboration` namespace.
- `AgentSpawnConfig { model, reasoning_effort, fork_mode, num_turns, skills_dir, ... }`.
- `SpawningProfile` / `ThreadTurnProfile` define roles.
- Subagents are child threads with their own model/effort/turn limits.

### What zenith has today

- `server/agents/delegation/` â€” `CaptainOrchestrator`, `scout.py` (crewmate runner), `specialist_registry.py`.
- `server/agents/crewmate_loop.py` â€” `CrewmateLoop.run` creates a child session and runs a sub-loop with a plan prompt.
- `server/toolkit/tools/explore_tool.py` â€” the `explore` tool.
- Explore delegation governance: `EXPLORE_DELEGATION = off | tool | proactive`.
- Budgets: `EXPLORE_BUDGETS` (quick/standard/deep with timeout_s + context_tokens), `EXPLORE_TOKEN_BUDGET`, `EXPLORE_BUDGET_WINDOW_SECONDS`.
- `APPOGEE_AGENT_*` constants, `EXPLORE_THOROUGHNESS_LEVELS`, `EXPLORE_PARALLEL_DEFAULT/MAX`.
- `CREWMATE_*` event kinds.
- Structural graph tools (code_callers/code_outline/code_blast_radius), `GRAPH_QUERY_*`.

### What is correct

- The idea of a child session running a focused task and returning a result (matches opencode's task tool and codex's spawn_agent).

### What is wrong / over-engineered / incorrect / missing

**Over-engineered (remove):**
- `CaptainOrchestrator` â€” not in opencode/codex.
- `scout.py` / `specialist_registry.py` â€” not in the reference.
- `crewmate_loop.py` â€” not in the reference.
- Explore delegation **governance modes** (off/tool/proactive) â€” not in the reference.
- `EXPLORE_BUDGETS` / `EXPLORE_TOKEN_BUDGET` / budget windows â€” opencode/codex control subagent spend via the subagent's own turn/model limits, not a parent-aggregated token-budget scheduler.
- Structural graph tools (code_callers/code_outline/code_blast_radius) as a crewmate subsystem â€” not a core reference feature.

**Missing:**
- A clean **task tool** (child session + prompt â†’ result) and subagent **permission** model where the child has its own permissions.

## What we will do

- Implement a `task` tool that spawns a child session with a prompt and returns the result.
- Subagent permissions: child agent has its own permissions (opencode pattern).
- Remove the captain/crewmate/scout/specialist orchestration.

## What we will REMOVE
- `server/agents/delegation/` (CaptainOrchestrator, scout, specialist_registry)
- `crewmate_loop.py`
- `explore_tool.py` (the explore tool) and `EXPLORE_*` / `APPOGEE_*` constants
- Explore delegation governance + budgets
- `CREWMATE_*` event kinds
- Structural graph tools if not otherwise needed

## Regex audit
| Regex | opencode/codex uses it? | Action |
|---|---|---|
| (none specific here) | â€” | â€” |

## Verification / signoff
- [ ] task tool spawns child session + returns result
- [ ] Subagent has own permissions
- [ ] No Captain/crewmate/scout/specialist
- [ ] ruff + pytest + runtime smoke pass

## Status: Pending
