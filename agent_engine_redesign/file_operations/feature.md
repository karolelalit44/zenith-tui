# File Operations

## Overview

The file tools: read, write, edit (apply_patch), delete. This includes how edits are serialized, how paths are validated, and how large outputs are truncated.

### How opencode does it

- `tool/read.ts`: reads a file, truncates head/tail with continuation notices (`DEFAULT_MAX_LINES`, `DEFAULT_MAX_BYTES`). No read-cache.
- `tool/write.ts`: writes a file. Refuses to overwrite an existing file unless `overwrite: true`.
- `tool/edit.ts` / `apply_patch`: applies edits via a unified diff (find/replace). Must match exactly.
- **Serial mutation queue**: `tool/file-mutation-queue.ts` â€” a `Semaphore` ensures file mutations are applied one at a time (avoids races when multiple tools run in parallel).
- Paths are normalized (`path.resolve`, cwd check); crossing outside the directory triggers `external-directory` permission.
- Reads are used, edits are exact-match with guidance ("read then edit").

### How codex does it

- Real disk changes happen only through tools under granted turn permissions.
- `write` / `edit` function calls and the `apply_patch` heredoc tool (applied via a dedicated `apply_granted_turn_permissions` path).
- Path validation / sandbox: commands and file ops run within the sandbox; escape requires approval.
- Edits applied sequentially; the `apply_patch` tool verifies the patch applies cleanly.

### What zenith has today

**Files (server/toolkit/tools/):**
- `file_read.py` â€” with read-caching logic (in session_workspace).
- `file_write.py` â€” `overwrite` param, "already exists" error.
- `file_edit.py` â€” uses **fuzzy** `SequenceMatcher` matching with `FUZZY_THRESHOLD = 0.85`, produces a unified diff.
- `multi_edit.py` â€” multi-file edit tool.
- `file_delete.py`.
- `list_dir.py`.

**Related (server/agents/session_workspace.py):**
- File-write-replay blocking (the "file_write blocked: already written this turn" rule).
- Read cache (`_try_cached_read`).
- Heavy-output isolation to disk.
- File hashing for state tracking.

### What is correct

- The overwrite-flag semantics on write (matches opencode).
- The read/truncation concept.
- The individual edit/delete tool existence.

### What is wrong / over-engineered / incorrect / missing

**Over-engineered (remove):**
- **Fuzzy edit matching** (`FUZZY_THRESHOLD = 0.85`). opencode/codex require exact match. Fuzziness causes incorrect edits.
- Read-cache in session_workspace. opencode/codex don't cache reads.
- `multi_edit.py` as a separate tool. opencode/codex use one `apply_patch`/edit tool.
- File-write-replay blocking. opencode/codex just write (with overwrite flag).
- Heavy-output isolation (replaced by unified truncation service).

**Missing / incorrect:**
- **No serial file-mutation queue.** opencode (Semaphore) and codex (sequential apply) both serialize mutations. zenith lacks this, risking races.

## What we will do

Build file operations that match the reference:
- Read: truncate head/tail, no cache.
- Write: overwrite flag, refuse existing unless overwrite.
- Edit/apply_patch: exact match only, unified diff output, "read then edit" guidance.
- A per-workspace serial mutation queue ensuring one file mutation at a time.
- Path normalization + directory-escape permission.
- Remove the separate multi_edit tool (fold into edit).

## What we will REMOVE
- `FUZZY_THRESHOLD` fuzzy matching (exact match only)
- Read-cache (session_workspace)
- File-write-replay blocking
- Heavy-output isolation (replaced by Truncate service)
- `multi_edit.py` (merge into edit)

## Regex audit
| Regex | opencode/codex uses it? | Action |
|---|---|---|
| (fuzzy SequenceMatcher not regex) | No | Replace with exact match |
| `FILE_EXISTS_ERROR_MARKER` / `FILE_ALREADY_EXISTS_ERROR` | opencode has identical "already exists" semantics | Keep (matches) |

## Verification / signoff
- [x] Serial mutation queue (additive `FileMutationQueue` per workspace)
- [~] Exact-match edits only (no fuzzy) — Phase 3 removal (fuzzy path still live)
- [~] No read-cache, no replay-block — Phase 3 (session_workspace, module 07)
- [x] Write respects overwrite flag — already present (kept, matches opencode)
- [~] Path validation + directory-escape permission — present (validate_path); queue adds serialization
- [x] ruff + pytest pass (additive change)

## Status: Interface-Locked (Phase 1 additive); fuzzy/replay/cache/multi_edit removals pending Phase 3

### Decision (2026-08-31) — phased execution (Mars, module 04 owner)

Per `progress.md` §11, Phase 1 is **additive interface-lock only; no removal yet**. Today the fuzzy
edit path (`FUZZY_THRESHOLD`, `_fuzzy_find`), read-cache/replay-block (session_workspace, module 07),
heavy-output isolation, and `multi_edit.py` are all still live and consumed. So module 04 has:
- **ADDED (interface-lock) in `server/toolkit/tools/file_mutation_queue.py`:**
  - `FileMutationQueue` — per-workspace serialization (keyed by resolved workspace root) via an
    `asyncio.Lock`, so only one mutation per workspace runs at a time while distinct workspaces run
    concurrently (opencode `file-mutation-queue.ts` Semaphore semantics).
  - `mutation(workspace_root)` asynccontextmanager critical section + `run_exclusive(workspace_root, fn)`
    helper + daemon-wide `FILE_MUTATION_QUEUE` singleton.
- **NOT removed yet (Phase 3, coordinated):** `_fuzzy_find`/`FUZZY_THRESHOLD`, read-cache/replay-block
  (session_workspace), heavy-output isolation, `multi_edit.py`. Also NOT yet-wired into file_write/
  file_edit/file_delete (Phase 2: route mutations through the queue, a behavior change needing
  coordination with 01 loop concurrency). Do NOT flip to exact-match-only or wire the queue during Phase 1.

### Decision (2026-09-01) - Phase 2 production wiring (Mars)

- **LIVE:** `file_write`, `file_edit`, and `file_delete` hold
      `FILE_MUTATION_QUEUE.mutation(workspace_root)` across their filesystem mutation.
      They remain ordinary `BaseTool` registrations and therefore run through Module 03's
      `ToolDef` decode/gate/execute/truncate path without registry changes.
- **Validation:** a focused integration test replaces the queue instance in all three
      tool modules and verifies that write, exact edit, and delete each enter the same
      per-workspace queue. Editor diagnostics pass for the test and all three tools.
- **Deferred:** the fuzzy fallback, session read-cache/replay blocking, heavy-output
      isolation, and `multi_edit` removal stay Phase 3 as required.

---

## Module report (§9 template)

```
Module: 04 file_operations
Status change: Pending → Interface-Locked (Phase 1 additive)
WHAT: Added FileMutationQueue (per-workspace serial lock) + mutation()/run_exclusive() + shared
      FILE_MUTATION_QUEUE in server/toolkit/tools/file_mutation_queue.py (NEW).
WHY: opencode (file-mutation-queue.ts Semaphore) and codex both serialize file mutations; zenith's
      tools declare concurrency_group=WORKSPACE_MUTATION but never serialize → race risk. This is the
      module's core *missing* correct behavior.
FILES: server/toolkit/tools/file_mutation_queue.py (NEW), server/tests/test_file_mutation_queue.py (NEW),
      agent_engine_redesign/file_operations/feature.md
KEPT/REMOVED: additive queue added; fuzzy matching, read-cache/replay-block, heavy-output, multi_edit.py
      kept for Phase 3; queue NOT wired into tools yet (Phase 2).
EXPECTED BEHAVIOUR: consumers now have a serialization primitive; existing tool behavior unchanged.
OUTCOME / TEST EVIDENCE: G1 PASS (4 new tests); G2 targeted-PASS (serialization tests green);
      G3 ruff clean; G4 interface declared in feature doc; G5 no transport/event change; G6 additive only;
      G7 no CCS/shared file touched (file_mutation_queue.py is module-04 owned; session_workspace.py not
      edited); G8 self-contained.
SHARED-FILE IMPACT: none.
DEPENDENCIES: provides serialization contract to 01 loop (concurrency) and module 07; Phase 2 wires the
      queue into file_write/file_edit/file_delete; Phase 3 removes fuzzy/cache/replay/multi_edit.
```

Next: Phase 2 routes file tools through the queue; Phase 3 removes fuzzy matching, read-cache,
replay-block, heavy-output, and multi_edit.py under coordination.
