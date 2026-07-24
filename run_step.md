# Running Zenith — Frontend & Backend

Zenith is a monorepo with two parts:

| Component | Stack | Default Port |
|-----------|-------|-------------|
| **Backend** | Python 3.11+ · FastAPI · WebSocket · SQLite | `8765` |
| **Frontend** | TypeScript · React (Ink TUI) | connects via WebSocket |

Both must run simultaneously — the frontend connects to the backend over WebSocket at `ws://localhost:8765/ws` and calls REST endpoints at `http://localhost:8765/` for startup validation and provider setup.

---

## Prerequisites

| Tool | Minimum Version | Check |
|------|----------------|-------|
| Python | 3.11 | `python --version` |
| Node.js | 18+ | `node --version` |
| npm | 9+ | `npm --version` |
| Git | any | `git --version` |

---

## 1 — Backend

### Windows (PowerShell)

```powershell
# from project root
cd zenith-frontend-tui

# create virtual environment (first time only)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# install in editable mode with all extras
pip install -e ".[llm,git,dev]"
```

### macOS / Linux

```bash
cd zenith-frontend-tui

python3 -m venv .venv
source .venv/bin/activate

pip install -e ".[llm,git,dev]"
```

### Configure API Keys

Create a `.zenith.json` in the project root **or** set environment variables.

Each provider needs at least an `api_key`. You can set these up front via `.zenith.json` or environment variables, **or** configure them interactively through the frontend's setup wizard on first launch.

**Option A — `.zenith.json`**

```json
{
  "active_provider": "openai",
  "providers": {
    "openai": { "api_key": "sk-..." },
    "anthropic": { "api_key": "sk-ant-..." }
  }
}
```

**Option B — Environment Variables** (works on all platforms)

```bash
# set the provider you want to use
export ZENITH_ACTIVE_PROVIDER=openai

# set the API key for that provider
export ZENITH_OPENAI_API_KEY=sk-...

# other supported env vars:
#   ZENITH_ANTHROPIC_API_KEY
#   ZENITH_GOOGLE_API_KEY
#   ZENITH_GROQ_API_KEY
#   ZENITH_OPENROUTER_API_KEY
#   ZENITH_CUSTOM_BASE_URL   (for Ollama / local providers)
#   ZENITH_DB_PATH            (override SQLite location)
```

### Start the Backend

```bash
# with virtual environment active
zenith serve --host localhost --port 8765
```

Or run directly:

```bash
python -m zenith serve --port 8765
```

Verify it's running:

```bash
# health check
curl http://localhost:8765/health
# → {"status":"ok","handler":true,"version":"0.1.0"}

# startup validation (used by frontend on launch)
curl http://localhost:8765/startup/validate
# → {"status":"ready"|"configuration_required","missing":[...],...}
```

---

## 2 — Frontend

Open a **second terminal** (keep the backend running in the first).

### Windows (PowerShell)

```powershell
cd zenith-frontend-tui

npm install
npm start
```

### macOS / Linux

```bash
cd zenith-frontend-tui

npm install
npm start
```

`npm start` runs `tsx src/index.tsx` which launches the Ink TUI directly — no build step required for development.

**Startup validation**: On launch, the frontend calls `GET /startup/validate` on the backend. If configuration is missing (no provider, no API key, etc.), it shows a **Setup Wizard** guiding you through provider selection, API key entry, and model selection. The main Welcome screen only appears after all prerequisites are satisfied.

### Build for Production (optional)

```bash
npm run build      # compiles to dist/
npm run preview    # runs the compiled output
```

---

## 3 — Running Both Together

You need two terminals open side by side:

```
Terminal 1 (Backend)                  Terminal 2 (Frontend)
─────────────────────                 ─────────────────────
cd zenith-frontend-tui                cd zenith-frontend-tui
.\.venv\Scripts\Activate.ps1         npm start
zenith serve --port 8765
```

```
Terminal 1 (Backend)                  Terminal 2 (Frontend)
─────────────────────                 ─────────────────────
cd zenith-frontend-tui                cd zenith-frontend-tui
source .venv/bin/activate             npm start
zenith serve --port 8765
```

---

## 4 — Useful Commands

### Backend

| Command | What it does |
|---------|-------------|
| `zenith serve` | Start the WebSocket server |
| `zenith serve --port 9000` | Start on a custom port |
| `zenith --help` | Show CLI help |
| `pytest tests/` | Run all 154 backend tests |
| `pytest tests/ -v` | Verbose test output |

### Frontend

| Command | What it does |
|---------|-------------|
| `npm start` | Run the TUI in dev mode |
| `npm run build` | Compile TypeScript |
| `npm run preview` | Run compiled build |
| `npm test` | Run all 25 Vitest tests |
| `npm run lint` | Lint with Biome |
| `npm run lint:fix` | Auto-fix lint issues |
| `npm run typecheck` | Type-check without emitting |

---

## 5 — Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError: No module named 'zenith'` | Make sure `.venv` is activated and you ran `pip install -e ".[llm,git,dev]"` |
| Backend starts but `curl /health` fails | Check the port isn't blocked; try `--port 9000` |
| Frontend says "Connection refused" | Backend must be running first on `localhost:8765` |
| Frontend shows Setup Wizard on every launch | Configure a provider via the wizard or manually create `.zenith.json` |
| Frontend shows "Cannot connect to backend" in error box | Backend WebSocket at `ws://localhost:8765/ws` is not reachable — start it with `zenith serve` |
| `litellm` import error | Install with `pip install -e ".[llm]"` |
| `gitpython` import error | Install with `pip install -e ".[git]"` |
| `tsx` not found | Run `npm install` in the project root |
| Port already in use | Use `--port <other>` or kill the process using that port |


cmd /c "zenith serve --host localhost --port 8765 2>&1" | Tee-Object -FilePath .\zenith_run.log


 Stop-Process -Name python -Force