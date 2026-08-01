# Zenith — AI Coding Assistant

A terminal-native coding assistant. A **Python server** (`server/`) runs the agent,
tool, and persistence stack; a **TypeScript TUI** (`tui/`) renders it in the terminal
over a JSON-RPC WebSocket connection.

```
┌──────────────────────────┐        WebSocket / JSON-RPC        ┌──────────────────────────┐
│  tui/  (TypeScript/Ink)  │  ───────────────────────────────►  │  server/  (Python)      │
│  terminal user interface │                                   │  agent + tool engine    │
└──────────────────────────┘                                   └──────────────────────────┘
```

## Repository layout

| Path          | Role                                                        |
| ------------- | ----------------------------------------------------------- |
| `server/`        | Backend: agent loop, tools, providers, persistence, RPC API |
| `server/tests/`  | Python test suite (pytest)                                 |
| `tui/`           | Frontend: Ink/React terminal UI (source + tests)           |
| `data/`          | Runtime SQLite database and exports                        |
| `ref_repo/`      | Reference repositories (not part of the codebase)          |
| (root)           | pnpm workspace + Turbo: `package.json`, `pnpm-workspace.yaml`, `turbo.json`, `dev.mjs` |

## Backend (`server/`)

### Entrypoints

| File                        | Role                                                              |
| --------------------------- | ----------------------------------------------------------------- |
| `server/main.py`            | Click CLI: `python -m server.main serve` (default port 8765)      |
| `server/__main__.py`        | Allows `python -m server` to delegate to the CLI                  |
| `server/app.py`             | `AppContainer` — dependency-injection composition root            |
| `server/api/server.py`      | FastAPI app factory (`create_app`) + HTTP `/health`, `/status`    |

### Package map

| Package        | Contents                                                                |
| -------------- | ----------------------------------------------------------------------- |
| `api/`         | **Transport/RPC layer.** `handlers.py` (RPC dispatch), `websocket.py` (`ZenithHandler`, `ConnectionManager`), `protocol.py` (JSON-RPC types), `server.py`, `startup.py`, `shutdown.py`, `schemas.py` |
| `domain/`      | **Core domain types.** `domain.py` (enums), `errors.py`, `events.py` (`EventBus`), `hooks.py` (`HookRunner`), `message.py`, `session.py` (session + state machine) |
| `persistence/` | **SQLite persistence.** `connection.py` (`Database`), `repositories.py` (session/message/provider/token/checkpoint repos), `search.py` (FTS5), `migration.py`, `blob_store.py`, `schema.sql`, `migrations/` |
| `sessions/`    | **Session services.** `service.py` (`SessionService`), `history.py`, `memory.py`, `export.py` |
| `agents/`      | **Agent engine.** `loop.py` (`AgentLoop`), `context.py`, `compaction.py`, `runtime.py`, `coordinator.py`, `recovery.py`, `sub_agent.py`, `llm_stream.py`, `prompts.py`, `prompt_executor.py`, `validation.py`, `loop_detection.py`, `templates.py` |
| `toolkit/`     | **Tool engine.** `registry.py`, `base.py`, `executor.py`, `command_safety.py`, `auto_lint.py`, `param_normalizer.py`, `path_validator.py`, `tools/` (built-in tool implementations), `middleware/` (safety, permission, hooks, validation, logging) |
| `providers/`   | **LLM providers.** `base.py`, `registry.py`, `llm_provider.py`, `parser.py`, `responder.py`, `retry.py`, `token_counter.py`, `provider_catalog.json` |
| `permissions/` | **Permission service.** `service.py` — tool risk decisions + persisted grants |
| `workspace/`   | **Workspace services.** `git.py`, `repo_map.py`, `tracker.py`, `service.py`, `context.py` |
| `skills/`      | `loader.py` — loads structured skill definitions for the agent   |
| `lsp/`         | `client.py`, `manager.py` — Language Server Protocol integration |
| `mcp/`         | `client.py`, `manager.py` — Model Context Protocol servers       |
| `config/`      | `settings.py`, `loader.py`, `env.py`, `providers.py`, `provider_catalog.json` |

### How the pieces fit

1. `server/main.py serve` builds the FastAPI app via `api/server.py:create_app()`.
2. `AppContainer` (`app.py`) wires providers, the tool registry, session services,
   permission service, and repositories together.
3. `api/websocket.py` `ZenithHandler` accepts JSON-RPC requests, dispatches via
   `api/handlers.py:MethodHandlers` to `sessions/`, `agents/`, or `toolkit/`.
4. `agents/loop.py` runs the agent loop, using `toolkit/` tools gated by
   `toolkit/middleware/` (safety, permission, config-driven hooks) and streamed to
   the TUI as domain events.
5. All state persists through `persistence/` into SQLite (`data/zenith.db`).

## Frontend (`tui/`)

### Entrypoints

| File                   | Role                                          |
| ---------------------- | --------------------------------------------- |
| `tui/src/index.tsx`    | Process entrypoint — renders `<App/>` via Ink |
| `tui/src/App.tsx`      | Root component; wires state, hooks, routing   |
| `tui/tests/`           | Vitest suite + `setup.ts`                     |

### Package map

| Path                     | Contents                                                        |
| ------------------------ | --------------------------------------------------------------- |
| `src/components/`        | Presentational components: `display/` (scenario renderer, status bar, token meter), `input/` (command input, autocomplete, file picker), `ui/` (rounded box, modal footer, error boundary), `layout/` (welcome view) |
| `src/screens/`           | Overlay screens: Context, Help, ModeSelect, Settings, SetupWizard, Usage, Welcome |
| `src/hooks/`             | Behavior hooks: `useConversation`, `useScenario`, `useProvider`, `useOverlayManager`, `useAutocomplete`, `useNotifications`, `useTickAnimation`, `useTerminalKeyboard` |
| `src/services/`          | Domain services: `transport/` (WebSocket client + scenario provider), `api/` (backend data access), `providers/` (model/provider registry), `export/` (markdown export), plus `git.ts`, `fileExplorer.ts`, `eventBus.ts`, `perf.ts` |
| `src/context/`           | `AppContext`, `useStore` — shared app state                      |
| `src/theme/`             | Ink theming (`theme.ts`, `ThemeContext.tsx`, `types.ts`)         |
| `src/config/` `src/constants/` `src/types/` `src/utils/` | Env config, constants, shared types, utilities |

### Flow

The TUI connects to the server over WebSocket (`services/transport/WebSocketClient.ts`),
dispatches user prompts through `hooks/useScenario` → `services/transport/BackendScenarioProvider.ts`,
and renders streamed events via `components/display/Scenario/ScenarioRenderer.tsx`.

## Running & verification

The repo is a pnpm workspace managed with Turborepo. One command runs the whole app:

```bash
pnpm install        # first time (or after dependency changes)

pnpm dev            # backend (background, logs to ./zenith_server.log) + TUI
pnpm dev:server     # backend only (foreground, :8765)
pnpm dev:tui        # TUI only (needs a running backend)
```

Individual packages can be targeted with `pnpm --filter <tui|server> <script>`.

Checks (all run across both packages via turbo):

```bash
pnpm lint          # ruff (server) + biome (tui)
pnpm typecheck     # tsc --noEmit (tui)
pnpm test          # pytest (server, 349) + vitest (tui, 70)
pnpm build         # tsc emit to tui/dist
```
