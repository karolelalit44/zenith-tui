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

Standalone helper modules in `server/toolkit/` (non-tool files) and `server/shell_runner.py`: `shell_runner.py`, `brace_expand.py`, `auto_lint.py`, `command_safety.py`, `catalog.py`, `digest.py`, `param_normalizer.py`, `path_validator.py`, `command_result.py`.

### Zenith modules and verdict

| zenith module | opencode/codex counterpart? | Verdict |
|---|---|---|
| `shell_runner.py` (63) â€” `run_shell_command`, `resolve_shell`, PowerShell on Windows | opencode shell.ts / codex exec.rs | **Real, but thin** â€” add codex Windows safety rules + `max_output_tokens` truncation accounting; consider permission/session support. Fold into `command_runner`. |
| `brace_expand.py` (82) â€” `expand_braces`, custom splitter, `_MAX_BRACE_EXPANSIONS=64` | None (ripgrep natively) | **Remove** â€” a bespoke splitter duplicates ripgrep and risks diverging from real glob semantics. |
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

- `brace_expand.py`, `auto_lint.py`, `catalog.py` are **unsupported by the references** and should be removed (or heavily trimmed).
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
| `_MAX_BRACE_EXPANSIONS` expander | No (ripgrep) | Remove |
| `_SECURITY_NAME_HINT`/`_FAST_HASH_HINTS` | No | Remove |

## Verification / signoff
- [ ] brace_expand / auto_lint / capability catalog removed
- [ ] command_safety reframed as permission model
- [ ] shell_runner folds into command_runner with Windows safety + truncation
- [ ] param decode via schema, minimal path_validator
- [ ] ruff + pytest + runtime smoke pass

## Status: In-Progress (Blocked)

## Report (Jupiter Worker)

```
Module: 23 toolkit_helpers
Status change: Pending → In-Progress (Blocked)
WHAT: Claimed for audit. No code change yet — helper removals are unsafe while dependents are Pending.
WHY: matches opencode/codex (ripgrep handles brace globs; no auto-lint; sandbox+approval, no name classifier).
FILES: none changed (owned: auto_lint.py, brace_expand.py, catalog.py, command_result.py,
       command_safety.py, digest.py, param_normalizer.py, path_validator.py)
OPEND/REMOVED: none yet.
EXPECTED BEHAVIOUR: (target) brace_expand/auto_lint/catalog removed; shell_runner folded into
     command_runner with codex Windows-safety + truncation; command_safety reframed to permissions.
OUTCOME / TEST EVIDENCE: G1 not started — blocked.
SHARED-FILE IMPACT: none taken.
DEPENDENCIES: BLOCKED on module 03/04/05 interface-lock:
     - brace_expand.expand_braces imported by glob.py + grep.py (module 04).
     - catalog.is_known_capability imported by registry_validation.py (module 03).
     - shell_runner owned by module 05 (command_runner) — fold there, not here.
     - command_safety used by loop.py (module 01) + permissions (OOS module 22).
     Needs 03 and 04 interface-locked to remove brace_expand/catalog; 05 to fold shell_runner.
```
