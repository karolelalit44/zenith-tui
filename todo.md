# Remaining Work — Zenith Refactor

Status legend: `[ ]` open · `[x]` done
Branch: `fix/ser-tu-communication-n-separations` · Git held until instructed.
Baseline: backend **416 passed**, frontend **90 passed**, ruff clean (after Tasks1–9 + quick cleanup).

---

## A. Dead code

### 1. Remove dead JSON-RPC methods — `server/api/handlers.py` — [x] 5 removed

**REMOVED (5 truly-dead, no test refs, frontend never sends):**
- `permission.grant`, `permission.revoke`, `permission.list`, `plan.approve`, `plan.reject`
- Handlers `_permission_grant`/`_permission_revoke`/`_permission_list`/`_plan_approve`/`_plan_reject`
  + orphaned helper `_resolve_permission_service` + now-unused `SessionState` import.
- Verified: no lingering refs; ruff clean; full suite **416 passed**; excluded e2e websocket **14 passed**.

**SCOPE CORRECTED (audit premise was wrong — the other 9 are NOT dead):**
- **`session.search` — KEPT (NOT dead).** `server/tests/test_search_index.py` (DEFAULT suite) calls
  `handlers._session_search()` directly (lines 189, 216) asserting hits + error code.
- **`session.export`, `provider.validate`, `provider.models`, `tools.list`,
  `workspace.status/diff/log/repo_map` (8) — KEPT.** Exercised ONLY by excluded e2e tests:
  `test_e2e_integration.py` (tools.list 194,452,468,477 · provider.validate 422,436 ·
  provider.models 429,443 · session.export 490 · workspace.*), `test_e2e_websocket.py`
  (tools.list 321 · provider.validate 333), `e2e_real.py` (workspace.status 141).
  Removing these 8 requires rewriting those e2e tests. **Decision needed.**

**Evidence they're dead:** frontend `tui/src/` sends none of the 14 strings (verified via grep).

---

## B. Persistence consolidation

### 2. Replace `provider_config_repo.py` sync engine — [ ] DEFERRED (high risk, low value)

**Decision:** skip. Consumers are legitimately **sync** (`config/loader.py` at CLI startup, `providers/validation.py`).
Forcing async ripples into sync startup paths (`config/__init__` → loader) — wide blast radius, no behavior
improvement. The engine remains; the sync functions it backs are still exercised by tests.

### 3. Convert 9 raw `text()` SQLite upserts → dialect `insert().on_conflict_*` — [x] DONE

Converted with `sqlalchemy.dialects.sqlite.insert` (`sqlite_insert`):
- `repositories.py` (4): `INSERT ... ON CONFLICT(provider_id,id) DO NOTHING` → `sqlite_insert(ProviderModelRecord).on_conflict_do_nothing(index_elements=["provider_id","id"])` · `SELECT id ...` → `select(ProviderModelRecord.id)` · `DELETE ...` → `delete(ProviderModelRecord).where(...)` · `INSERT OR REPLACE INTO pricing` → `sqlite_insert(PricingRecord).on_conflict_do_update(index_elements=["provider","model_id"], set_=...)`
- `provider_config_repo.py` (5): `active_provider` + `model_store` upserts → `sqlite_insert(AppSettingRecord).on_conflict_do_update` · `INSERT OR IGNORE INTO providers` → `on_conflict_do_nothing(index_elements=["id"])` · `provider_models` upsert → `on_conflict_do_update(index_elements=["provider_id","id"])` · `DELETE app_settings` → `delete(AppSettingRecord).where(...)`

**Result:** zero raw `text()` SQL remains in either file. Added imports `ProviderModelRecord`, `PricingRecord`, `sqlite_insert`. Removed `text` import (now unused). Verified: ruff clean, targeted tests (provider_api/openai_compatible/permission) pass.

---

## C. Magic numbers / strings (large, mechanical, low risk)

### 4. `128000` context-window default — [x] DONE (production)

Added `DEFAULT_CONTEXT_WINDOW = 128000` to `server/config/constants.py`; replaced in **14 production files**:
`agents/context.py`, `agents/prompts.py`, `agents/prompt_executor.py`, `agents/validation.py`, `api/provider_validation.py`, `api/schemas.py`, `config/settings.py`, `persistence/provider_config_repo.py`, `persistence/repositories.py`, `providers/base.py`, `providers/llm_provider.py`, `providers/registry.py`, `providers/validation.py`, `toolkit/executor.py`.

**Left as literal:** `persistence/models.py:110,161` (`server_default="128000"`) — importing config.constants into models.py creates an import cycle (config→loader→provider_config_repo→models); it's a SQLite DDL default, not Python config. **Test literals untouched** (assert behavior; changing them is churn).

Verified: ruff clean; import chain `server.main` + `server.api.server` loads (no cycle); targeted tests pass.

### 5. `"build"` / `"plan"` mode literals — [x] DONE

Re-added `BUILD_MODE = "build"` / `PLAN_MODE = "plan"` to `config/constants.py` (were deleted in Task6 as "unused"). Replaced literals in **16 files**:
`agents/loop.py` (defaults + comparisons + tool-registry mode), `agents/recovery.py`, `agents/sub_agent.py`, `api/handlers.py`, `config/settings.py` (`AgentModeConfig.name` + `AGENT_MODES` keys), `agents/prompts.py`, `agents/prompt_executor.py`, `domain/hooks.py`, `toolkit/base.py`, `toolkit/registry.py`, `toolkit/tools/{file_delete,file_edit,file_write,lsp_rename,multi_edit}.py` (`requires_mode`).

`domain/domain.py` `ScenarioMode` enum now references the constants (`BUILD = BUILD_MODE`, `PLAN = PLAN_MODE`).

**Left as literal (intentional):** `workspace/repo_map.py:19` + `agents/context.py:168` `"build"` — code-relevance keyword / sort key, NOT mode strings · `agents/prompt_executor.py:231` `{"plan": ...}` — data dict key.

Verified: ruff clean (removed unused `PLAN_MODE` import from handlers.py); targeted tests pass.

---

## D. Structure (high effort/risk — defer)

### 6. God-object / long-function refactors — [x] DONE (Item 6 completed)

| File | Size | What was done |
|---|---|---|
| `server/agents/loop.py` | 792 → ~750 | Extracted 4 duplicated "summarize + rebuild" blocks into `_summarize_and_rebuild()` (yields `_maybe_summarize` events, writes rebuilt messages to a result holder); dedupes the 10-arg `_rebuild_messages` call ×4 |
| `server/agents/prompt_executor.py` | 538 → ~500 | Extracted `_load_plan_context()`, `_maybe_emit_plan_ready()`, `_persist_plan_output()`, `_persist_assistant_message()` from `_execute` |
| `server/api/handlers.py` | 631 → ~600 | Extracted `_validate_override_number()`, `_ensure_prompt_session()`, `_resolve_provider_for_prompt()`, `_persist_model_override()` from `_prompt` (130 → ~100 lines) |
| `server/persistence/repositories.py` | 1158 → package | Split by domain into `server/persistence/repositories/` package: `base.py` (load_catalog/_iso/_seed_providers_from_catalog), `sessions.py` (SessionRepository/MessageRepository), `providers.py` (ProviderRepositoryDB), `token_usage.py` (TokenUsageRepository), `misc.py` (Checkpoint/SyncEvent/StatusHistory/Draft), `__init__.py` re-exports full public API. No caller changes needed |

**Validation:** per-file ruff check + format clean; ruff `server/` all checks pass; targeted suites pass:
loop (`test_compaction`/`test_context`/`test_integration`/`test_e2e`), prompt_executor+handlers (`test_prompt_overrides`/`test_transport`),
repositories (`test_db`/`test_provider_api`/`test_sync_log`/`test_blob_store`/`test_search_index`/`test_hooks`/`test_workspace`).
Runtime sanity: `python -m server.main status` + `serve` boot OK (migrate → connect → ensure_seeded → config load).
Frontend: biome lint clean, vitest **90 passed**, `tsc` build clean.

**Pre-existing environment issues (NOT caused by Item 6):**
- `test_config.py::test_load_config` + `test_e2e.py::test_e2e_config_bootstrap` fail: assert `active_provider == ""`
  but `data/zenith.db` has `active_provider='openrouter'` persisted (env drift; read via `provider_config_repo`, untouched).
- 3 `test_mcp.py` async subprocess tests hang on this Windows host (stdio MCP subprocess; `server/mcp` does not
  import any refactored module). All other mcp tests pass.

---

## E. Housekeeping

- [ ] **7. Commit all pending changes** — working tree holds Tasks1–9 + cleanup + items A1–C5 when done. Git held per user instruction; user to authorize commit.
