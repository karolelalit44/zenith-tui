# 10 — agg-bar-prism run audit: codebase-rooted problem inventory

> Area: **Zenith codebase** (agent loop, toolkit, validation, TUI) as demonstrated by the 2026-08-09 `agg-bar-prism` run
> Severity: **Critical** — the generated app is broken, and it *cannot be fixed by editing the app*. Every failure is an output of the agent loop; each root cause lives in this repo and is linked below with file:line. Fix the codebase and the generated artifacts stop being broken.
>
> Read the document as: **What failed (observed) → Codebase root cause (file:line) → What we want (behaviour the codebase must guarantee).** Nothing here prescribes implementation; it defines the problem and the required behaviour, in depth.

---

## 1. The five codebase defects that made the run fail (ranked)

### D1. Working-directory intent is silently discarded (`cd X; cmd` → runs in repo root)

**What failed (observed):** The agent ran `Set-Location agg-bar-prism; python data_generator.py`, then `python -m venv venv; ./venv/Scripts/pip install ...`. The harness log shows `Stripped cd prefix, command now: ...`. On disk the venv was created at the **repo root** (`D:\vdo\code\zenith-frontend-tui\.venv`) and `agg-bar-prism` never got one. The install job that ran there was the failed background job (D3). The model's explicit "run inside this folder" intent was erased with zero feedback, so the agent believed it was working inside the app folder when it was not.

**Codebase root cause:**
- `server/agents/validation.py:33-35` — `_CD_PREFIX_RE` matches a leading `cd <dir>;` and `validation.py:71-77` `strip_cd_prefix()` removes it from the command.
- `server/toolkit/executor.py:96-110` `apply_bash_prechecks()` calls `strip_cd_prefix` and **mutates `tool_params["command"]`**, logging `"Stripped cd prefix, command now: ..."`.
- `server/toolkit/tools/bash.py:139-154` `_execute_sync()` then runs the stripped command with `cwd=workspace_root` — the `cd` target directory is **never** used as the working directory.

Net: the three files collaborate to make `cd X; cmd` mean "run `cmd` in the workspace root, silently". The model is taught to write `cd X; ...` (the workspace guidance even says "to act inside a subfolder, start the command with 'Set-Location <folder>;'"), and the tooling erases the half it cares about.

**What we want:** A command with an explicit working-directory intent must execute in that directory. Either the leading `cd <dir>;` is parsed and its target becomes the subprocess `cwd` (resolved under the workspace root, validated to stay inside it), or the stripping is removed and the tool schema exposes a `workdir` parameter the model sets explicitly. Under no circumstances may a cwd-changing prefix be dropped while the rest of the command still runs — that produces silent wrong-directory side effects (files/venvs landing in the wrong place) with no error.

---

### D2. Bash "success" trusts `exit_code == 0` even when nothing ran (`Unable to initialize device PRN`)

**What failed (observed):** The verification command `python -c "import uvicorn, fastapi, pandas; print('All modules present!')"` printed `Unable to initialize device PRN` (a Windows failure where the `python` invocation is the MS Store alias and the command never really runs). The bash tool returned success (`exit_code=0`), the run log recorded `success=True`, and the agent reported "All modules present!" — a check that verified nothing was treated as proof the app works. This is the single biggest trust failure in the run: the only "verification" was a false positive, and nothing downstream ever re-verified.

**Codebase root cause:** `server/toolkit/tools/bash.py:213-214` classifies `exit_code == 0` as success unconditionally. There is no post-execution sanity check: no expectation that the command produced *its declared output*, no detection of known Windows failure signatures (e.g. `Unable to initialize device PRN`, MS Store `python` stub), no check that stderr is empty when stdout is empty. `server/toolkit/executor.py:65-77` (`build_tool_metadata`) records the same `exit_code` as truth into metadata.

**What we want:** Success must mean "the command executed what was asked and produced evidence of it", not "the process exited zero". Concretely: detect known no-op/failure signatures on Windows (the PRN stub, the MS Store python alias), treat `exit 0 + empty stdout + non-empty stderr` as suspicious, and let tools (or the loop) attach an expected-output assertion so a verification command can actually fail when it produces garbage. A "success" the agent reports must be traceable to real output.

---

### D3. Background-job failures are invisible to the agent (failed `pip install` never surfaced)

**What failed (observed):** `python -m venv venv; ./venv/Scripts/pip install -r requirements.txt` was auto-backgrounded at 60s (`job_output` → "Still running..."), later completed with **`exit_code=1`, stderr_len=268**. The agent polled twice, got "Still running..." both times, then stopped polling; the completion with its failure code was never read. The run continued and claimed success with a failed dependency install on record.

**Codebase root cause:**
- `server/toolkit/tools/background.py:63-80` `_collect_output()` stores the result silently — it only `logger.info`s; no event is emitted into the agent turn when a job finishes with a non-zero exit.
- `background.py:82-95` `get_output()` only reports "Completed (exit code: N)" **when asked again**; a job that finishes between polls is never re-presented, and the agent has no signal to re-poll.
- `server/toolkit/tools/bash.py:108-132` `_start_background()` returns the "Background job started" message; nothing in the loop watches for completion.

**What we want:** Background jobs are first-class state: when a job transitions to `done`, the loop must emit a completion event with its `exit_code`, stdout tail, and stderr tail into the conversation — and if `exit_code != 0`, that is a **failure event** the agent must handle before it may claim success on anything that depends on the job. The agent should never be able to finish a turn while a job it spawned has failed and gone unread.

---

### D4. The identical-param "skip" guard treats legitimate polling as a loop (warning storm)

**What failed (observed):** The agent re-emitted `job_output(62f8e358)` (twice), `get_tool_definition('job_output')` (twice — it was already loaded), and re-globbed a path that had already failed. The loop's skip logic flagged all of them, producing the repeated wall of `[WARNING] Skipped calls already completed with identical params...` the user saw, and — worse — it *blocked* the agent from legitimately polling the background job again, which is exactly what caused D3 to go unnoticed.

**Codebase root cause:**
- `server/agents/loop.py:143-151` `_all_calls_repeat()` + `loop.py:675-696` per-call skip detection treat *all* tools uniformly by `_call_signature`.
- `loop.py:890-918` emits a user/system message re-listing skipped calls on every such iteration, compounding context and noise.
- `loop.py:620-632` dynamic tool discovery loads `get_tool_definition` schemas on demand and re-registers; nothing prevents requesting a tool that is already loaded, and `_call_signature` dedupes it out.

**What we want:** The loop must distinguish *repeat work* (re-running the same mutation) from *legitimate repeated reads* (polling `job_output`, re-reading a file that may have changed). Polling/read-only tools with identical params are valid and must not be skipped or blocked. Tool-schema discovery must be idempotent per session (requesting an already-loaded tool is a no-op, not a "skip"). The skip warning must be emitted **once per turn** and compact, not re-listed every iteration — the current design adds a full system message with the whole skipped-call list on each stall.

---

### D5. Completion is decided by "files created + summary text", never by "does it work"

**What failed (observed):** The run "completed" — manifest reported 6 files created, final summary asserted success — while the app was never started, never imported, never hit. `python main.py` does nothing (no `__main__`), the startup import references a symbol that does not exist, the pipeline CSV filename and schema are wrong. Nothing in the loop is able to say "this claim is unverified", because nothing in the loop does verification.

**Codebase root cause:**
- `server/agents/loop.py:919-934` — a turn is marked complete when `final_text` is long enough **and** `created_files` is non-empty. The loop's definition of "done" is *writing files and saying something*, with zero notion of correctness.
- `loop.py:100-140` `_build_manifest` — the end-of-turn manifest does check each created file `exists` + `size`, but that is the entire depth of verification; "exists" is not "works".
- `server/toolkit/auto_lint.py` + `server/toolkit/executor.py:172-188` — the only post-write check in the system is syntax/lint, and it only reports (D7).

**What we want:** The loop must have a verification phase for project-generation tasks: before declaring success, execute the artifact (import it, boot it, hit its endpoints, run its tests) and fold the result into the manifest. "Success" = file created **and** verified to behave. If verification cannot run in the environment, the manifest must say `verified: no` and the final summary must not claim success — exactly the discipline that would have caught every one of the artifact defects (no entrypoint, missing symbol, wrong filename/schema).

---

### D6. Context pressure + late summarization + no "done" signal = a 15-turn, 68k-token spin

**What failed (observed):** Per-turn prompt tokens grew ~4.4k → ~6.1k because the whole transcript is re-sent each turn; the session reached 53% of a 128k window for a six-file scaffold. The model, swimming in context, re-emitted completed calls; the loop fell through to skip/stall handling; 15 iterations and 2m17s later it ended not because the work finished cleanly but because the stall handler forced a summary.

**Codebase root cause:**
- `server/agents/context.py:253` `get_token_info()` + `server/agents/context.py:6` `CONTEXT_SUMMARY_THRESHOLD` — summarization fires only when the threshold is crossed; for a task like this it never fired, so the transcript grew unbounded.
- `server/agents/loop.py:420-471` — the summarization gate and the `CONTEXT_EXHAUSTED` path are the only pressure releases, and they are late.
- `server/agents/loop.py:650-658, 919-952` — the stall handler is lenient and encourages extra turns ("take a different action") instead of recognizing task-complete and stopping.
- `server/agents/provider_adapters.py:40-53` — the compact-model anti-loop instructions are *text the model must obey*; they cannot counteract a design that keeps re-sending 6k tokens and blocking its legitimate polls (D4).

**What we want:** A task is done when its defined success criteria are met (see D5), and the loop must recognize that *before* the stall path. Context should be trimmed aggressively (summary the moment the transcript passes a working budget, not only at an emergency threshold). A model that stops emitting new work must stop the turn — the loop should not invite more turns after the user's ask has been fulfilled.

---

## 2. Scaffold-quality gaps (capabilities this codebase does not have)

The artifact defects — no runnable entrypoint, no tests, broken filename/schema, README/code contradictions, no docker hygiene — are **not** accidental; the codebase has no mechanism that would prevent them. These are missing capabilities:

### G1. No project-scaffold conventions
**What failed:** A single-file app with no `__main__`/`uvicorn.run`, no package layout, no tests. Nothing in the agent's knowledge of this codebase prescribes what a "professional project" looks like (entrypoint, structure, response models, config, tests).
**What we want:** The agent must have concrete scaffold conventions to apply (entrypoint present, package layout, tests present, typed responses, project metadata) so generation isn't a free-form gamble.

### G2. No schema/cross-file contract checking
**What failed:** Three mutually incompatible schemas shipped in one project (generator vs pipeline vs a stray second generator). Nothing detects that the CSV a generator writes is not the CSV the pipeline reads, with different columns.
**What we want:** When a task involves "data written here, consumed there", the loop must verify the contract end-to-end (generate → load → transform) instead of trusting that names line up.

### G3. No README↔code consistency validation
**What failed:** README documented `GET /bronze` while code exposed `POST /bronze`; the final summary described a third reality (`POST /data/*`). Three sources, three stories.
**What we want:** The final report must be derived from the code (what was actually built), and any README shipped with a scaffold must be validated against the implemented API surface.

### G4. No docker hygiene defaults
**What failed:** Dockerfile without `.dockerignore`, `HEALTHCHECK`, non-root user, or compose; the image would bake in the broken dataset.
**What we want:** A scaffold convention for containerized apps (see G1) covering `.dockerignore`, healthcheck, non-root execution, and a one-command run path, verified by actually building/running.

---

## 3. TUI presentation defects (the "wall of warnings" the user saw)

### U1. Every internal warning renders as a full user-visible `▲ [WARNING]`
**What failed (observed):** The screen filled with `▲ [WARNING] Skipped calls already completed with identical params...`, lint warnings, context warnings, completion warnings — mechanical loop plumbing, all rendered equal to real problems.
**Codebase root cause:** `tui/src/components/Display/Scenario/WarningBlock.tsx:31-37` renders every `warning` event as a bold `▲ [WARNING]` line; the backend produces these liberally (`loop.py:432, 661, 898, 930, 943, 948`; `executor.py:185`).
**What we want:** Severity bucketing. Internal/mechanical events (skips, lint, context, completion notices) collapse into a single compact status line or a debug trace; only user-actionable warnings render prominently. One quiet, uncluttered surface like Claude Code / Codex — not the whole machinery.

### U2. Completion is duplicated and overstated
**What failed (observed):** A boxed "Turn complete · N files created" (from `SuccessCard`) *and* a final assistant message both restated the summary; the assistant's version asserted success that was never verified (D5).
**Codebase root cause:** `tui/src/components/Display/Scenario/SuccessCard.tsx:16-39` renders the turn summary; `server/agents/loop.py:919-934` + manifest mark it complete; `server/agents/prompt_executor.py` persists the assistant's final message on top. Duplication is structural.
**What we want:** One consolidated completion block derived from the verified manifest (`created / verified / remaining`), not a success card plus a summary plus an over-claiming message.

### U3. Always-on footer token gauge
**What failed (observed):** The footer permanently showed `[█████░░░░░] 53%` token usage for a trivial session.
**Codebase root cause:** `tui/src/components/Input/ComposerGauge.tsx:12-24` renders unconditionally.
**What we want:** The gauge is optional/condensed — visible on demand or only past a meaningful threshold — so the workspace feels calm.

---

## 4. Symptom → codebase root cause trace

Every observed failure in the run, and the single codebase fix it maps to. This is the table that keeps the generated artifact from being "fixed in isolation".

| # | Observed symptom (2026-08-09 run / artifact) | Codebase root cause | Fix lands in |
|---|---------------------------------------------|--------------------|--------------|
| 1 | `Set-Location agg-bar-prism; ...` ran in repo root; `.venv` landed at repo root | D1 `strip_cd_prefix` drops cwd intent | `server/agents/validation.py:33,71` · `server/toolkit/executor.py:96` · `server/toolkit/tools/bash.py:141` |
| 2 | `python -c "import ..."` printed `Unable to initialize device PRN`, recorded `success=True` | D2 success = `exit_code==0` | `server/toolkit/tools/bash.py:213` · `server/toolkit/executor.py:65` |
| 3 | `pip install` job `exit_code=1` never surfaced; run claimed success | D3 background completion invisible | `server/toolkit/tools/background.py:63,82` · `server/toolkit/tools/job_output.py` · `server/agents/loop.py` |
| 4 | `job_output`/`get_tool_definition` re-requests → skip warning storm and *blocked polling* | D4 identical-param guard treats polling as loop | `server/agents/loop.py:143,650,675,890,620` |
| 5 | App scaffolded but never run: `python main.py` no-op, missing symbol, wrong filename/schema, zero tests | D5 no verification phase; "done" = files+text | `server/agents/loop.py:100,919` · manifest · completion logic |
| 6 | 15 turns / 68.4k tokens / looped to a stall-force finish | D6 context pressure, late summarization, lenient stall | `server/agents/context.py:6,253` · `server/agents/loop.py:420,935` |
| 7 | ruff `I001`/`F401` shipped unfixed in generated files | D7 auto-lint reports, never fixes/gates | `server/toolkit/auto_lint.py` · `server/toolkit/executor.py:172` · `server/agents/loop.py` |
| 8 | 3 incompatible schemas, 2 generators, README (GET) vs code (POST) vs summary (`/data/*`) | G2/G3 no contract or docs validation | Missing capabilities (Section 2) |
| 9 | Wall of `▲ [WARNING]` lines | U1 all warnings rendered equal | `tui/src/components/Display/Scenario/WarningBlock.tsx:31` + warning emission sites |
| 10 | Duplicate success card + summary; over-claimed success | U2 + D5 | `tui/src/components/Display/Scenario/SuccessCard.tsx` · `server/agents/loop.py` |
| 11 | Footer `[███...] 53%` gauge | U3 unconditional gauge | `tui/src/components/Input/ComposerGauge.tsx` |

---

## 5. What we want — consolidated acceptance behaviour (codebase, not artifact)

1. **Cwd integrity (D1):** no command with a cwd-changing prefix ever runs in the wrong directory; either the prefix is honored as cwd or the tool demands an explicit `workdir`.
2. **Honest success (D2):** a tool result is "success" only with real evidence; known Windows failure signatures fail loudly; "verification passed" claims are backed by executed output.
3. **Background jobs (D3):** completion is an event in the turn; a non-zero exit is a failure the agent must handle before finishing; no silent absorption.
4. **Polling vs looping (D4):** read/poll tools with identical params are never blocked; tool discovery is idempotent; skip warnings are once-per-turn and compact.
5. **Verify before success (D5):** project-generation tasks include a run/verify step; the manifest carries `verified: true/false`; an unverified claim can never be reported as success.
6. **Bounded context (D6):** the turn ends when the ask is fulfilled; transcript pressure is trimmed proactively, not at an emergency threshold.
7. **Clean output (D7):** generated code is lint/format clean at completion, enforced not just reported.
8. **Scaffold conventions (G1–G4):** the agent applies concrete, verifiable project conventions (entrypoint, tests, schema contract, docker hygiene, docs consistency).
9. **Calm UI (U1–U3):** mechanical events collapse to a compact status line; one consolidated, accurate completion block; optional token gauge.

---

## 6. Status

- **Documentation status:** DRAFT — problem inventory, codebase-linked. No fixes applied.
- **Dependency:** Items D1–D7 are prerequisites for the artifact ever being fixable; the generated `agg-bar-prism` folder is a symptom, not a target. Any later artifact repair must be driven by these codebase changes (re-generate/repair via a fixed loop), not by hand-editing the scaffold.
- **Open decision:** Track D1–D7 here (this file) or fold into the main `todo.md` tracker; whether the verification phase (D5) applies to all build tasks or only project-generation tasks.
