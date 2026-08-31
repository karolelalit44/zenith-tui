# Config Management

## Overview

How zenith loads, merges, and exposes configuration (env vars, files, defaults, provider config, mode configs).

### How opencode does it

- `config.ts` / `loader.ts` / `defaults.ts`: layered config â€” defaults â†’ **environment** â†’ **config file** (`opencode.json`) â†’ CLI flags. Negative-array-merge semantics for arrays.
- Config file drives most behavior; env vars override select values. A single `loadConfig()` produces a typed `Config` object with properties (provider, model, permissions, hooks, mcp, etc.).
- Agent/mode definitions (build/plan) in `agent/` and command config in `command/`. Model + agent are first-class config fields.

### How codex does it

- Layered config (`config/layer.rs`): `ConfigLayer` from file + env + defaults, merged in order; **CSV/env-specific parsing**; `configure` merges layers.
- `config/` has typed sections: `Model`, `MCP`, `Sandbox`, `PerPermissions`, `Hook`, `ChatGPT`, etc.; `ConfigLayer::merge` combines with clear precedence.
- `LocalConfig`/`GlobalConfig`/`UserConfig` split by scope (repo vs user).

### What zenith has today

**Files:**
- `server/config/constants.py` (486) â€” every constant in one file (mode budgets, tool sets, guidance levels, mkdir tool sets, request canons, etc.).
- `server/config/env.py` â€” `optional_env`, `optional_int`, `optional_float`, `optional_int_none` helpers.
- `server/config/loader.py` (200) â€” `load_config()` reading env + file; honors `ZENITH_*` vars.
- `server/config/settings.py` â€” `AppSettings` pydantic model, `AgentModeConfig` (PLAN/BUILD/READ_ONLY/CREWMATE modes), `ToolConfig`, `McpServerConfig`, `HooksConfig`, `BootstrapDefaults`, `DEFAULTS`.
- `server/config/providers.py` â€” `ProviderConfig`.

### What is correct

- `AppSettings` pydantic model with env overrides is a reasonable config core.
- Env helpers (`optional_*`) are clean.

### What is wrong / over-engineered / incorrect / missing

**Over-engineered / incorrect:**
- `constants.py` as a single 486-line grab-bag of unrelated constants (agent-loop guidance, explore budgets, graph tools, toolscapes, mode budgets). opencode/codex keep config near the module that owns it; the constants module conflates tunables and fixed values.
- **Agent mode configs** (PLAN/BUILD/READ_ONLY/CREWMATE) that gate allowed_tools and push schema-escalation are not opencode/codex's model. opencode/codex attach permitted tools per **agent**, but do not maintain a 4-mode toolscape system with dynamic schema promotion (see tool_service).
- The **CREWMATE_MODE** and build-mode `crewmate=True` flags belong to the delegation subsystem slated for removal.

**Missing:**
- A real config **file** (zenith is essentially env-driven; opencode/codex are file-driven with layered precedence). `loader.py` reads env + limited file.
- Scoped configs (repo vs user/global) like codex's `LocalConfig`/`GlobalConfig`.
- Consistency: settings constants scattered between `constants.py` and `settings.py` and `env.py`.

## What we will do

- Consolidate config into a typed `AppSettings` loaded with clear precedence: defaults â†’ config file â†’ env â†’ CLI/API.
- Move constants to the module that owns them (no single grab-bag).
- Reduce agent modes to a simple per-agent tool permission set; remove the 4-mode dynamic toolscape and CREWMATE mode.
- Support repo vs user scoped config (codex-style) if useful.

## What we will REMOVE
- The 486-line `constants.py` grab-bag (redistribute constants to owning modules).
- PLAN/BUILD/READ_ONLY/CREWMATE **mode toolscape** system + dynamic schema escalation (see tool_service).
- `CREWMATE_MODE`, build `crewmate=True` flags (delegation removal).
- Explore/budget constants already slated for removal in other modules.

## Regex audit
| Regex | opencode/codex uses it? | Action |
|---|---|---|
| (none specific here) | â€” | â€” |

## Verification / signoff
- [ ] Typed settings with layered precedence (defaults â†’ file â†’ env â†’ CLI)
- [ ] Constants redistributed to owning modules
- [ ] Simple per-agent tool permission, no 4-mode toolscape
- [ ] CREWMATE/mode-gating removed
- [ ] ruff + pytest + runtime smoke pass

## Status: In-Progress

## Report (Jupiter Worker)

```
Module: 14 config_management
Status change: Pending → In-Progress (safe-additive portion done; removals blocked)
WHAT: Documented + locked the layered precedence model (defaults → file → env →
      CLI) in settings.py/loader.py; added precedence-confirmation tests.
WHY: matches opencode/codex layered config (defaults → env → file → CLI); the
     merge order is now explicit and test-enforced.
FILES: server/config/settings.py, server/config/loader.py, server/tests/test_config.py
OPEND/REMOVED: no removals yet — see BLOCKED.
EXPECTED BEHAVIOUR: settings load with defaults→file→env→CLI precedence; precedence
     is documented and covered by 5 new tests (all green).
OUTCOME / TEST EVIDENCE: G1 partial (13 config tests pass); G3 ruff clean (verify);
     G2 targeted suite green; G6 PASS (no new features).
SHARED-FILE IMPACT: none (kept constants.py untouched — CCS).
DEPENDENCIES: BLOCKED on module 01/02/07 interface-lock for the rest:
     - constants.py grab-bag redistribution touches files owned by 04/03/01/05
       (module ownership map §4) → not safe to do while they are Pending.
     - PLAN/BUILD/READ_ONLY/CREWMATE toolscape removal touches loop.py (01),
       prompt_executor.py (02), handlers.py (10) → blocked on their interface-lock.
     - CREWMATE_MODE/graph constants belong to OOS module 11 (delegation) → out of scope.
     Needs: 01, 02, 07 interface-locked before completing the removals.
```
