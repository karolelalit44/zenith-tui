# Zenith Repository Audit Report

Date: 2026-08-04
Branch: `fix/ser-tu-communication-n-separations`
Scope: Python/FastAPI backend (`server/`) + TUI frontend (`tui/`)

## 1. Verification baseline (done checks)

| Check | Result |
|---|---|
| Ruff lint (`server/`) | All checks passed |
| Ruff format (`server/`) | 159 files compliant |
| Biome lint (`tui/`) | 127 files, no issues |
| TypeScript typecheck | Clean |
| Backend tests (from repo root) | 447/447 pass |
| Frontend tests (vitest) | 90/90 pass |
| Docstrings in production | 0 |
| Comments in production | 0 |
| Unused imports (F401/F811) | 0 |

## 2. Dead code

### 2.1 Fully dead modules (zero imports anywhere)

| File | Symbols | Verdict |
|---|---|---|
| `server/app.py` | `AppContainer`, `_StubSessionService` | Delete |
| `server/workspace/service.py` | `WorkspaceService`, `DefaultWorkspaceService`, `GitStatus`, `GitCommit`, `FileVersion` | Delete |

### 2.2 Dead in production — imported only by `__init__.py` re-exports or tests

| File | Symbols | Verdict |
|---|---|---|
| `server/agents/coordinator.py` | `CoordinatorService`, `DefaultCoordinator` | Delete |
| `server/agents/runtime.py` | `AgentRuntime`, `DefaultAgentRuntime` | Delete |
| `server/agents/templates.py` | `PromptBuilder`, `PromptTemplate` | Delete (test-only) |
| `server/sessions/history.py` | `HistoryManager` | Delete (test-only) |
| `server/workspace/tracker.py` | `FileTracker` | Delete (test-only) |

These form a removable cluster with `app.py`. Strip re-exports from `server/agents/__init__.py`, `server/sessions/__init__.py`, `server/workspace/__init__.py` together.

### 2.3 Dead functions/classes (grep-verified, no production callers)

| File: symbol | Verdict |
|---|---|
| `domain/errors.py`: `PersistenceUnavailableError`, `ZenithError.to_dict` | Delete |
| `persistence/logging.py`: `timed_db_log`, `_Timer` | Delete |
| `persistence/repositories.py`: `reset_catalog_cache`, `get_active_provider_id`, `set_active_provider_id`, `get_provider`, `list_providers`, `save_provider`, `get_models_for_provider`, `record_v2`, `get_lifetime_stats`, `list_by_session`, `delete_old`, `list_expired`, `delete_expired` | Delete |
| `api/validation_state.py`: `mark_failed`, `mark_configured`, `snapshot` | Delete |
| `config/env.py`: `require_float` | Delete |
| `toolkit/tools/question.py`: `set_question_callback` | Delete |
| `toolkit/executor.py`: `confirm_risky_command`, `reject_tool` | Delete |
| `providers/retry.py`: `retry_stream`, `RetryPolicy` (+`from_env`/`for_stream`/`calculate_delay`) | Delete |
| `providers/registry.py`: `get_typed`, `require_typed`, `list_typed`, `get_model_capabilities` | Delete |
| `providers/llm_provider.py`: `complete_typed`, `stream_typed`, `list_models_typed` | Delete |
| `providers/responder.py`: `event`, `progress`, `confirmation_request` | Delete |
| `providers/token_counter.py`: `TokenCounter.fallback_usage` | Delete |
| `providers/base.py`: `ProviderService` ABC (nothing implements it) | Delete |
| `api/shutdown.py`: `install_signal_handlers`, `_handle_signal` | Delete |
| `api/websocket.py`: `ConnectionManager.get_sequence` | Delete |
| `domain/message.py`: `Message.is_tool_message`, `Message.get_tool_call_by_id`, `Message.tool_result` field | Delete |
| `domain/session.py`: `Session.to_legacy_dict` | Delete |
| `domain/events.py`: `get_persistent_events`, `dropped_count` | Delete |
| `permissions/service.py`: `set_callback` | Delete |
| `persistence/connection.py`: `Database.executemany` | Delete |
| `sessions/service.py`: `restore_from_checkpoint`, `create_draft`, `promote_draft`, `get_message_count`, `get_token_count`, `initialize`, `complete`, `add_message`, `record_error`, `get_status_history` | Delete |
| `toolkit/tools/agent_tool.py`: `SubAgentTool.set_provider` | Delete |
| `toolkit/tools/background.py`: `is_running`, `list_jobs`, `cleanup_completed` | Delete |
| `toolkit/tools/todo.py`: `get_pending`, `get_completed` | Delete |
| `workspace/git.py`: `GitOps.diffstat` | Delete |
| `lsp/manager.py`: `supports_file`, `shutdown_all`, `active_servers` | Delete |
| `lsp/client.py`: `did_change`, `did_save`, `goto_references` | Delete |
| `api/protocol.py`: `JsonRpcMethod` enum (dispatch uses string literals) | Delete |

### 2.4 Dead API endpoints (no client, no test, no script caller)

| Route | Verdict |
|---|---|
| `GET /usage/token-stats/{session_id}` | Delete |
| `POST /usage/seed-pricing` | Delete (startup seeds directly) |

Keep (conventional ops endpoints, exercised by e2e tests): `GET /health`, `GET /status`.

### 2.5 Dead JSON-RPC methods (no client sends them; no test)

`session.export`, `session.search`, `provider.validate`, `provider.models`, `tools.list`, `workspace.status`, `workspace.diff`, `workspace.log`, `workspace.repo_map`, `permission.grant`, `permission.revoke`, `permission.list`, `plan.approve`, `plan.reject`.

Decision: **Remove**. The TUI client (`tui/src/services/transport/WebSocketClient.ts` + all screens) sends none of these; no test exercises them. Removing shrinks the protocol surface to what the client actually uses.

### 2.6 Dead SQLAlchemy models

| Model | Status |
|---|---|
| `PricingRecord` | Table written via raw SQL in `repositories.py:826` — model unused |
| `BudgetEventRecord` | Table `budget_events` never referenced |
| `PermissionRecord` | Table handled via raw SQL in `permission_repo.py` — model unused |

Decision: after ORM conversion (see §4), `PermissionRecord` becomes used. `PricingRecord` and `BudgetEventRecord` — verify table existence before deleting (check migrations). If `budget_events`/`pricing` tables are created but never written, remove the migration DDL too.

### 2.7 Dead frontend files

`src/components/Display/TokenBurnMeter.tsx`, `src/components/Model/ModelSelect.tsx`, `src/components/Model/ProviderSelect.tsx`, `src/components/ui/PromptInput.tsx`, `src/components/WelcomeView.tsx`, `src/context/useStore.tsx`, `src/hooks/useNotifications.ts`, `src/services/api/fetchJson.ts`, `src/services/perf.ts`.

All superseded by `screens/Provider/ProviderPicker.tsx` / `ModelPicker.tsx`, `components/Input/CommandInput.tsx` / `MultiLineTextInput.tsx`, `screens/Welcome/WelcomeScreen.tsx`. Verdict: delete all 9.

## 3. Constants / configuration

### 3.1 Unused constants in `server/config/constants.py` (only re-exported, never consumed)

`METRICS_PATH`, `API_PREFIX`, `CONFIG_PATH`, `SESSIONS_PATH`, `DEFAULT_BASH_TIMEOUT`, `CONTEXT_SUMMARY_THRESHOLD`, `DEFAULT_PROVIDER`, `DEFAULT_MODE`, `PLAN_MODE`, `BUILD_MODE`.

Decision: **Apply the values** where the literal is hardcoded, then keep the constants that are used; delete any that remain unconsumed after applying. Used constants (keep): `DEFAULT_HOST`, `DEFAULT_PORT`, `HOST_ENV_VAR`, `PORT_ENV_VAR`, `WS_PATH`, `HEALTH_PATH`.

### 3.2 Hardcoded mode strings

`"build"` / `"plan"` appear in ~20 production files while `BUILD_MODE`/`PLAN_MODE`/`DEFAULT_MODE` sit unused. Replace with the constants. Note: `agents/context.py:167` and `workspace/repo_map.py:19` use `"build"` as code-relevance keywords/sort keys — lower priority, not mode strings.

### 3.3 Magic numbers (representative; full list in §6 of original sweep)

| Value | Files | Constant |
|---|---|---|
| `128000` | ~15 files (providers, agents, api, persistence) | context window default |
| `4096` | ~10 files | default max output tokens |
| `32768` | registry, validation, llm_provider | max output cap |
| `30` / `60` / `120` | timeouts across tools, agents, domain | per-domain timeout constants |
| `5000` | websocket, responder, blob_store | event/char limits |
| `2000` | blob_store, loop, file_read | line/char limits |
| `30000` | connection, provider_config_repo | SQLite busy_timeout |
| `0.85` | constants.py, context.py, loop.py, file_edit.py | summary threshold |
| `"data/zenith.db"` | connection.py:23,35, settings.py:88 | DB path default |

### 3.4 Inline env-var defaults

`persistence/connection.py:23` `ZENITH_DB_PATH` default `"data/zenith.db"` (3× dup); `api/server.py:40` `ZENITH_WS_TOKEN` default `""`; `api/__init__.py:18` `ZENITH_LOG_LEVEL` default `"INFO"`; `config/loader.py:96,116` `ZENITH_MCP_SERVERS`/`ZENITH_HOOKS` default `""`; `providers/retry.py` re-derives settings.py defaults. Consolidate to one source.

## 4. Database standards — raw SQL inventory

Raw SQL is permitted only in `server/persistence/migrations/`. Violations in application code:

| File:line | Statement | Type | Model available | Difficulty |
|---|---|---|---|---|
| `permission_repo.py:18` | `SELECT * FROM permissions` | single-table | `PermissionRecord` | easy |
| `permission_repo.py:23` | `INSERT INTO permissions (...) VALUES (...)` | single-table | `PermissionRecord` | easy |
| `permission_repo.py:37` | `DELETE ... WHERE tool_name = ?` | single-table | `PermissionRecord` | easy |
| `permission_repo.py:40` | `DELETE ... WHERE tool_name = ? AND session_id = ?` | single-table | `PermissionRecord` | easy |
| `permission_repo.py:46` | `DELETE ... WHERE session_id = ?` | single-table | `PermissionRecord` | easy |
| `provider_config_repo.py:247` | `INSERT OR REPLACE INTO app_settings ...` | upsert | `AppSettingRecord` | medium |
| `provider_config_repo.py:268` | `INSERT OR IGNORE INTO providers ...` | upsert | `ProviderRecord` | medium |
| `provider_config_repo.py:278` | `INSERT INTO provider_models ... ON CONFLICT ... DO UPDATE` | upsert | `ProviderModelRecord` | medium |
| `provider_config_repo.py:415` | `DELETE FROM app_settings WHERE key = :key` | single-table | `AppSettingRecord` | easy |
| `provider_config_repo.py:419` | `INSERT OR REPLACE INTO app_settings ...` | upsert | `AppSettingRecord` | medium |
| `repositories.py:490` | `INSERT INTO provider_models ... ON CONFLICT ... DO NOTHING` | upsert | `ProviderModelRecord` | medium |
| `repositories.py:510` | `SELECT id FROM provider_models WHERE provider_id = :pid` | single-table | `ProviderModelRecord` | easy |
| `repositories.py:521` | `DELETE FROM provider_models WHERE provider_id = :pid AND id = :mid` | single-table | `ProviderModelRecord` | easy |
| `repositories.py:554` | `INSERT OR REPLACE INTO app_settings ...` | upsert | `AppSettingRecord` | medium |
| `repositories.py:674` | `INSERT OR REPLACE INTO app_settings ...` | upsert | `AppSettingRecord` | medium |
| `repositories.py:826` | `INSERT OR REPLACE INTO pricing ...` | upsert | `PricingRecord` | medium |
| `search.py:29` | FTS5 `SELECT ... snippet(message_fts) ... MATCH` | FTS+joins+dynamic SQL | none (FTS virtual table) | hard |
| `search.py:43` | FTS5 `SELECT ... snippet(session_fts) ... MATCH` | FTS+joins+dynamic SQL | none | hard |
| `search.py:58` | `SELECT COUNT(*) AS n FROM messages` | aggregate | `MessageRecord` | easy |
| `search.py:59` | `SELECT COUNT(*) AS n FROM message_fts` | aggregate | none | hard |
| `search.py:60` | `SELECT COUNT(*) AS n FROM sessions` | aggregate | `SessionRecord` | easy |
| `search.py:61` | `SELECT COUNT(*) AS n FROM session_fts` | aggregate | none | hard |

Permitted (not violations): `startup.py` DDL/schema introspection, `connection.py` PRAGMAs + `SELECT 1` health check, `migrations/runner.py`.

**Carve-out decision for FTS5**: SQLite FTS5 has no core-SQLAlchemy API. Keep `search.py` as an isolation-bounded raw-SQL module; register the FTS virtual tables as ORM `Table` objects and use `select()` for the `messages`/`sessions` join while keeping `MATCH`/`snippet()`/`bm25()` fragments raw. The two plain COUNTs convert to `func.count()`.

**Architecture finding**: `provider_config_repo.py` maintains a parallel sync SQLAlchemy engine stack (`_engine`/`_session`) alongside `Database` in `connection.py`, duplicating PRAGMA setup. Convert it to use `Database` (and its async ORM session).

## 5. Code smells

| Finding | Location | Recommendation |
|---|---|---|
| Placeholder regex duplicated (drifted) | `agents/validation.py`, `toolkit/tools/file_write.py`, `providers/parser.py` | One canonical constant + `detect_placeholders()`/`strip_placeholders()` in a shared module; note `toolkit/` importing from `agents/` is a layer inversion |
| provider_models upsert duplicated | `repositories.py:490`, `provider_config_repo.py:279` | Merge into one `upsert_provider_models()` |
| Identical `_sqlite_tables()` | `startup.py`, `migrations/runner.py` | Keep one, import from the other |
| Identical `_set_pragmas()` | `connection.py`, `provider_config_repo.py` | Resolved by §4 engine consolidation |
| ANSI-strip twice | `compaction.py`, `llm_provider.py` | `llm_provider` imports `strip_ansi` from `compaction` |
| 3 catalog-cache wrappers | `repositories.py`, `config/loader.py`, `llm_provider.py` | Keep `repositories.load_catalog()` only |
| Model-override in 2 layers | `prompt_executor.py`, `loop.py` | Pass through `process_prompt(model_override=...)`, remove direct provider mutation |
| Repeated summarization block ×4 | `loop.py:_process_prompt_impl` (486 lines) | Extract `_ensure_context_headroom(...)` helper |
| Large functions | `loop.py:148` (486), `prompt_executor.py:173` (364), `validation.py:158` (269), `handlers.py:353` (130), `context.py:189` (124) | Split / extract helpers |
| Circular deps (latent) | `repositories` ↔ `provider_config_repo`; `connection` → `startup` → `migrations.runner`; `handlers` ↔ `prompt_executor` | Break `repositories`↔`provider_config_repo` by extracting catalog loading; consolidate sqlite helpers |
| God objects | `handlers.py` (756), `repositories.py` (1528), `loop.py` (787), `prompt_executor.py` (537) | Split by domain |
| `make_event` name collision | `domain/events.py:77`, `api/protocol.py:84` | Rename one |
| `ToolCall` defined twice | `domain/message.py:12`, `providers/base.py:45` | Single shared model |
| `count_tokens` ×5 | base, llm_provider, token_counter, context, repo_map | Delegate to `TokenCounter` |
| `NO_CONTEXT_SENTINEL` duplicated | `sessions/history.py:10`, `sessions/memory.py:12` | Share (history.py being deleted) |

## 6. Performance issues

| Finding | Location | Recommendation |
|---|---|---|
| Sync DB calls in async `validate_provider` | `providers/validation.py` | `asyncio.to_thread` or async repo |
| Engine per call + dispose | `provider_config_repo.py` | Reuse module-level engine |
| Fresh event loop per summarization | `agents/summarizer.py:39` | `await` the coroutine directly |
| Dead `PromptExecutor` per connection | `websocket.py:208,232`, `handlers.py:74` | Remove the never-read `_executor`/`_shared_executor` |

## 7. Error handling

174 `except Exception` handlers remain; many are deliberate (documented in `pyproject.toml` ruff ignores `BLE001`/`S110`/`S112`). Per-site review needed to narrow exception types where feasible. Inline env defaults (§3.4) are a form of silent fallback — consolidate.

## 8. Stale test

`server/tests/test_e2e_integration.py` runs `uvicorn.run("transport.server:app", ...)` — `transport/server.py` was moved to `server/api/server.py:create_app`. Excluded from default suite via `addopts`, fails when run explicitly. Fix: `import server.api.server as api; uvicorn.run(api.create_app(), factory=True, ...)`.

## 9. Execution order

1. Dead code removal (modules → functions → API surface → frontend) — verify tests after each.
2. Constants application.
3. Raw SQL → ORM.
4. Code smells + structure.
5. Performance + error-handling cleanup.
6. Stale e2e test fix.

Every step preserves the 447 backend + 90 frontend tests green and the lint/format gates.
