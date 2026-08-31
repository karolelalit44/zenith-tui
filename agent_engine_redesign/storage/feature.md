# Storage Layer

## Overview

How zenith persists sessions, messages, provider config, usage, search, and catalog data.

### How opencode does it

- File-based JSON under `Global.Path.data/storage/` (`storage/storage.ts`: RootFile/SessionFile/MessageFile/DiffFile/SummaryFile schemas, read/write/update/remove/list with per-target `TxReentrantLock`, migration marker). **Plus** SQLite tables for Account/Project/Session/Message/Part/Todo/SessionShare/Workspace (`storage/schema.ts`).

### How codex does it

- **SQLite-backed** state runtime (`codex_state::StateRuntime` via rollout `state_db.rs`), rollout-file backfill, read-repair, reconciliation. Persistence via external `codex_thread_store` + `codex_rollout::state_db`.

### What zenith has today

- File-based, **one append-only JSONL per session** (`session_file.py`: header/meta/stats/msg/sync/usage/checkpoint/wsfile) with atomic `.bak` rewrites (`atomic.py`).
- Repositories: `session_store.py`, `usage_store.py`, `search_store.py`, `catalog_store.py`, `profile_store.py`, `workspace_store.py`, `provider_config.py`, `builtin_seed.py`, `catalog_compat.py`, `paths.py`.
- `sessions/export.py`, `sessions/import_service.py`.

### Verdict per store (real vs invented)

| Store | Real counterpart? | Verdict |
|---|---|---|
| `session_store.py` | opencode SessionFile/Messages; codex session | **Real** â€” keep |
| `profile_store.py` | opencode/openai creds; codex auth | **Real** â€” keep |
| `catalog_store.py` | opencode provider catalog / codex model_catalog | **Real concept**, but name collides with opencode/codex `McpCatalog`/`mcp_server_catalog` â€” **rename** to provider/model catalog |
| `provider_config.py` | config provider section | **Real** â€” keep |
| `builtin_seed.py` | bundled catalog | **Real** â€” keep (but simplify seed-merge, see below) |
| `atomic.py` | opencode `fs.writeJson` | **Real/defensible** â€” keep |
| `session_file.py` | append-only imperative | **Real** â€” keep |
| `usage_store.py` | codex usage; opencode none | **Semi-real** â€” real run-recording; **over-engineered** aggregation/efficiency metrics hardcoded to zeros |
| `search_store.py` | **neither engine has one** | **Invented** â€” linear-scan repo with `index_parity()` vs a removed FTS index (self-referential dead code). Remove unless productized. |
| `workspace_store.py` (`wsfile`) | opencode/codex track no per-file edit/write registry | **Invented** â€” per-session edit-count/content-hash registry is zenith-unique. Remove unless needed. |

### What is correct

- Single append-only JSONL per session is a coherent simplification (vs codex's SQLite + backfill) and appropriate for a local TUI harness. No SQLite needed.
- `atomic.py` `.bak` sibling + retry is defensible for single-file sessions.
- `PROFILE_LOCK` threading reasoning is correct (asyncio + FastAPI threadpool both write).

### What is wrong / over-engineered / incorrect / missing

**Over-engineered:**
- `usage_store` aggregation surface: `record(...)` with 15 args, pricing cache, per-step + aggregate + efficiency reporting; `get_efficiency`'s `waste_ratio`/`summarization_count`/`average_context_utilization` are **hardcoded 0.0/0** (`usage_store.py:250-253`) â€” dead/aspirational scaffolding from removed context-degradation diagnostics.
- `catalog_store._refresh_seed` elaborate merge logic (185-222) â€” opencode rebuilds from `models.dev`; codex loads a bundled JSON wholesale. Surgical seed-merge is more than either needs.
- **Dual catalog paths** â€” `catalog_store.py` + `catalog_compat.py` (threading cache, `EMPTY_CATALOG`) creates a second read path.
- `search_store.py` linear-scan replace of an FTS5 index neither engine ships.

**Naming:**
- `catalog_store` collides with the unrelated `McpCatalog` concept in both references.

**Missing:**
- Nothing critical; storage is broadly sound.

## What we will do

- Keep: `session_store`, `profile_store`, `provider_config`, `builtin_seed` (simplified), `atomic`, `session_file`.
- Rename catalog to avoid the `McpCatalog` collision.
- Remove `search_store` (or productize real search).
- Remove invented `workspace_store` per-file edit registry.
- Reduce `usage_store` to real run-recording; drop the hardcoded-zero efficiency metrics.

## What we will REMOVE
- `search_store.py` (and `index_parity()` scaffolding) unless productized
- `workspace_store.py` per-file `wsfile` registry
- `usage_store` efficiency/`waste_ratio`/`summarization_count` placeholder metrics
- Dual catalog path (`catalog_compat` read path) â€” single catalog store
- Elaborate `_refresh_seed` merge (simplify)

## Regex audit
| Regex | opencode/codex uses it? | Action |
|---|---|---|
| (none specific here) | â€” | â€” |

## Verification / signoff
- [ ] Invented stores (search, workspace per-file) removed
- [ ] usage_store trimmed to real run-recording
- [ ] Single catalog store, renamed, simplified seed
- [ ] append-only JSONL + atomic keep
- [ ] ruff + pytest + runtime smoke pass

## Status: In-Progress (Blocked)

## Report (Jupiter Worker)

```
Module: 21 storage
Status change: Pending → In-Progress (Blocked)
WHAT: Claimed for audit. No code change yet — removals are unsafe while dependents are Pending.
WHY: matches codex/opencode single real store; append-only JSONL + atomic is the correct model.
FILES: none changed (owned: server/storage/*.py, sessions/export.py, import_service.py)
OPEND/REMOVED: none yet.
EXPECTED BEHAVIOUR: (target) real stores kept, search_store + workspace_store removed,
     single catalog (renamed), usage_store trimmed to run-recording.
OUTCOME / TEST EVIDENCE: G1 not started — blocked.
SHARED-FILE IMPACT: none taken.
DEPENDENCIES: BLOCKED on module 07/10/16 interface-lock:
     - FileSearchRepository + FileWorkspaceRepository are imported by handlers.py (module 10).
     - workspace_store FileWorkspaceRepository is the workspace_repo fixture & repo (07/16).
     - catalog_compat dual read path consumed by providers (13), context (06), loop (01).
     Needs 07, 10, 16 interface-locked before removing invented stores; also 13/06 for catalog path.
```
