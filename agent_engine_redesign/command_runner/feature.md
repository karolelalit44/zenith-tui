# Command Runner

## Overview

How the agent runs shell commands (bash/PowerShell), how it waits for completion, and how output flows back. This is a major UX difference vs the reference engines.

### How opencode does it

- `tool/shell.ts` â€” the `bash` tool runs via a **persistent pseudo-TTY shell session**.
- It uses `ChildProcess` + `CrossSpawnSpawner` with `TERM=dumb`, spawns the preferred shell with the command and the working directory.
- It streams decoded output chunks into `part.state.metadata.output` **as they arrive** â€” the user sees the running command's output live.
- The tool part transitions `status: running â†’ completed`. The user sees the live running state.
- Abort support marks the output with a metadata note and ends the tool part.
- Force-kill after a grace period if the process hangs.
- A background escape exists for intentionally long-running processes, but the normal flow is synchronous-with-live-stream.

### How codex does it

- Native `exec` with a **PTY** (`codex-rs/core/src/exec.rs`, `tools/runtimes/unified_exec.rs`).
- `ExecExpiration { TimeoutOrCancellation }` â€” the command runs until it completes, hits a timeout, or is cancelled.
- Output is chunk-capped (`EXEC_OUTPUT_MAX_BYTES`) and streamed live as `ExecCommandOutputDelta` events.
- Default timeout (`DEFAULT_EXEC_COMMAND_TIMEOUT_MS`).
- Background via a process manager where needed.
- Shell sessions (zsh fork, etc.) for interactive use.

### What zenith has today

**Files (server/toolkit/tools/):**
- `bash.py` â€” runs a PowerShell/UNIX command in the workspace, refuses unbounded recursive listings, PowerShell-aware descriptions. Has `DEFAULT_BASH_TIMEOUT_MS = 60_000`.
- `background.py` â€” runs commands as background jobs.
- `job_output.py` â€” poll a completed background job for its output.
- `job_kill.py` â€” kill a background job.

**Constants (server/config/constants.py):**
- `DEFAULT_BASH_TIMEOUT_MS = 60_000`
- `POLL_TOOLS = ("job_output",)`
- `BG_OUTPUT_TAIL = 800`
- `BASH_FALSE_SUCCESS_PATTERNS = ("Unable to initialize device PRN",)`

**The model:** to run a command, the model calls `bash`. If the command is long or the result is needed incrementally, zenith routes it to `background` + `job_output`, and the **model must make an extra poll call** to see the output.

### What is correct

- The PowerShell-aware bash tool and refusal of unbounded listings are good, Windows-specific, behaviors.
- Timeouts exist.

### What is wrong / over-engineered / incorrect / missing

**Over-engineered / incorrect:**
- The **async background + poll `job_output` model** as the primary way to see command output. Neither opencode nor codex works this way. They run commands synchronously with live-streamed output in-place. Requiring a separate `job_output` tool call is non-standard and worse UX.
- `BASH_FALSE_SUCCESS_PATTERNS` â€” matching output text to decide success is a heuristic not in opencode/codex (they use the process exit code).

**Missing:**
- **Live output streaming** in-place while the command runs.
- **Persistent shell session / PTY**.
- Clean **wait-for-completion** semantics (block until done, timeout, or cancel), rather than background+poll.

### Static/simulation code to remove
- `BASH_FALSE_SUCCESS_PATTERNS` (heuristic on output text; use exit code instead).

## What we will do

Build a command runner that matches opencode/codex:
- A PTY (or persistent-shell) based runner that executes the command synchronously.
- Stream output chunks to the tool result as they arrive (user sees live output).
- Mark the tool part running â†’ completed.
- Wait for completion via timeout or cancellation (not poll).
- Keep the PowerShell-aware descriptions and the unbounded-listing refusal (Windows-specific, valuable).
- Background only as an explicit escape for very long tasks, not the normal path.

## What we will REMOVE
- The poll-based `job_output` / `job_kill` as the primary interface (keep only as explicit background escape).
- `BASH_FALSE_SUCCESS_PATTERNS` (use exit code).

## Regex audit
| Regex | opencode/codex uses it? | Action |
|---|---|---|
| `BASH_FALSE_SUCCESS_PATTERNS` matching | No (they use exit code) | Remove |

## Verification / signoff
- [x] Live output streaming in-place (additive `run_shell_command_streamed` + `ShellStreamEvent`)
- [~] PTY / persistent-shell runner — Phase 2/3 (subprocess-approximation now; PTY later)
- [x] Wait-for-completion (block until done / timeout / cancel), no poll — in the streaming primitive
- [x] PowerShell-aware + unbounded-listing refusal kept (untouched)
- [x] ruff + pytest pass (additive change)

## Status: Interface-Locked (Phase 1 additive); poll-based background path pending Phase 3; false-success heuristic and auto-background fallback removed

### Decision (2026-08-31) — phased execution (Mars, module 05 owner)

Per `progress.md` §11, Phase 1 is **additive interface-lock only; no removal yet**. Today `bash.py`
streams foreground output to completion and uses `background`/`job_output`/`job_kill` only when the
caller explicitly opts in. The `BASH_FALSE_SUCCESS_PATTERNS` heuristic and auto-background fallback
have been removed. So module 05 has:
- **ADDED (interface-lock) in `server/shell_runner.py`:**
  - `ShellStreamEvent` (stdout/stderr chunk, or terminal `exit` with exit_code) and
    `run_shell_command_streamed(command, cwd, timeout)` — an async generator that yields live decoded
    output chunks in arrival order (opencode bash.ts streams into part.metadata.output as they arrive;
    codex ExecCommandOutputDelta) and waits for completion, timeout (kills + raises asyncio.TimeoutError),
    or consumer cancellation (kills + propagates). No background job or separate poll involved.
- **NOT removed yet (Phase 2/3, coordinated):** the explicit `background`/`job_output`/
      `job_kill` escape hatch. These are removed / re-wired only after the loop + transport (module 01/12)
      and TUI adopt the streaming contract. The PowerShell-aware descriptions,
      `_assess_enumeration` unbounded-listing refusal, and exit-code semantics are kept. Do NOT replace
      bash.py's execute path during Phase 1.

### Decision (2026-09-01) - Phase 2 foreground wiring (Mars)

- **LIVE:** foreground `BashTool.execute()` consumes `run_shell_command_streamed()` through its
      final exit event and returns the accumulated output and exit code in the unchanged `ToolResult`.
      `run_in_background` remains the explicit opt-in escape.
- **HANDOFF:** `ShellStreamEvent` already supplies live stdout/stderr chunks. Module 01/10 owns the
      loop/event-adapter path that must publish those chunks to the TUI, so this module does not modify
      transport files or invent a second event contract.
- **Validation:** editor diagnostics pass for `bash.py`, `shell_runner.py`, and streaming tests.
      Focused pytest on the touched helper/background slice passes locally.

---

## Module report (§9 template)

```
Module: 05 command_runner
Status change: Pending → Interface-Locked (Phase 1 additive)
WHAT: Added ShellStreamEvent + run_shell_command_streamed (live chunk streaming + wait-for-completion
      with timeout/cancellation) in server/shell_runner.py.
WHY: opencode/codex stream command output live in-place (bash.ts metadata.output; ExecCommandOutputDelta)
      and wait for completion — zenith's background+poll job_output model is non-standard/worse UX. This is
      the module's core *missing* correct behavior, expressed as the primitive the tools/transport adopt in Phase 2.
FILES: server/shell_runner.py, server/tests/test_shell_streamed.py (NEW),
      agent_engine_redesign/command_runner/feature.md
KEPT/REMOVED: additive streaming runner added; background/job_output/job_kill explicit escape retained,
      false-success heuristic and auto-background fallback removed; PowerShell-aware + enumeration-refusal
      kept.
EXPECTED BEHAVIOUR: consumers can stream command output live and await completion; foreground
      `bash.py` now consumes the streaming primitive while explicit backgrounding remains the
      long-running escape hatch.
OUTCOME / TEST EVIDENCE: G1 PASS (5 new tests); G2 targeted-PASS (streaming tests green; a benign Windows
      asyncio subprocess-transport GC resource warning noted — non-fatal); G3 ruff clean; G4 interface
      declared in feature doc; G5 no transport/event change; G6 additive only; G7 module-05 owned files
      updated consistently (shell_runner.py, bash.py, background.py); G8 self-contained.
SHARED-FILE IMPACT: none.
DEPENDENCIES: provides streaming-exec contract to module 01 loop, 12, and 10 transport for Phase 2 live
      streaming; Phase 3 keeps the poll-based primary path pending while the false-success heuristic has
      already been removed.
```

Next: Phase 2 keeps the streamed foreground path and explicit background escape; Phase 3 removes the
background+poll primary path under coordination.
