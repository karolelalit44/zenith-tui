# Zenith End-to-End Testing Guide

> **Version:** 0.1.0  
> **Date:** July 2026  
> **Scope:** Full-stack manual verification of Zenith AI Coding Assistant

---

## Table of Contents

1. [Frontend Architecture Summary](#1-frontend-architecture-summary)
2. [Backend Architecture Summary](#2-backend-architecture-summary)
3. [End-to-End Request Lifecycle](#3-end-to-end-request-lifecycle)
4. [Startup Verification Guide](#4-startup-verification-guide)
5. [Provider Setup Guide](#5-provider-setup-guide)
6. [OpenRouter Integration Review](#6-openrouter-integration-review)
7. [OpenRouter API/SDK Compliance Report](#7-openrouter-apisdk-compliance-report)
8. [Manual Testing Scenarios](#8-manual-testing-scenarios)
9. [Example Prompts by Feature](#9-example-prompts-by-feature)
10. [Feature Verification Checklist](#10-feature-verification-checklist)
11. [Production Readiness Checklist](#11-production-readiness-checklist)
12. [Gap Analysis & Prioritized Recommendations](#12-gap-analysis--prioritized-recommendations)

---

## 1. Frontend Architecture Summary

### Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Runtime | Node.js 18+ / `tsx` | TypeScript execution |
| UI Framework | React 18 + Ink 5 | Terminal rendering (no DOM) |
| Rendering | `ink-testing-library` | Test harness |
| State | React hooks (useState, useCallback, useRef, useEffect) | Local component state |
| Events | `useInput` from Ink | Keyboard input handling |
| HTTP | `fetch` with `AbortSignal.timeout` | REST calls to backend (`/startup/validate`) |
| WebSocket | Native `WebSocket` + JSON-RPC 2.0 | Real-time prompt/event stream |
| Type system | TypeScript strict | All files typed |

### Component Tree

```
src/index.tsx
  ThemeProvider
    ErrorBoundary
      App
        ├── (phase=loading)  → "Initializing Zenith..."
        ├── (phase=setup|error) → SetupWizard
        │     ├── Step: intro → select_provider → enter_key → select_model → validating → done
        │     └── Calls startupService.validateProvider() + saveProviderConfig()
        └── (phase=ready) → Main App
              ├── WelcomeScreen (always visible at top)
              │     ├── Logo (ASCII art)
              │     ├── System Status (provider, model, workspace)
              │     ├── Greeting (time-of-day)
              │     └── Recent Sessions list
              ├── Conversation turns (scrollable via PgUp/PgDn)
              │     ├── PromptHeader (prompt, mode, timestamp)
              │     └── ScenarioRenderer (events for that turn)
              ├── Active scenario (isRunning)
              │     ├── PromptHeader
              │     └── ScenarioRenderer (live events)
              ├── CommandInput (when idle, no overlays)
              │     ├── Keyboard: type → Enter to submit
              │     ├── `/` → autocomplete dropdown
              │     ├── `@` → file picker modal
              │     └── ↑/↓ → history navigation
              ├── SessionStatusBar (mode, tokens, running state)
              └── Overlays (mutually exclusive, Esc to close)
                    ├── mode → ModeSelectScreen
                    ├── help → HelpModal
                    ├── settings → SettingsModal (theme + preferences)
                    ├── context → ContextModal
                    ├── add-dir → AddDirModal
                    └── provider → ProvidersScreen
                          ├── ProviderList (navigate, activate)
                          └── GenericProviderConfigForm (edit API key, model, etc.)
```

### Key Hooks

| Hook | State | Purpose |
|------|-------|---------|
| `useScenario` | `events`, `isRunning` | Connects via WebSocket, sends prompts, receives events |
| `useConversation` | `turns`, `activeTurn`, `totalTokens` | Manages conversation turns, token estimation |
| `useOverlayManager` | `selectedMode`, `overlay`, `isOverlayOpen` | Mode switching, overlay routing |
| `useAutocomplete` | `input`, `showAutocomplete`, `showFilePicker` | Input value, `/` commands, `@` file picker |
| `useTerminalKeyboard` | (none) | Global keyboard shortcuts (Esc, Ctrl+S, PgUp/Dn, Shift+T, Shift+M) |
| `useProvider` | `activeProvider`, `allProviders` | Provider state subscriber |
| `useTickAnimation` | `tick` | Animation interval counter |

### Services Layer

| Service | Type | Purpose |
|---------|------|---------|
| `StartupService` | REST (`/startup/validate`) | Async startup validation on launch |
| `WebSocketClient` | WebSocket (JSON-RPC) | Bidirectional event streaming |
| `BackendScenarioProvider` | WebSocket listener | Maps backend `EventKind` → frontend `ScenarioEvent` |
| `EventMapper` | Pure function | 19 event kind transformations |
| `SessionService` | WebSocket | Session CRUD |
| `ProviderService` | Local (JSON config + user_profile.json) | Provider state, config CRUD |
| `ProviderRepository` | Local (static JSON + user_profile.json) | Provider metadata + persisted config |
| `CommandService` | Local (`options.json`) | Slash command dispatch |
| `userProfileService` | File (`user_profile.json`) | User preferences (theme, mode, provider, settings) |

### Data Flow: Configuration

```
User types API key in UI
  → ProviderRepository.updateProviderConfig()
    → saveUserProfile() writes to user_profile.json
      → ProviderService.notifyListeners()
        → React components re-render via useProvider()
```

**Note:** The frontend stores provider config in `user_profile.json` independently of the backend's `.zenith.json`. This is a **dual-configuration** antipattern — the two can diverge.

---

## 2. Backend Architecture Summary

### Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Runtime | Python 3.11+ | Async event loop |
| ASGI Server | uvicorn | HTTP + WebSocket server |
| Framework | FastAPI | REST routes + WebSocket endpoint |
| ORM/DB | aiosqlite + raw SQL | SQLite persistence |
| Validation | Pydantic v2 | Model validation, settings |
| LLM Bridge | litellm | Unified provider API (OpenAI, Anthropic, Google, Groq, OpenRouter) |
| Tokenizer | tiktoken (optional) | Token counting |
| Auth | None | No authentication layer |
| CLI | Click | `zenith serve` command |

### Module Map

```
zenith/
├── __init__.py        — version
├── __main__.py        — if __name__ == "__main__": cli()
├── main.py            — Click CLI: `zenith serve --host --port`
│
├── config/
│   ├── settings.py    — AppSettings, ToolConfig, BootstrapDefaults (Pydantic)
│   ├── providers.py   — ProviderConfig model (api_key, model, base_url, etc.)
│   ├── loader.py      — load_config(), save_config(), _validate_config()
│   └── __init__.py
│
├── core/
│   ├── session.py     — Session model (Pydantic)
│   ├── message.py     — Message model (events list, tokens)
│   ├── events.py      — Event model, EventKind enum (19 kinds)
│   └── errors.py      — ZenithError hierarchy (ConfigError, ProviderError, ToolError, etc.)
│
├── db/
│   ├── connection.py  — Database (aiosqlite wrapper, schema apply, migrations)
│   ├── schema.sql     — sessions + messages tables
│   ├── repository.py  — SessionRepository, MessageRepository
│   ├── migration.py   — MigrationRunner (_migrations table, numbered .sql files)
│   └── migrations/    — (empty, no migrations yet)
│
├── providers/
│   ├── base.py        — BaseProvider ABC (complete, stream, validate, list_models)
│   ├── llm_provider.py — LLMProvider (litellm implementation)
│   ├── registry.py    — ProviderRegistry (from_config, get, require, list)
│   ├── retry.py       — retry_with_backoff (exponential backoff + jitter)
│   └── token_counter.py — TokenCounter (tiktoken with heuristic fallback)
│
├── tools/
│   ├── base.py        — BaseTool ABC, ToolResult model
│   ├── registry.py    — ToolRegistry (register, execute, get_schema)
│   ├── permission.py  — PermissionGate (mode-based tool restrictions)
│   ├── bash.py        — BashTool (subprocess with timeout)
│   ├── file_read.py   — FileReadTool
│   ├── file_write.py  — FileWriteTool
│   ├── file_edit.py   — FileEditTool (search-replace)
│   ├── file_delete.py — FileDeleteTool
│   ├── glob_tool.py   — GlobTool
│   ├── grep_tool.py   — GrepTool
│   └── webfetch.py    — WebfetchTool
│
├── agent/
│   ├── loop.py        — AgentLoop (multi-step: LLM → tool calls → response)
│   ├── context.py     — ContextManager (token budgeting, summarization trigger)
│   ├── prompts.py     — build_system_prompt (mode-aware, tool list, repo context, skills)
│   └── recovery.py    — RecoverableAgentLoop wrapper
│
├── session/
│   ├── history.py     — HistoryManager (summarization)
│   └── export.py      — SessionExporter (markdown export)
│
├── skills/
│   └── loader.py      — SkillLoader (find SKILL.md files, build prompt section)
│
├── workspace/
│   ├── git.py         — GitOps (status, diff, log)
│   ├── tracker.py     — FileTracker (track created/modified/deleted files)
│   └── repo_map.py    — RepoMap (project structure, summary, key files)
│
└── transport/
      ├── server.py    — create_app(), lifespan, REST routes, WebSocket endpoint
      ├── websocket.py — ZenithHandler (16 JSON-RPC methods, ConnectionManager)
      ├── protocol.py  — JsonRpcRequest, make_response, make_error_response, make_event
      ├── startup.py   — validate_startup(), validate_provider_setup(), save_provider_setup()
      ├── middleware.py — validate_provider_config(), wrap_handler()
      └── shutdown.py  — GracefulShutdown
```

### WebSocket RPC Methods (16 total)

| Method | Handler | Purpose |
|--------|---------|---------|
| `session.create` | `_handle_session_create` | Create a new session |
| `session.list` | `_handle_session_list` | List active sessions |
| `session.resume` | `_handle_session_resume` | Resume a session with history |
| `session.export` | `_handle_session_export` | Export session as markdown |
| `prompt.send` | `_handle_prompt` | Submit prompt, stream events back |
| `provider.validate` | `_handle_provider_validate` | Check provider connectivity |
| `provider.models` | `_handle_provider_models` | List available models (hardcoded) |
| `tools.list` | `_handle_tools_list` | List tool schemas for mode |
| `workspace.status` | `_handle_workspace_status` | Git status |
| `workspace.diff` | `_handle_workspace_diff` | Git diff (staged/unstaged) |
| `workspace.log` | `_handle_workspace_log` | Git log |
| `workspace.repo_map` | `_handle_workspace_repo_map` | Repo structure + summary |
| `health` | (inline) | Liveness check |
| *(middleware rejects)* | `-32000` | Provider config missing |

### REST Endpoints (5 total)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Liveness: `{status, handler, version}` |
| `GET` | `/status` | Readiness: `{ready, provider, workspace, tools}` |
| `GET` | `/startup/validate` | Startup validation: `{status, missing[], ...}` |
| `POST` | `/startup/validate-provider` | Validate provider config during setup |
| `POST` | `/startup/save-config` | Save provider config during setup |
| `GET` | `/ws` (upgrade) | WebSocket for all business logic |

---

## 3. End-to-End Request Lifecycle

### Flow A: Full Prompt Execution

```
User types prompt "create a todo app" + Enter
  │
  ▼
App.tsx handleSubmit()
  ├── addHistory(trimmed)          — save to input history
  ├── addTurn(trimmed, mode)       — create ConversationTurn
  ├── clearInput()                 — reset input field
  └── startScenario(trimmed, mode) — useScenario()
        │
        ▼
  useScenario.startScenario()
    ├── wsClient.connect()         — WebSocket to ws://localhost:8765/ws
    ├── wsClient.createSession()   — JSON-RPC: session.create
    ├── backendScenarioProvider.resolve() — return empty Scenario
    ├── backendScenarioProvider.execute() — subscribe to WebSocket events
    ├── wsClient.sendPrompt()      — JSON-RPC: prompt.send {content, mode, session_id}
    │
    ▼
  Backend WebSocket receives prompt.send
    ├── _handle_prompt()
    │     ├── Load history from DB
    │     ├── Create RecoverableAgentLoop
    │     ├── agent.process_prompt(content, session_id, history, mode, skills_section)
    │     │     ├── build_system_prompt() — mode instructions + tools + repo context + skills
    │     │     ├── context_manager.build_messages() — token-budgeted message list
    │     │     ├── provider.stream(messages) — litellm.acompletion(stream=True)
    │     │     │     └── Litellm translates to provider API (OpenAI, Anthropic, etc.)
    │     │     ├── Parse tool calls from LLM response
    │     │     ├── Execute tools (bash, file_write, etc.)
    │     │     ├── Feed tool results back to LLM
    │     │     └── Repeat until no more tool calls (max 25 iterations)
    │     │
    │     └── Each step yields Event objects → sent via WebSocket
    │
    ▼
  Frontend WebSocketClient receives events
    ├── EventMapper.mapEvent() converts backend EventKind → frontend ScenarioEvent
    ├── backendScenarioProvider.onEvent() callback fires
    │     └── setEvents() → React re-render → ScenarioRenderer displays
    │
    ▼
  Backend finishes processing
    ├── Assistant message saved to DB
    ├── FINAL event (success + token info)
    └── Stream closes
          │
          ▼
  Frontend sets isRunning=false
    ├── useScenario completes
    ├── completeActiveTurn(events) — stores events in ConversationTurn
    └── addSession(prompt) — adds to Recent Sessions list
```

### Flow B: Startup Validation

```
npm start → tsx src/index.tsx
  │
  ▼
ThemeProvider → ErrorBoundary → App (mounts)
  │
  ▼
useEffect → startupService.initialize()
  │
  ├── state.phase = 'loading' → render "Initializing Zenith..."
  │
  └── fetch GET /startup/validate
        │
        ├── Success: {status:"ready"} → phase=ready → render Main App
        │     └── WelcomeScreen + input + overlays
        │
        ├── Success: {status:"configuration_required", missing:[...]} → phase=setup
        │     └── SetupWizard
        │           ├── Intro → Select Provider → Enter API Key → Select Model
        │           ├── POST /startup/validate-provider
        │           ├── POST /startup/save-config
        │           └── revalidate → phase=ready → Main App
        │
        └── Error (network failure) → phase=error
              └── SetupWizard shows error message + retry
```

### Flow C: Provider Middleware Validation

```
WebSocket message arrives: prompt.send
  │
  ▼
ZenithHandler.handle() → _dispatch()
  │
  ▼
middleware.wrap_handler() intercepts
  ├── require_provider("prompt.send") → True
  ├── validate_provider_config(config)
  │     ├── active_provider exists?        → NO → return -32000 error
  │     ├── provider configured?            → NO → return -32000 error
  │     ├── API key present?               → NO → return -32000 error
  │     └── model selected?                 → NO → return -32000 error
  │
  └── All valid? → pass to original _dispatch handler
```

---

## 4. Startup Verification Guide

### Test Environment Setup

```bash
# Terminal 1 — Backend
cd D:\vdo\code\zenith-frontend-tui
.\.venv\Scripts\Activate.ps1
zenith serve --port 8765

# Terminal 2 — Frontend
cd D:\vdo\code\zenith-frontend-tui
npm start
```

### Step-by-Step Verification

| # | Test | Expected Result | Status |
|---|------|----------------|--------|
| 1 | Start backend with no `.zenith.json` | Backend starts. Config warnings logged. Server listens on :8765 | |
| 2 | `curl http://localhost:8765/health` | `{"status":"ok","handler":true,"version":"0.1.0"}` | |
| 3 | `curl http://localhost:8765/startup/validate` | `{"status":"configuration_required","missing":["provider","model","apiKey"],...}` | |
| 4 | Start frontend with no config | Shows "Initializing Zenith..." then Setup Wizard | |
| 5 | Setup Wizard: Intro screen | Shows "⚙ Setup Required" with list of missing items | |
| 6 | Press Enter → Select Provider | Lists 6 providers (OpenRouter, OpenAI, Anthropic, Gemini, Groq, Custom) | |
| 7 | Navigate to OpenRouter, Enter | Step advances to API Key entry | |
| 8 | Press Space to edit key | Cursor appears, typing is masked as `••••` | |
| 9 | Type fake key, Enter | Advances to Model selection (or falls through to default) | |
| 10 | Select model, Enter | Validates, saves to `.zenith.json`, returns to Welcome screen | |
| 11 | Verify `.zenith.json` created | Contains `active_provider`, provider config with api_key | |
| 12 | Restart backend **without** `.zenith.json` | Deleted file → backend falls back to env vars | |
| 13 | Set `ZENITH_OPENAI_API_KEY=sk-test` env var | Restart backend, `startup/validate` should see the key | |
| 14 | `curl /startup/validate` with valid config | `{"status":"ready","missing":[],...}` | |
| 15 | Start frontend with valid config | Skips wizard, shows WelcomeScreen immediately | |

### Edge Cases

| Test | Expected | Status |
|------|----------|--------|
| No backend running, start frontend | Shows "Cannot connect to backend" in SetupWizard | |
| Corrupt `.zenith.json` | Backend fails to start with JSON decode error | |
| Empty `.zenith.json` | Backend starts, config_required returned | |
| Backend stops during wizard | Fetch fails, wizard shows error + retry | |
| Set `ZENITH_STRICT_VALIDATION=true` | Backend exits on config warnings | |

---

## 5. Provider Setup Guide

### OpenRouter Configuration

1. **Get an API key**
   - Go to https://openrouter.ai/keys
   - Sign in/create account
   - Click "Create Key"
   - Copy the key (starts with `sk-or-v1-`)

2. **Configure via Setup Wizard** (recommended for first-time use)
   - Start frontend with `npm start`
   - Setup Wizard appears automatically
   - Navigate to "OpenRouter AI" using ↑/↓
   - Press Enter to select
   - Press Space to start typing API key
   - Paste or type `sk-or-v1-...`
   - Press Enter to confirm
   - Select model (e.g., `openai/gpt-4o` or `anthropic/claude-sonnet-4-20250514`)
   - Press Enter to validate and save
   - Wizard completes → Welcome screen appears

3. **Configure via `.zenith.json`**
   ```json
   {
     "active_provider": "openrouter",
     "providers": {
       "openrouter": {
         "api_key": "sk-or-v1-...",
         "model": "openai/gpt-4o",
         "base_url": "https://openrouter.ai/api/v1"
       }
     }
   }
   ```

4. **Configure via Environment Variables**
   ```bash
   export ZENITH_ACTIVE_PROVIDER=openrouter
   export ZENITH_OPENROUTER_API_KEY=sk-or-v1-...
   ```

5. **Verify Configuration**
   ```bash
   curl http://localhost:8765/startup/validate
   # {"status":"ready","active_provider":"openrouter","active_model":"openai/gpt-4o",...}
   ```

### All Supported Providers

| Provider | Frontend ID | API Key Format | Base URL |
|----------|------------|----------------|----------|
| OpenRouter | `openrouter` | `sk-or-v1-...` | `https://openrouter.ai/api/v1` |
| OpenAI | `openai` | `sk-...` | `https://api.openai.com/v1` |
| Anthropic | `anthropic` | `sk-ant-...` | `https://api.anthropic.com` |
| Google Gemini | `gemini` | (varies) | `https://generativelanguage.googleapis.com` |
| Groq | `groq` | `gsk_...` | `https://api.groq.com` |
| Custom | `custom` | Any | User-specified (Ollama, etc.) |

### Common Mistakes

| Mistake | Symptom | Fix |
|---------|---------|-----|
| Missing `sk-` prefix | "API key format looks wrong" | Check key starts with correct prefix |
| Wrong model name | "Model not found" or empty response | Use full model ID (e.g., `openai/gpt-4o` for OpenRouter) |
| Trailing whitespace in key | Silent auth failures | Trim the key before saving |
| No base URL for custom provider | Connection refused | Set base URL (e.g., `http://localhost:11434/v1` for Ollama) |
| `.zenith.json` in wrong directory | Backend loads default config | Ensure `.zenith.json` is in CWD where `zenith serve` runs |

---

## 6. OpenRouter Integration Review

### Current Implementation

**Backend (`llm_provider.py`):**
- Uses `litellm` library with provider prefix `"openrouter"`
- Model IDs are prefixed as `openrouter/<model>` (e.g., `openrouter/openai/gpt-4o`)
- API key passed via `api_key` kwarg to litellm
- Base URL configurable via `base_url` (default: None — litellm uses its own default)
- No OpenRouter-specific headers (`HTTP-Referer`, `X-Title`)
- No OpenRouter-specific error handling or rate limit parsing
- Models list is hardcoded: `["openai/gpt-4o", "anthropic/claude-sonnet-4-20250514"]`
- No model discovery via API
- No support for OpenRouter-specific parameters (route, provider preferences, etc.)

**Frontend (`openrouter/config.json`):**
- Name: "OpenRouter AI"
- Description: "Unified router access to 100+ top open and proprietary models"
- Default model: `openrouter/auto`
- Base URL: `https://openrouter.ai/api/v1`
- Fields: API Key (required), Base URL, Timeout
- No `availableModels` array — no model selection in Setup Wizard
- No OpenRouter-specific fields (allow_fallbacks, route, etc.)

### Issues Found

1. **Missing required OpenRouter headers** — The OpenRouter API requires `HTTP-Referer` and `X-Title` headers for ranking and tracking. These are not sent.
2. **Model list is hardcoded** — OpenRouter has 200+ models. The hardcoded list of 2 is extremely limited. Should use `/api/v1/models` endpoint.
3. **No `openrouter/auto` model in backend** — The frontend default is `openrouter/auto` but the backend maps to `openrouter/openrouter/auto` (double prefix) via `_model_id()`.
4. **No rate limit handling** — OpenRouter returns `429` with `retry-after-ms` header. This isn't parsed.
5. **No error code mapping** — OpenRouter uses specific error codes (`insufficient_quota`, `invalid_api_key`, etc.) that should be mapped to typed errors.

---

## 7. OpenRouter API/SDK Compliance Report

### Specification Check

| Requirement | Status | Details |
|------------|--------|---------|
| API Key in header | ✅ | Passed via litellm `api_key` kwarg |
| Model ID format `provider/model` | ✅ | Prefixed via `_model_id()` |
| Base URL configurable | ✅ | Via `base_url` param |
| Streaming support | ✅ | `litellm.acompletion(stream=True)` |
| `HTTP-Referer` header | ❌ Missing | Required for OpenRouter rankings |
| `X-Title` header | ❌ Missing | Required for OpenRouter tracking |
| Model discovery API | ❌ Missing | `/api/v1/models` not called |
| Rate limit parsing | ❌ Missing | `retry-after-ms` not parsed from responses |
| Error code mapping | ❌ Missing | `insufficient_quota`, `invalid_api_key`, `moderation` not mapped |
| `provider` parameter | ❌ Missing | Cannot force specific provider (e.g., `provider: {order: ["Anthropic"]}`) |
| `route` parameter | ❌ Missing | Cannot set fallback behavior |
| `max_price` parameter | ❌ Missing | No price capping |
| Token counting | ✅ | tiktoken + heuristic fallback |
| Response parsing | ✅ | Standard litellm response format handled |

### Recommended Fixes

1. **Send required headers** in `_build_kwargs()`:
   ```python
   kwargs["extra_headers"] = {
       "HTTP-Referer": "https://github.com/anomalyco/zenith",
       "X-Title": "Zenith AI Coding Assistant",
   }
   ```

2. **Replace hardcoded model list** with API call to `https://openrouter.ai/api/v1/models`:
   - Filter by supported capabilities
   - Cache with 10-minute TTL

3. **Fix double-prefix bug**: The `_model_id()` method should detect `openrouter/` prefix on model names like `openai/gpt-4o` and NOT prepend another `openrouter/`.

4. **Add OpenRouter error parser** in `LLMProvider.complete()`:
   - Parse `retry-after-ms` → `RateLimitError`
   - Parse error codes → typed errors

5. **Expose route/fallback params** in frontend config:

---

## 8. Manual Testing Scenarios

### 8.1 Application Startup

| Step | Action | Expected Result |
|------|--------|----------------|
| 1.1 | Start backend with valid `.zenith.json` | Server starts, logs "Handler initialized" |
| 1.2 | Start frontend | Shows "Initializing Zenith..." then Welcome screen |
| 1.3 | Verify Welcome screen shows | Logo ASCII art, "SYSTEM STATUS", provider name, model, workspace, greeting, "RECENT SESSIONS" |
| 1.4 | Verify input ready | `❯ Ask anything...` prompt visible |
| 1.5 | Remove `.zenith.json`, restart backend + frontend | Shows Setup Wizard |
| 1.6 | Complete Setup Wizard | Welcome screen appears with configured provider |

### 8.2 Mode Selection

| Step | Action | Expected Result |
|------|--------|----------------|
| 2.1 | Press `Shift+M` | Mode select overlay opens |
| 2.2 | Navigate with ↑/↓ | Selection highlight moves |
| 2.3 | Select "Plan" mode, Enter | Overlay closes, status bar shows "PLAN" |
| 2.4 | Type `/build`, Enter | Mode switches to BUILD |
| 2.5 | Type `/mode`, Enter | Mode select overlay opens |
| 2.6 | Press Esc | Overlay closes without changing mode |

### 8.3 Prompt Execution (Backend Required)

| Step | Action | Expected Result |
|------|--------|----------------|
| 3.1 | In BUILD mode, type "create a FastAPI project" + Enter | `Thinking` indicator, events stream in |
| 3.2 | Observe `file_create` events | File creation cards with diff display |
| 3.3 | Observe `terminal` events | Command execution with output |
| 3.4 | Wait for completion | Success card with token info |
| 3.5 | Verify conversation turn saved | Previous turn visible above input |
| 3.6 | In PLAN mode, type "design a React architecture" + Enter | Analysis cards with sections, no file modifications |
| 3.7 | Press `Ctrl+S` during or after plan | Plan exported as `zenith_plans/implementation-plan.md` |
| 3.8 | Verify exported file exists | Contains markdown of all events |

### 8.4 Slash Commands

| Step | Action | Expected Result |
|------|--------|----------------|
| 4.1 | Type `/` | Autocomplete dropdown appears with 10 commands |
| 4.2 | Type `/help` + Enter | Help modal shows all keyboard shortcuts |
| 4.3 | Type `/settings` + Enter | Settings modal shows theme + preferences |
| 4.4 | Navigate themes with ↑/↓ | Live theme preview |
| 4.5 | Press Esc to close settings | Returns to main view |
| 4.6 | Type `/clear` + Enter | All conversation turns cleared |
| 4.7 | Type `/compact` + Enter | Turns replaced with summary turn |
| 4.8 | Type `/context` + Enter | Context modal shows token usage |
| 4.9 | Type `/add-dir` + Enter | Directory picker modal |
| 4.10 | Type `/provider` + Enter | Provider list screen |

### 8.5 Provider Management

| Step | Action | Expected Result |
|------|--------|----------------|
| 5.1 | `/provider` → Enter | Provider list shows 6 providers |
| 5.2 | Navigate to Anthropic + `A` | Anthropic becomes active (checkmark) |
| 5.3 | Press Enter on active provider | Config form opens |
| 5.4 | Navigate to API Key field | Highlighted |
| 5.5 | Press Enter to edit, type key, Enter | Key saved |
| 5.6 | Navigate to Base URL, edit | URL saved |
| 5.7 | Press Esc to return to list | Provider list shows updated config |
| 5.8 | Switch back to OpenRouter | Active provider updates throughout app |
| 5.9 | Verify Welcome screen shows new provider | Provider name and model updated |

### 8.6 Error Handling

| Step | Action | Expected Result |
|------|--------|----------------|
| 6.1 | Stop backend, submit prompt | Error card: "Cannot connect to backend" |
| 6.2 | Start backend with no API key, submit prompt | Middleware rejects with -32000 error |
| 6.3 | Type empty string + Enter | Input ignored, no action |
| 6.4 | Type `/invalid-command` + Enter | Command shows "Unknown command" message |
| 6.5 | Disconnect network during prompt execution | Error card: "Connection to backend lost" |
| 6.6 | Press Esc during prompt execution | Scenario aborts, "Cancelled by user" warning |
| 6.7 | Remove `.zenith.json`, restart backend | `startup/validate` returns `configuration_required` |

### 8.7 File Operations (via LLM tool calls)

| Step | Action | Expected Result |
|------|--------|----------------|
| 7.1 | "create a python script hello.py" | File create event with content |
| 7.2 | "add error handling to hello.py" | File edit event with diff (removed + added lines) |
| 7.3 | "delete hello.py" | File delete event |
| 7.4 | "create a React component" | Multiple file creates in proper directory structure |
| 7.5 | "list all .py files" | Glob tool executes, returns file list |

### 8.8 Terminal Execution

| Step | Action | Expected Result |
|------|--------|----------------|
| 8.1 | "run pytest" | Terminal event with command + output |
| 8.2 | "install a package" | Terminal event showing install output |
| 8.3 | "run a failing command" | Error event with stderr output |
| 8.4 | "retry the last command" | (Agent should retry on recoverable errors) |

### 8.9 Keyboard Shortcuts

| Key | Expected | Status |
|-----|----------|--------|
| `Esc` (when running) | Aborts scenario | |
| `Esc` (in overlay) | Closes overlay (1-step-back) | |
| `PgUp` | Scroll up conversation turns | |
| `PgDn` | Scroll down conversation turns | |
| `Shift+T` | Toggle thinking block collapse | |
| `Shift+M` | Open mode selector | |
| `Ctrl+S` | Export plan to markdown | |
| `Shift+Enter` | Newline in input (not submit) | |

---

## 9. Example Prompts by Feature

### Planning

| Prompt | Mode | Expected Events |
|--------|------|----------------|
| "Design a REST API for a blog with users, posts, comments" | plan | analysis → sections for models, endpoints, auth |
| "Create a development plan for migrating from JS to TS" | plan | analysis → migration steps, risks, timeline |
| "Plan the architecture for a real-time chat application" | plan | analysis → WebSocket design, data model, scaling |
| "Design a database schema for an e-commerce platform" | plan | analysis → tables, relationships, indexes |

### Code Generation

| Prompt | Mode | Expected Events |
|--------|------|----------------|
| "Create a FastAPI project with CRUD endpoints for tasks" | build | file_create (main.py, models.py, schemas.py, etc.) |
| "Generate a React Todo component with TypeScript" | build | file_create (Todo.tsx, types.ts, styles) |
| "Build a Python CLI using Click that manages todo items" | build | file_create (cli.py, todo.py, requirements.txt) |
| "Create a Docker Compose for FastAPI + PostgreSQL + Redis" | build | file_create (docker-compose.yml, Dockerfile, etc.) |

### File Operations

| Prompt | Mode | Expected Events |
|--------|------|----------------|
| "Add JWT authentication middleware to main.py" | build | file_edit with diff |
| "Refactor the database module to use async/await" | build | file_edit with multiple edits |
| "Delete all temporary log files" | build | file_delete events |
| "Create a complete React dashboard with 3 components" | build | Multiple file_create events in src/components/ |

### Testing

| Prompt | Mode | Expected Events |
|--------|------|----------------|
| "Add unit tests for the user service" | build | file_create (test_user_service.py), terminal (pytest) |
| "Run the test suite and fix failures" | build | terminal (pytest), file_edit (fixes), terminal (re-run) |

### Error Recovery

| Prompt | Mode | Expected Events |
|--------|------|----------------|
| (no backend) "create a file" | build | error: "Cannot connect to backend" |
| (invalid API key) "run a command" | build | error from middleware or provider |

---

## 10. Feature Verification Checklist

### 10.1 Frontend Features

| # | Feature | Test Steps | Expected | Status |
|---|---------|-----------|----------|--------|
| F1 | Startup validation | Start without config | Setup Wizard appears | |
| F2 | Welcome screen | Start with valid config | Logo, status, greeting, sessions | |
| F3 | Command input | Type text | Text appears at prompt | |
| F4 | Input history | ↑/↓ | Previous prompts cycle | |
| F5 | Prompt submit | Enter | Scenario starts (or error) | |
| F6 | Mode selector | Shift+M | Overlay opens | |
| F7 | Mode switching | Select Plan | Status bar shows PLAN | |
| F8 | /mode command | Type `/mode` + Enter | Mode overlay opens | |
| F9 | /help command | Type `/help` + Enter | Help modal displays | |
| F10 | /settings command | Type `/settings` + Enter | Settings modal displays | |
| F11 | Theme switching | Navigate in settings | Live theme preview | |
| F12 | /clear command | Type `/clear` + Enter | All turns cleared | |
| F13 | /compact command | Type `/compact` + Enter | Turns replaced by summary | |
| F14 | /context command | Type `/context` + Enter | Context/token modal | |
| F15 | /add-dir command | Type `/add-dir` + Enter | Directory picker | |
| F16 | /provider command | Type `/provider` + Enter | Provider list | |
| F17 | /build command | Type `/build` + Enter | Mode switches to BUILD | |
| F18 | /plan command | Type `/plan` + Enter | Mode switches to PLAN | |
| F19 | Provider list | Open provider screen | 6 providers listed | |
| F20 | Provider activation | Select + A | Active provider changes | |
| F21 | Provider config edit | Enter on provider | Config form opens | |
| F22 | Auto-complete dropdown | Type `/` | Command list appears | |
| F23 | File picker | Type `@` | File browser opens | |
| F24 | Scenario rendering | Submit prompt | Events render as cards | |
| F25 | Error card rendering | Backend down | Error box with message | |
| F26 | Thinking block | Toggle with Shift+T | Collapse/expand | |
| F27 | Plan export | Ctrl+S | File saved to zenith_plans/ | |
| F28 | Turn scrolling | PgUp/PgDn | Hidden turns scroll | |
| F29 | Esc abort | During scenario | Scenario stops, warning | |
| F30 | Setup Wizard | Missing config | 4-step guided setup | |

### 10.2 Backend Features

| # | Feature | Test Steps | Expected | Status |
|---|---------|-----------|----------|--------|
| B1 | Server startup | `zenith serve` | Listens on :8765 | |
| B2 | Health endpoint | `GET /health` | `{"status":"ok"}` | |
| B3 | Status endpoint | `GET /status` | `{"ready":true,...}` | |
| B4 | Startup validate | `GET /startup/validate` | Structured result | |
| B5 | Config load | From `.zenith.json` | Settings populated | |
| B6 | Config env override | Set env var | Env overrides file | |
| B7 | DB schema creation | Auto on connect | tables: sessions, messages | |
| B8 | DB migrations | On connect | _migrations table created | |
| B9 | Provider registry | From config | Providers registered | |
| B10 | Provider validate | RPC `provider.validate` | Valid/invalid response | |
| B11 | Session create | RPC `session.create` | Session returned | |
| B12 | Session list | RPC `session.list` | Active sessions | |
| B13 | Session resume | RPC `session.resume` | Session + messages | |
| B14 | Session export | RPC `session.export` | Markdown filepath | |
| B15 | Prompt send | RPC `prompt.send` | Events streamed | |
| B16 | Tool execution | LLM calls tools | Tools run, results returned | |
| B17 | Middleware validation | Missing provider | -32000 error | |
| B18 | Workspace git status | RPC `workspace.status` | Git status dict | |
| B19 | Workspace diff | RPC `workspace.diff` | Diff text | |
| B20 | Workspace log | RPC `workspace.log` | Commit log | |
| B21 | Repo map | RPC `workspace.repo_map` | Structure + summary | |
| B22 | Skills loading | In handler init | Skills found/loaded | |
| B23 | Recovery wrapping | Agent errors | RecoverableAgentLoop used | |
| B24 | Retry with backoff | Provider errors | Retry with exponential delay | |

---

## 11. Production Readiness Checklist

### Startup & Configuration

- [ ] Backend starts without crashing on missing config
- [ ] Backend starts without crashing on corrupt config
- [ ] Frontend shows Setup Wizard when config missing
- [ ] Frontend transitions to Welcome when config valid
- [ ] `.zenith.json` and environment variables both work
- [ ] `ZENITH_STRICT_VALIDATION=true` exits on config warnings

### Provider Connectivity

- [ ] Provider.validate() actually calls the LLM API (not just local check)
- [ ] Invalid API key returns meaningful error (not generic 500)
- [ ] Missing API key caught by startup validation
- [ ] Missing API key caught by WebSocket middleware
- [ ] Model selection maps to valid model ID

### Prompt Execution

- [ ] Prompt with tool calls completes successfully
- [ ] Streaming tokens appear in real-time on frontend
- [ ] Tool call LLM → tool execution → LLM cycle works
- [ ] Max iterations (25) stops infinite loops
- [ ] Empty prompt returns error (not crash)
- [ ] Very long prompt fits within context budget
- [ ] Esc cancels mid-execution cleanly

### Error Handling

- [ ] Backend restart doesn't leave dangling connections
- [ ] WebSocket disconnect triggers cleanup
- [ ] Provider timeout triggers retry (not silent hang)
- [ ] Rate limit error triggers retry with backoff
- [ ] Non-recoverable errors surface to user correctly
- [ ] Frontend handles backend-down gracefully
- [ ] Middleware rejects unconfigured providers

### Security

- [ ] API keys not logged in plaintext
- [ ] API keys not exposed in error messages
- [ ] Bash tool has timeout (30s default)
- [ ] File tool operations restricted to workspace root
- [ ] No eval() or dynamic imports of user input
- [ ] SQL uses parameterized queries (not string interpolation)

### Persistence

- [ ] Sessions survive backend restart (SQLite)
- [ ] Messages saved with events as JSON
- [ ] Config persisted across restarts
- [ ] User profile (theme, preferences) persists
- [ ] Migration system works (no data loss on schema changes)

### Performance & Limits

- [ ] Max context tokens respected (128k default)
- [ ] Token counting works without tiktoken (heuristic fallback)
- [ ] Tool output truncated at 10k chars
- [ ] Bash commands respect timeout
- [ ] WebSocket reconnection with backoff (5 attempts max)

### Monitoring

- [ ] Backend logs startup with config summary
- [ ] Backend logs provider registration
- [ ] SQLite WAL mode enabled for concurrent reads
- [ ] Graceful shutdown closes DB connection

---

## 12. Gap Analysis & Prioritized Recommendations

### Critical (Blocks Production Use)

| # | Issue | Current Behavior | Expected | Fix | Priority |
|---|-------|-----------------|----------|-----|----------|
| G1 | Dual config stores diverge | Frontend writes to `user_profile.json`, backend reads from `.zenith.json`. User configures via wizard → saved to backend but frontend still has stale local data. | Single source of truth — frontend always reads from backend or backend always writes to `.zenith.json`. | Remove provider config from `user_profile.json`. Frontend should only read provider state from backend REST. | **P0** |
| G2 | No API key validation on save | Setup Wizard `POST /startup/validate-provider` only checks key prefix format, not actual API connectivity. Users can save invalid keys. | Wizard should call `provider.validate()` (actual API call) before accepting config. | Add `validate_provider_setup()` to do a real `complete([{"role":"user","content":"OK"}])` call. | **P0** |
| G3 | OpenRouter double-prefix bug | `_model_id()` prepends `openrouter/` to model names. Default `openrouter/auto` becomes `openrouter/openrouter/auto` | `openrouter/auto` should stay as-is (already has prefix). | Check if model already starts with provider prefix before prepending. | **P0** |
| G4 | Frontend tests mock backend only, no real connectivity test | All 25 frontend tests pass without a real backend connection. | Integration tests verify actual WebSocket communication. | Add playwright/ink integration tests with real backend. | **P0** |

### High Priority

| # | Issue | Current Behavior | Expected | Fix | Priority |
|---|-------|-----------------|----------|-----|----------|
| G5 | OpenRouter missing headers | `HTTP-Referer` and `X-Title` headers not sent | Sent for ranking/tracking | Add `extra_headers` to litellm kwargs | P1 |
| G6 | Provider model list hardcoded | `list_models()` returns hardcoded arrays | Should fetch from API or at least expose full known list | Query `/api/v1/models` for OpenRouter; expand hardcoded lists | P1 |
| G7 | No WebSocket auth | Anyone who connects to :8765 can use the backend without authentication | At minimum, require matching origin or token | Add simple API key check on WebSocket upgrade | P1 |
| G8 | Error events not mapped to typed frontend errors | Backend sends `EventKind.ERROR` with generic message | Frontend should map to ErrorEvent with code, recovery hint | Add `code` field to ErrorEvent, map in component registry | P1 |
| G9 | Session status bar shows hardcoded provider info | "Provider: Anthropic Claude | Model: claude-3-5-sonnet-latest" is from user_profile.json, not backend | Read active provider from backend state | Sync provider display from backend config | P1 |

### Medium Priority

| # | Issue | Current Behavior | Expected | Fix | Priority |
|---|-------|-----------------|----------|-----|----------|
| G10 | No graceful reconnection on WebSocket drop | Frontend creates new session on reconnect instead of resuming | Reconnect with same session_id | Track session_id in localStorage | P2 |
| G11 | `artificialLatency` in WebSocket client | `WebSocketClient` has `artificialLatency = 800` that is never used | Should be removed or documented | Remove field | P2 |
| G12 | Frontend `providerSettings` stores all config in `user_profile.json` | API keys persisted in `user_profile.json` alongside theme preferences | Configs should be in `.zenith.json`, not mixed with user prefs | Separate provider config from user profile | P2 |
| G13 | No OpenRouter model discovery in frontend | `openrouter/config.json` has no `availableModels` array | Should list available models (fetched or static list) | Add model list to config.json | P2 |
| G14 | Backend config not hot-reloadable | Changing `.zenith.json` requires restart | Should watch for file changes | Add file watcher or `/config/reload` endpoint | P2 |
| G15 | 4 silent `try/catch (_err)` blocks in frontend | `userProfileService.ts` has 4 empty catch blocks | Should log errors | Add `console.warn()` in each catch | P2 |

### Low Priority

| # | Issue | Current Behavior | Expected | Fix | Priority |
|---|-------|-----------------|----------|-----|----------|
| G16 | No pagination for conversation turns | All turns loaded into memory | Virtual list for large conversations | Implement turn windowing | P3 |
| G17 | No ANSI output handling in terminal events | Raw ANSI codes shown in terminal output | Strip or render ANSI codes | Add ANSI stripping before display | P3 |
| G18 | WebSocket client has no ping/pong | No keepalive; connection may drop silently | Periodic ping to detect dead connections | Add heartbeat interval | P3 |
| G19 | No request ID tracing | Cannot correlate frontend → backend requests | Add correlation IDs | Pass request ID through the chain | P3 |
| G20 | Migration directory is empty | `db/migrations/` exists but has no migration files | At minimum a baseline migration | Empty directory is harmless but confusing | P3 |

### Summary

| Priority | Count | Key Action Items |
|----------|-------|-----------------|
| P0 | 4 | Fix dual config, real API validation, double-prefix, integration tests |
| P1 | 5 | OpenRouter headers, model lists, WebSocket auth, error mapping, provider sync |
| P2 | 6 | Reconnection, cleanup, split config, model discovery, hot-reload, silent catches |
| P3 | 4 | Virtual list, ANSI, heartbeat, tracing |

---

*End of Testing Guide*
