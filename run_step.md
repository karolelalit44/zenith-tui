# Zenith — Run Steps

AI coding assistant. Python backend + TypeScript/Ink TUI frontend, connected over WebSocket.

---

## Stack

| Layer | Tech | Port |
|-------|------|------|
| Backend | Python 3.11+ / FastAPI / WebSocket / SQLite | `8765` |
| Frontend | TypeScript / React (Ink TUI) | connects via WS |

Communication: JSON-RPC over `ws://localhost:8765/ws`.

---

## Prerequisites

Python 3.11+, Node.js 18+, pnpm, Git.

---

## Setup

### Backend

```powershell
cd zenith-frontend-tui
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[llm,git,dev]"
```

```bash
cd zenith-frontend-tui
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[llm,git,dev]"
```

### Frontend

```bash
cd zenith-frontend-tui
pnpm install
```

---

## Configure Provider

Set environment variables. No config files needed.

```bash
ZENITH_ACTIVE_PROVIDER=nvidia
ZENITH_NVIDIA_API_KEY=nvapi-...
```

Supported: `nvidia`, `openai`, `anthropic`, `google`, `groq`, `openrouter`, `ollama`, `custom`.

---

## Dev Server

Run the whole app with one command:

```bash
pnpm dev
```

- Starts the backend in the background (logs to `zenith_server.log`), then launches the TUI.
- Backend: `http://localhost:8765` — health check: `/health`.
- Quit the TUI (or press Ctrl+C) to stop the backend too.

Or run each part individually:

```bash
pnpm dev:server   # backend only (foreground, :8765)
pnpm dev:tui      # TUI only (backend must already be running)
```

---

## Backend Env Vars

| Variable | Purpose | Default |
|----------|---------|---------|
| `ZENITH_ACTIVE_PROVIDER` | Provider name | — |
| `ZENITH_DB_PATH` | SQLite database path | `zenith.db` |
| `ZENITH_LOG_LEVEL` | Logging level | `info` |
| `ZENITH_MAX_CONTEXT_TOKENS` | Max context window | `128000` |
| `ZENITH_SUMMARY_THRESHOLD` | Auto-summarize threshold | `0.8` |
| `ZENITH_MAX_ITERATIONS` | Agent loop limit | `25` |
| `ZENITH_MAX_TOOL_OUTPUT` | Tool output char limit | `10000` |
| `ZENITH_BASH_TIMEOUT` | Bash command timeout (s) | `300` |
| `ZENITH_MAX_RETRIES` | Max retry attempts | `3` |
| `ZENITH_STREAM_MAX_RETRIES` | Stream retry limit | `2` |
| `ZENITH_RETRY_BASE_DELAY` | Retry backoff base (s) | `1.0` |
| `ZENITH_RETRY_MAX_DELAY` | Retry backoff max (s) | `60.0` |
| `ZENITH_WEBFETCH_TIMEOUT` | Web fetch timeout (s) | `300` |
| `ZENITH_WEBFETCH_MAX_BYTES` | Web fetch size limit | `50000` |
| `ZENITH_GIT_TIMEOUT` | Git operation timeout (s) | `300` |

---

## Event Pipeline

19 event kinds: `thinking`, `file_create`, `file_edit`, `file_delete`, `terminal`, `error`, `warning`, `retry`, `success`, `summary`, `message`, `progress`, `waiting`, `test_execution`, `build_step`, `deployment`, `analysis`, `planner_action_panel`, `mode_mismatch`.

Flow: `AgentLoop → WebSocket → EventMapper → componentRegistry → UI`

---

## Architecture

```
App.tsx
├── WelcomeScreen
├── Turn[] (PromptHeader + ScenarioRenderer)
├── Running Scenario (PromptHeader + ScenarioRenderer)
├── CommandInput (MultiLineTextInput)
├── SessionStatusBar
└── Overlays (mode, help, settings, context, add-dir, provider)
```

No virtual scroll, no permission prompts, 9 themes.

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Shift+T` | Toggle thinking collapsed |
| `Shift+M` | Open mode selector |
| `Shift+Enter` | Insert newline in input |
| `Escape` | Abort running scenario / close overlay |
| `/` | Open slash command palette |
| `@` | Open file picker |
| `Ctrl+S` | Export last plan to markdown |

---

## Tests

```bash
pnpm test          # pytest (server/tests) + vitest (tui/tests)
pnpm lint          # ruff (server) + biome (tui)
pnpm typecheck     # tsc --noEmit (tui)
pnpm build         # tsc emit to tui/dist
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError: zenith` | Activate venv + `pip install -e ".[llm,git,dev]"` |
| `curl /health` fails | Port blocked? Try `--port 9000` |
| Frontend "Connection refused" | Start backend first on `localhost:8765` |
| Frontend shows Setup Wizard | Configure `ZENITH_ACTIVE_PROVIDER` + API key env vars |
| `tsx` not found | Run `pnpm install` |
| Port in use | `--port <other>` or kill the occupying process |
