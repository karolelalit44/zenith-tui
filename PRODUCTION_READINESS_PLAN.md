# Zenith – Production Readiness Plan

**Date**: 2026-07-23
**Based on**: Full audit of 54 Python files, ~90 TypeScript/TSX files, 2 reference repos

---

## Table of Contents

1. Current Architecture Assessment
2. Repository Cleanup – What to Remove
3. Modules to Refactor
4. Hardcoded Value Audit
5. Environment & Configuration
6. Error Handling Strategy
7. Database Architecture
8. Dockerization
9. Dependency Management
10. Implementation Roadmap
11. Critical Metrics

---

## 1. Current Architecture Assessment

### 1.1 Backend (zenith/)

**Structure**: ✅ Clean module layout with `core/`, `config/`, `db/`, `providers/`, `agent/`, `tools/`, `workspace/`, `session/`, `skills/`, `transport/`

**Test coverage**: ✅ 158 tests, all passing

| Module | Files | Tests | Coverage | Issues |
|--------|-------|-------|----------|--------|
| `config/` | 4 | 5 | Good | ENV_MAP hardcoded |
| `core/` | 4 | 12 | Good | None |
| `db/` | 3 | 7 | Good | No migrations strategy |
| `providers/` | 5 | 14 | Good | Hardcoded model lists |
| `agent/` | 4 | 10 | Good | No queue, no coordinator |
| `tools/` | 10 | 54 | Excellent | websearch.py is placeholder |
| `workspace/` | 4 | 27 | Good | lsp.py is placeholder |
| `session/` | 2 | 12 | Good | None |
| `skills/` | 1 | 0 | None | Only integration tests |
| `transport/` | 4 | 5 | Good | None |

### 1.2 Frontend (src/)

**Structure**: ✅ Clean component/service/hook separation

**Test coverage**: ❌ 7 test files, all testing mock systems

| Area | Files | Tests | Issues |
|------|-------|-------|--------|
| `services/scenario/` | 15 files | 1 test file | **Entirely mock — 10 fake scenario files** |
| `services/data/` | 9 files | 2 test files | In-memory storage, no backend connection |
| `services/providers/` | 9 files | 1 test file | Local-only, not connected to backend |
| `services/export/` | 1 file | 0 tests | Works only with mock events |
| `hooks/` | 6 files | 1 test file | Only useMock connected to reality |
| `screens/` | 7 screens | 0 tests | All drive mock system |
| `components/` | ~30 files | 3 test files | Mostly display, some with mock logic |

### 1.3 Reference Repos Insight

| Feature | aider | crush | We Have? |
|---------|-------|-------|----------|
| WebSocket backend | ❌ (CLI only) | ❌ (Go TUI) | ✅ |
| litellm provider | ✅ | ❌ (fantasy) | ✅ |
| File tools | ✅ | ✅ | ✅ |
| Bash tool | ✅ | ✅ | ✅ |
| Git integration | ✅ (gitpython) | ✅ (subprocess) | ✅ |
| Repo map | ✅ (tree-sitter) | ✅ (file tree) | ⚠️ file-tree only |
| Session persistence | ✅ (files) | ✅ (SQLite) | ✅ |
| Chat summarization | ✅ | ✅ | ✅ |
| Auto-commit | ✅ | ✅ | ✅ |
| Tool approval flow | ⚠️ (basic) | ✅ (3-tier) | ❌ **Missing** |
| LSP integration | ❌ | ✅ | ⚠️ **Placeholder** |
| Hook system | ❌ | ✅ | ❌ **Missing** |
| Context files | ✅ | ✅ | ❌ **Missing** |
| Per-session queue | ❌ | ✅ | ❌ **Missing** |
| Plan mode | ❌ | ✅ | ✅ |
| MCP support | ❌ | ✅ | ❌ **Missing** |
| Stream backend events | ❌ | ✅ (pub/sub) | ✅ |

---

## 2. Repository Cleanup – What to Remove

### 2.1 Files to Remove (Production)

| File | Reason | Size |
|------|--------|------|
| `src/services/scenario/scenarios/*.ts` (10 files) | 10 mock scenario generators, never used with real backend | ~1,200 lines |
| `src/services/scenario/providers/MockScenarioProvider.ts` | Active provider — prevents real backend connection | 16 lines |
| `src/services/scenario/delays.ts` | Mock timing engine for fake events | 36 lines |
| `src/services/scenario/engine.ts` | Mock execution engine for fake events | 46 lines |
| `src/services/scenario/templateLoader.ts` | Template system for mock scenarios | 31 lines |
| `src/services/data/ScenarioRepository.ts` | Keyword-based mock scenario selection | 81 lines |
| `src/services/data/options.json` | Hardcoded command definitions | 64 lines |
| `src/services/data/tokenEstimationService.ts` | Duplicates backend token counting | 74 lines |
| `src/services/data/jsonEventNormalizer.ts` | Only needed if events come from non-standard sources | 31 lines |
| `zenith/tools/websearch.py` | Placeholder — no real search integration | 43 lines |
| `zenith/workspace/lsp.py` | Placeholder — no real LSP connection | 28 lines |
| `reference_repo/aider/` | Reference only — not part of production code | ~10MB |
| `reference_repo/crush/` | Reference only — not part of production code | ~30MB |

**Total removable**: ~1,800 lines of code + ~40MB of reference repos

### 2.2 What to Keep (With Modifications)

| File | Modification Needed |
|------|-------------------|
| `src/services/scenario/index.ts` | Remove MockScenarioProvider export, add BackendScenarioProvider |
| `src/services/scenario/types.ts` | Keep — abstract interface, still valid |
| `src/services/data/SessionRepository.ts` | Rewrite to call backend instead of in-memory array |
| `src/services/data/StartupService.ts` | Add backend health check on startup |
| `src/services/data/userProfileService.ts` | Simplify — remove nested `provider`/`settings` duality |
| `src/services/export/markdownExport.ts` | Keep — can still generate markdown from real events |
| `src/services/data/CommandService.ts` | Keep — but commands should call backend |
| `zenith/config/loader.py` | Add startup validation |
| `zenith/providers/llm_provider.py` | Move model lists to config |
| `zenith/tools/websearch.py` | Integrate with real search API |

### 2.3 Orphaned/Unused Modules (Current Backend)

| Module | Status | Action |
|--------|--------|--------|
| `zenith/skills/` | Implemented but unused by agent loop | Wire into system prompt in `prompts.py` |
| `zenith/session/export.py` | Implemented but not exposed via WebSocket | Add `session.export` RPC method |
| `zenith/agent/recovery.py` | Implemented but not used by default | Make it the default wrapper in websocket handler |
| `zenith/workspace/tracker.py` | Implemented but not wired into agent loop | Hook into tool execution events |

---

## 3. Modules to Refactor

### 3.1 Priority 0 (Critical – Blocks Production)

| Module | Issue | Refactor |
|--------|-------|----------|
| `src/hooks/useScenario.ts` | Hardcodes `MockScenarioProvider` | Accept injected provider, default to `BackendScenarioProvider` |
| `src/services/providers/ProviderService.ts` | All local — no backend validation | Add `validate()` and `listModels()` via WebSocket RPC |
| `zenith/transport/websocket.py` | No per-session queue | Add `SessionQueue` with serialized processing per session |
| `zenith/agent/loop.py` | No coordinator wrapping | Wrap with `Coordinator` pattern from crush |

### 3.2 Priority 1 (High)

| Module | Issue | Refactor |
|--------|-------|----------|
| `zenith/config/loader.py` | Silent on missing config | Add `validate_config()` on startup, fail if required fields missing |
| `zenith/providers/llm_provider.py` | Hardcoded model lists | Move to `.zenith.json` provider config |
| `src/services/data/SessionRepository.ts` | In-memory only | Rewrite as backend RPC client |
| `src/services/data/StartupService.ts` | No backend check | Add WebSocket health check before marking ready |
| `src/services/data/userProfileService.ts` | Dual-state (flat + nested) | Flatten to single state structure |

### 3.3 Priority 2 (Medium)

| Module | Issue | Refactor |
|--------|-------|----------|
| `zenith/agent/prompts.py` | No context file loading | Add AGENTS.md, .cursorrules scanning |
| `zenith/tools/webfetch.py` | Hardcoded 50KB cap | Make configurable |
| `zenith/workspace/repo_map.py` | File tree only, no semantics | Add tree-sitter parsing |
| `zenith/core/errors.py` | `TransportError` code clash | Ensure unique error codes |
| `zenith/db/connection.py` | No migration support | Add migration runner |

---

## 4. Hardcoded Value Audit

### 4.1 Backend Hardcoded Values

| File | Line | Value | Should Be |
|------|------|-------|-----------|
| `config/settings.py` | 20 | `max_context_tokens=128000` | Configurable via `.zenith.json` |
| `config/providers.py` | 9 | `max_tokens=4096` | Per-provider config |
| `providers/base.py` | 6 | `temperature=0.7` | Per-request parameter |
| `providers/llm_provider.py` | 21 | `model="gpt-4"` | From config |
| `providers/llm_provider.py` | 97-104 | Model lists | From provider config or dynamic fetch |
| `main.py` | 12-13 | `host="localhost"`, `port=8765` | From config + env override |
| `tools/webfetch.py` | 43 | `content[:50000]` | Configurable cap |
| `agent/loop.py` | 26 | `MAX_TOOL_OUTPUT=10000` | Configurable |
| `config/loader.py` | 11-20 | `ENV_MAP` provider mapping | Extensible mapping |
| `tools/file_read.py` | 33 | `default: 2000` | Configurable limit |
| `transport/server.py` | 81 | `code=1011`, `reason="Server not ready"` | Configurable |
| `workspace/tracker.py` | 21 | `content[:10000]` | Configurable cap |

### 4.2 Frontend Hardcoded Values

| File | Line | Value | Should Be |
|------|------|-------|-----------|
| `services/providers/types.ts` | 1 | `ProviderId = 'openrouter'\|'openai'\|...` | From backend config |
| `services/providers/ProviderRepository.ts` | 10-17 | `PROVIDER_CONFIG_MAP` | From backend |
| `services/data/options.json` | 1-64 | 10 commands | From backend configuration |
| `services/data/SessionRepository.ts` | 6 | Initial session | From backend |
| `services/data/userProfileService.ts` | 43-67 | `DEFAULT_PROFILE` | From backend bootstrap |
| `services/export/markdownExport.ts` | 272 | `process.cwd()` | Configurable |
| `hooks/useConversation.ts` | 67-71 | Hardcoded abort event | From backend event |
| `screens/Help/HelpModal.tsx` | - | Hardcoded help content | From backend or config |
| `screens/ModeSelect/data/modeData.ts` | - | Hardcoded mode descriptions | From backend |
| `components/Input/CommandInput.tsx` | 36 | `placeholder="Ask anything..."` | Configurable |

---

## 5. Environment & Configuration

### 5.1 Create `.env.example`

```
# ── Backend ──────────────────────────────────────────
ZENITH_ACTIVE_PROVIDER=openai
ZENITH_DB_PATH=./data/zenith.db
ZENITH_LOG_LEVEL=info
ZENITH_WORKSPACE_ROOT=.

# ── Provider API Keys ────────────────────────────────
ZENITH_OPENAI_API_KEY=sk-...
ZENITH_ANTHROPIC_API_KEY=sk-ant-...
ZENITH_GOOGLE_API_KEY=...
ZENITH_GROQ_API_KEY=gsk_...
ZENITH_OPENROUTER_API_KEY=...

# ── Provider URLs (custom/Ollama) ────────────────────
ZENITH_CUSTOM_BASE_URL=http://localhost:11434/v1

# ── Search (optional) ────────────────────────────────
ZENITH_SEARCH_API_KEY=...
ZENITH_SEARCH_ENGINE=google

# ── Server ───────────────────────────────────────────
ZENITH_HOST=localhost
ZENITH_PORT=8765

# ── Frontend ─────────────────────────────────────────
ZENITH_BACKEND_URL=ws://localhost:8765/ws
```

### 5.2 Add Startup Validation

```python
# In config/loader.py or a new validation module
REQUIRED_FOR_PROVIDER = {
    "openai": ["api_key"],
    "anthropic": ["api_key"],
    "google": ["api_key"],
    "groq": ["api_key"],
    "openrouter": ["api_key"],
    "custom": ["base_url"],
}

def validate_config(settings: AppSettings) -> list[str]:
    errors = []
    active = settings.get_active_provider_config()
    if active is None:
        errors.append(f"Active provider '{settings.active_provider}' not configured")
    else:
        for field in REQUIRED_FOR_PROVIDER.get(settings.active_provider, []):
            if not getattr(active, field, None):
                errors.append(f"Missing {field} for provider '{settings.active_provider}'")
    return errors
```

---

## 6. Error Handling Strategy

### 6.1 Current State

- Error hierarchy: ✅ 8 exception types with codes and recoverable flags
- Structured errors: ✅ JSON-RPC error responses with codes
- User-friendly messages: ⚠️ Inconsistent in some places
- Silent failures: ❌ Several bare `except` clauses in frontend

### 6.2 Issues Found

| Location | Issue | Fix |
|----------|-------|-----|
| `src/services/data/userProfileService.ts:110` | `catch (_err) {}` — silences all errors | Log the error, surface to user |
| `src/services/data/userProfileService.ts:132-135` | `catch (_err) {}` — ignores write errors | Log + surface |
| `src/services/data/userProfileService.ts:177-179` | `catch (_err) {}` — ignores write errors | Log + surface |
| `src/services/providers/ProviderService.ts:98-100` | `catch (_err) {}` — ignores listener errors | Log warning |
| `zenith/db/connection.py:26` | `assert` — crashes on missing connection | Raise proper `DatabaseError` |
| `zenith/db/connection.py:39-41` | `assert` — crashes on missing connection | Raise proper `DatabaseError` |

### 6.3 Error Codes Registry

| Code | Exception | When | Recoverable |
|------|-----------|------|-------------|
| `CONFIG_ERROR` | `ConfigError` | Missing/bad config | No |
| `PROVIDER_ERROR` | `ProviderError` | Provider call failed | Yes |
| `RATE_LIMIT` | `RateLimitError` | Provider rate limited | Yes |
| `AUTH_ERROR` | `AuthenticationError` | Bad API key | No |
| `TIMEOUT` | `TimeoutError` | Request timed out | Yes |
| `TOOL_ERROR` | `ToolError` | Tool execution failed | Yes |
| `SESSION_ERROR` | `SessionError` | Session not found | No |
| `TRANSPORT_ERROR` | `TransportError` | WebSocket issue | Yes |
| `PERMISSION_DENIED` | `PermissionDenied` | Tool not allowed | No |
| `MAX_ITERATIONS` | `MaxIterationsError` | Agent loop limit | No |

---

## 7. Database Architecture

### 7.1 Current State

- SQLite via aiosqlite ✅
- WAL mode ✅
- Foreign keys ✅
- Schema auto-creation on connect ✅

### 7.2 Missing

| Feature | Missing | Action |
|---------|---------|--------|
| Schema migrations | ✅ | Add migration runner (sequentially numbered SQL files) |
| Connection pooling | ⚠️ | Single connection is fine for single-user |
| Error recovery | ❌ | Add retry + graceful degradation |
| Index strategy | ⚠️ | Current indexes are basic — review query patterns |
| Data directory | ❌ | Default `zenith.db` in CWD — use `./data/` instead |

### 7.3 Migration Strategy

```
zenith/db/migrations/
├── 001_initial.sql      # Current schema
├── 002_add_todos.sql    # Session todo support
├── 003_add_cost.sql     # Cost tracking
└── _runner.py           # Applies pending migrations
```

```python
class MigrationRunner:
    def __init__(self, db: Database):
        self.db = db
        self.migrations_dir = Path(__file__).parent

    async def run(self):
        await self.db.execute("CREATE TABLE IF NOT EXISTS _migrations (id INTEGER PRIMARY KEY, name TEXT)")
        applied = {row["name"] for row in await self.db.fetch_all("SELECT name FROM _migrations")}
        for f in sorted(self.migrations_dir.glob("*.sql")):
            if f.name not in applied:
                sql = f.read_text()
                await self.db.execute(sql)
                await self.db.execute("INSERT INTO _migrations (name) VALUES (?)", (f.name,))
        await self.db.commit()
```

---

## 8. Dockerization

### 8.1 Backend Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install -e ".[llm,git]"

COPY zenith/ zenith/
COPY .zenith.json .zenith.json 2>/dev/null || true

EXPOSE 8765

CMD ["zenith", "serve", "--host", "0.0.0.0", "--port", "8765"]
```

### 8.2 Frontend Dockerfile

```dockerfile
FROM node:20-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY tsconfig.json ./
COPY src/ src/
RUN npm run build

FROM node:20-alpine

WORKDIR /app
COPY --from=builder /app/dist/ dist/
COPY package.json ./

CMD ["node", "dist/index.js"]
```

### 8.3 Docker Compose

```yaml
version: "3.8"

services:
  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    ports:
      - "${ZENITH_PORT:-8765}:8765"
    environment:
      - ZENITH_ACTIVE_PROVIDER=${ZENITH_ACTIVE_PROVIDER:-}
      - ZENITH_OPENAI_API_KEY=${ZENITH_OPENAI_API_KEY:-}
      - ZENITH_DB_PATH=/data/zenith.db
    volumes:
      - ./data:/data
      - .:/workspace
    working_dir: /workspace

  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    environment:
      - ZENITH_BACKEND_URL=ws://backend:8765/ws
    depends_on:
      - backend
```

---

## 9. Dependency Management

### 9.1 Backend (pyproject.toml)

**Current**: 8 dependencies + 3 optional extras

**Issues**:
- No version pins for sub-dependencies
- `[dev]` extras install pytest-cov but no coverage config in pyproject.toml

**Fix**: Add `requirements/` directory:

```
requirements/
├── base.txt          # Runtime deps (pinned)
├── llm.txt           # LLM extra (pinned)
├── git.txt           # Git extra (pinned)
└── dev.txt           # Dev extra (pinned)
```

### 9.2 Frontend (package.json)

**Current**: 5 dependencies + 8 devDependencies

**Issues**:
- `cli-highlight` (2.1.11) — only used in one component, could be removed
- `ts-node` (10.9.2) — not used if tsx is the runner

**Potential removals**:
- `cli-highlight` → `npm uninstall`
- `ts-node` → `npm uninstall`

---

## 10. Implementation Roadmap

### Phase 6 — Frontend Bridge (CRITICAL)

| # | Task | Files | Effort |
|---|------|-------|--------|
| 6.1 | Create `BackendScenarioProvider` | New: `src/services/scenario/providers/BackendScenarioProvider.ts` | 4h |
| 6.2 | Create WebSocket client service | New: `src/services/backend/WebSocketClient.ts` | 6h |
| 6.3 | Event mapper (backend → frontend) | New: `src/services/backend/EventMapper.ts` | 4h |
| 6.4 | Update `useScenario` to use backend | Modify: `src/hooks/useScenario.ts` | 2h |
| 6.5 | Remove mock scenario system | Delete: 10 mock files, delays.ts, engine.ts, templateLoader.ts, ScenarioRepository.ts | 1h |
| 6.6 | Rewrite SessionRepository (backend RPC) | Rewrite: `src/services/data/SessionRepository.ts` | 2h |
| 6.7 | Add `session.export` RPC to backend | Modify: `zenith/transport/websocket.py` + `zenith/session/export.py` | 2h |
| 6.8 | Wire recovery.py into websocket handler | Modify: `zenith/transport/websocket.py` | 1h |
| 6.9 | Wire skills loader into agent prompts | Modify: `zenith/agent/prompts.py` | 1h |
| 6.10 | Remove websearch.py + lsp.py placeholders | Delete: `websearch.py`, `lsp.py` | 0.5h |

### Phase 7 — Production Backend

| # | Task | Files | Effort |
|---|------|-------|--------|
| 7.1 | Add per-session prompt queue | New: `zenith/agent/queue.py` | 4h |
| 7.2 | Add Coordinator pattern | New: `zenith/agent/coordinator.py` | 6h |
| 7.3 | Add startup config validation | Modify: `zenith/config/loader.py` | 2h |
| 7.4 | Create `.env.example` | New: `.env.example` | 1h |
| 7.5 | Add migration runner | New: `zenith/db/migrations/_runner.py`, rename `schema.sql` to `001_initial.sql` | 3h |
| 7.6 | Make hardcoded values configurable | Modify: `llm_provider.py`, `webfetch.py`, `file_read.py`, `loop.py` | 4h |
| 7.7 | Add context file loading (AGENTS.md etc.) | Modify: `zenith/agent/prompts.py` | 3h |
| 7.8 | Add tool approval protocol | New: `zenith/tools/approval.py`, modify `websocket.py` | 6h |
| 7.9 | Add session todo support | Modify: `session.py`, `db/schema.sql`, `repository.py` | 3h |
| 7.10 | Add cost tracking | Modify: `session.py`, `db/migrations/`, `llm_provider.py` | 3h |
| 7.11 | Dockerfiles + compose | New: `Dockerfile.backend`, `Dockerfile.frontend`, `docker-compose.yml` | 3h |
| 7.12 | Clean up frontend dead code | Delete: mock files, unused configs, reference_repo/ | 2h |

### Phase 8 — Intelligence

| # | Task | Files | Effort |
|---|------|-------|--------|
| 8.1 | Add tree-sitter repo map | Rewrite: `zenith/workspace/repo_map.py` | 8h |
| 8.2 | Add post-edit lint hook | New: `zenith/tools/lint_hook.py` | 4h |
| 8.3 | Add reflection loop | Modify: `zenith/agent/loop.py` | 4h |
| 8.4 | Wire file tracker into agent loop | Modify: `zenith/agent/loop.py` | 2h |

### Phase 9 — Extensibility

| # | Task | Files | Effort |
|---|------|-------|--------|
| 9.1 | Add hook system (shell commands on events) | New: `zenith/hooks/` | 8h |
| 9.2 | Add LSP integration | Rewrite: `zenith/workspace/lsp.py` | 12h |
| 9.3 | Add websearch integration | Rewrite: `zenith/tools/websearch.py` | 4h |

---

## 11. Critical Metrics

### Code Health

| Metric | Current | Target |
|--------|---------|--------|
| Backend tests | 158 | 200+ |
| Frontend tests | 7 | 30+ |
| Backend test pass | 100% | 100% |
| Frontend test pass | ❌ unknown | 100% |
| Hardcoded values (backend) | 15 | 3 (bootstrap-only) |
| Hardcoded values (frontend) | 14 | 0 |
| Mock/placeholder files | 12 | 0 |
| `except: pass` blocks | 4 | 0 |
| Placeholder tools | 2 | 0 |
| Docker support | ❌ | ✅ |

### Performance (Targets)

| Metric | Target |
|--------|--------|
| Backend startup time | <2s |
| First LLM token | <3s |
| Tool execution latency | <500ms |
| SQLite query latency | <10ms |
| WebSocket reconnect | <1s |
| Frontend startup | <1s |
| Event render latency | <100ms |

---

## Quick Win Checklist (Week 1)

- [ ] Remove `reference_repo/` directory (moves to backup)
- [ ] Remove 10 mock scenario files
- [ ] Remove `delays.ts`, `engine.ts`, `templateLoader.ts`, `ScenarioRepository.ts`
- [ ] Remove `websearch.py`, `lsp.py` placeholders
- [ ] Create `BackendScenarioProvider.ts`
- [ ] Create `WebSocketClient.ts`
- [ ] Wire `useScenario.ts` to backend
- [ ] Add startup validation to config loader
- [ ] Create `.env.example`
- [ ] Add migration runner
- [ ] Wire recovery.py into websocket handler
- [ ] Wire skills loader into prompts
- [ ] Add `session.export` RPC method
- [ ] Run `pytest tests/` — confirm 158 still pass
- [ ] Remove `ts-node`, `cli-highlight` from frontend deps
