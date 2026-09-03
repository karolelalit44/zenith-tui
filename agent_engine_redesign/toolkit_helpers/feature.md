# Toolkit Helper / Utility Modules

## Overview

Standalone helper modules in `server/toolkit/` (non-tool files) and `server/shell_runner.py`. Audit against opencode/codex to decide keep / remove / reframe.

### How opencode does it

- **Brace expansion:** opencode does not expand braces itself â€” it hands globs to **ripgrep** (`tool/grep.ts`/`glob.ts`), which natively handles `*.{ts,tsx}`. codex relies on shell grep.
- **Auto-lint:** Neither reference auto-runs post-write lint/security scanning.
- **Command safety:** codex has permission tiers via OS sandboxing + approval gates (`exec.rs`, `shell_spec sandbox_permissions`), NOT a static read-only/destructive command-name classifier.
- **Digest / catalog:** No analogues. References return raw tool outputs; neither maintains a capability-descriptor registry.
- **Shell runner:** opencode `tool/shell.ts` uses `CWD`/`FILES`/`CMD_FILES` guard sets and `MAX_METADATA_LENGTH=30_000`. codex `exec.rs` + `shell_spec.rs` provides `exec_command` with `cmd`, `workdir`, `tty`, `yield_time_ms`, `max_output_tokens`, `sandbox_permissions`/`justification`/`prefix_rule`, session persistence (`write_stdin`), truncation accounting, and **Windows-specific destructive-command safety rules** (shell_spec.rs:339-344: no cross-shell deletion composition, `-LiteralPath`, verify resolved target before recursive delete).

### How codex does it

See above â€” codex (`exec.rs`, `shell_spec.rs`) uses OS sandboxing + approval gates rather than name classifiers or brace splitters; its `exec_command` carries `workdir`, `yield_time_ms`, `max_output_tokens`, `sandbox_permissions`, and Windows destructive-command safety. It has no capability-descriptor registry (`catalog.py` analogue) and no auto-lint.

### What zenith has today

Standalone helper modules in `server/toolkit/` (non-tool files) and `server/shell_runner.py`: `shell_runner.py`, `auto_lint.py`, `command_safety.py`, `catalog.py`, `digest.py`, `param_normalizer.py`, `path_validator.py`, `command_result.py`.

### Zenith modules and verdict

| zenith module | opencode/codex counterpart? | Verdict |
|---|---|---|
| `shell_runner.py` (63) â€” `run_shell_command`, `resolve_shell`, PowerShell on Windows | opencode shell.ts / codex exec.rs | **Real, but thin** â€” add codex Windows safety rules + `max_output_tokens` truncation accounting; consider permission/session support. Fold into `command_runner`. |
| `auto_lint.py` (157) â€” `detect_security_pitfall` | None | **Remove** â€” no reference auto-lints; invented regex heuristic. |
| `command_safety.py` (466) â€” `READ_ONLY_COMMANDS` tier classifier | codex uses sandbox + approval, not name-classifier | **Reframe** into genuine permission/approval model (see `permissions/feature.md`). |
| `catalog.py` (303) â€” `CapabilityDescriptor`, `CAPABILITIES` domain/risk/cost/latency | None | **Remove/trim** â€” speculative capability registry; no reference counterpart. |
| `digest.py` (80) â€” `format_tool_digest` 1-line structured output | None (raw outputs) | **Optional** token-economy nicety; keep only if it demonstrably saves tokens. |
| `param_normalizer.py` (136) â€” normalize tool params | â€” (schema decode handles it) | **Re-evaluate** â€” opencode/codex decode params from JSON schema directly; normalize only what schema decode misses. |
| `path_validator.py` (18) â€” path safety | codex sandbox read-grants | **Keep** minimal; expand for Windows safety. |
| `command_result.py` (24) | â€” | Keep minimal. |

### What is correct

- `shell_runner.py` Windows shell selection + subprocess + capture is a sound baseline.
- `path_validator.py` path-safety direction is reasonable.

### What is wrong / over-engineered / incorrect / missing

- `auto_lint.py`, `catalog.py` are **unsupported by the references** and should be removed (or heavily trimmed).
- `command_safety.py` mis-claims Codex parity; the static tier classifier should be reframed as a real permission/approval model.
- `shell_runner.py` lacks codex's Windows destructive-command safety rules, output/truncation budget, and (optionally) permission tiers / session persistence.

## What we will do

- Fold `shell_runner.py` into `command_runner`, adding codex Windows safety rules + truncation budget.
- Implement param decoding via JSON schema (reduce `param_normalizer` to gaps only).
- Keep a minimal `path_validator` with Windows read-grant safety.
- Consolidate `command_result.py`.

## What we will REMOVE
- `brace_expand.py` (rely on ripgrep for brace globs)
- `auto_lint.py` (no reference auto-lints)
- `catalog.py`/`CapabilityDescriptor` capability registry (trim)
- `command_safety.py` static command-name tier (reframe to permission model)

## Regex audit
| Regex | opencode/codex uses it? | Action |
|---|---|---|
| `_SECURITY_NAME_HINT`/`_FAST_HASH_HINTS` | No | Remove |

## Verification / signoff
- [x] brace_expand removed; auto_lint / capability catalog pending
- [ ] command_safety reframed as permission model
- [ ] shell_runner folds into command_runner with Windows safety + truncation
- [ ] param decode via schema, minimal path_validator
- [ ] ruff + pytest + runtime smoke pass

## Status: In-Progress (Blocked)

## Report (Jupiter Worker)

```
Module: 23 toolkit_helpers
Status change: Pending → In-Progress (Blocked)
WHAT: Claimed for audit. `brace_expand.py` has already been removed; the remaining helper removals stay blocked on live consumers.
     The unsupported auto-lint security heuristic has been removed, while lint
     execution remains intact. The
      speculative capability catalog is gone; discovery now groups tools from the
      live registry directly.
WHY: matches opencode/codex (ripgrep handles brace globs; no auto-lint; sandbox+approval, no name classifier).
FILES: `server/toolkit/brace_expand.py` deleted; owned helpers now include `auto_lint.py`,
       `catalog.py` (inventory only), `command_result.py`, `command_safety.py`,
       `digest.py`, `param_normalizer.py`, `path_validator.py`.
OPEND/REMOVED: `brace_expand.py` removed from the live tool path; `auto_lint`
     security heuristic removed; capability catalog removed in favor of direct
     registry grouping.
EXPECTED BEHAVIOUR: glob/grep rely on ripgrep-native brace handling; discovery
     uses the live registry directly; shell_runner remains folded into command_runner
     for a later phase.
OUTCOME / TEST EVIDENCE: brace-expansion regression slice passed (12 focused
     glob/grep tests; Ruff clean); auto-lint helper trim validated (4 focused
     TestAutoLint tests; Ruff clean); catalog/discovery slice passed (39 focused
     tests; Ruff clean).
SHARED-FILE IMPACT: none taken.
DEPENDENCIES: BLOCKED on module 03/04/05 interface-lock:
     - shell_runner owned by module 05 (command_runner) — fold there, not here.
     - command_safety used by loop.py (module 01) + permissions (OOS module 22).
     Needs 05 to fold shell_runner.
```
