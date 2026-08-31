# Permissions / Approval

## Overview

Whether and how the harness asks for, gates, or escalates user permission before risky operations (file mutation, destructive commands, external requests).

### How opencode does it

- **`Permission` system** (`permission/`): `allow` / `deny` / `ask` per (tool, input) via a permission profile loaded from config. `Permission.ask()` prompts the user interactively; the tool blocks until approved/denied.
- Each tool declares its own permission needs (`metadata.permission`). The TUI renders an interactive ask dialog.
- **Subagent permissions**: child agents have their own profiles; the parent's restrictions only govern the parent (`agent/subagent-permissions.ts`).

### How codex does it

- **Sandboxing + approval gates** (`exec.rs`, `exec_policy.rs`, `sandboxing/`): `sandbox_permissions` per command, `require_escalated`, `prefix_rule`. OS/process-level sandboxing plus structured approval for network and destructive ops. `PERMISSIONS` from config and approval templates.
- Windows-specific destructive-command safety encoded in the tool spec (no cross-shell deletion composition, verify resolved path before recursive delete).

### What zenith has today

- `server/toolkit/command_safety.py` (466): `READ_ONLY_COMMANDS`, a tier model (`read_only`/`workspace_write`/`network`/`destructive`), docstring claims "Claude Code and Codex" inspiration; auto-approval flags `auto_risky`, `auto_overwrite` in settings.
- `server/toolkit/auto_lint.py` (157): `detect_security_pitfall` regex heuristic for "fast-hash" password writes.
- Approval config: `auto_approve_plan`, `auto_overwrite`, `auto_risky` (config/settings.py).
- `server/toolkit/middleware/safety.py` and plan_write hooks.

### What is correct

- The *concept* of classifying dangerous operations and asking before them is directionally sound as a policy/permission layer.

### What is wrong / over-engineered / incorrect / missing

**Over-engineered / invented:**
- `auto_lint.py` `detect_security_pitfall` â€” **no reference auto-lints** / runs a regex security classifier. Invented, prone to false positives/negatives. Remove.
- `command_safety.py` claims a tier model inspired by "Claude Code and Codex", but codex's real model is **OS sandboxing + approval gates**, not a static command-name classifier (`READ_ONLY_COMMANDS` set). The heuristic tier is a weaker, different mechanism than what it claims to mirror.

**Missing:**
- A real **Permission.ask()** interactive flow with per-tool permission profiles (opencode).
- Codex's **sandboxing** and **Windows destructive-command safety rules** in the shell spec (cross-shell deletion composition, resolved-path verification before recursive delete/move).

## What we will do

- Introduce a `Permission` abstraction: per-tool permission profiles (`allow`/`deny`/`ask`) with an interactive ask flow toward the TUI.
- Replace the static command-name tier classifier with a permission model (allow/deny/ask per operation type + approval).
- Add codex's **Windows destructive-command safety rules** to the shell tool/spec.
- Subagent permissions: child agents have their own profiles.

## What we will REMOVE
- `auto_lint.py` (`detect_security_pitfall` regex heuristic)
- `command_safety.py` static `READ_ONLY_COMMANDS` tier classifier (reframe as permission model)
- `auto_risky`/`auto_overwrite` blanket auto-approval flags (replace with per-tool ask/allow)
- Anything that duplicates opencode Permission or codex sandbox semantics

## Regex audit
| Regex | opencode/codex uses it? | Action |
|---|---|---|
| `_SECURITY_NAME_HINT`, `_FAST_HASH_HINTS` (auto_lint) | No | Remove |
| `READ_ONLY_COMMANDS` matching | No (sandbox/approval not name-classifier) | Remove/reframe |

## Verification / signoff
- [ ] Per-tool permission profiles (allow/deny/ask) + interactive ask
- [ ] Windows destructive-command safety rules in shell spec
- [ ] Subagent permissions (child has own profile)
- [ ] auto_lint / command-safety classifier removed
- [ ] ruff + pytest + runtime smoke pass

## Status: Pending
