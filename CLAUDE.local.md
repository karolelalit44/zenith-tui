# Zenith TUI - Agent Mode

## Overview
Zenith is a full-stack terminal UI application with a Python backend server and React-based TUI frontend. It provides an agentic coding assistant experience with scenario-based workflows, tool execution, and real-time streaming.

## Architecture

### Backend (Python)
- **server/** - FastAPI-based backend with WebSocket support
  - `api/handlers.py` - HTTP & WebSocket RPC dispatch
  - `api/websocket.py` - Connection management
  - `sessions/service.py` - Session lifecycle management
  - `providers/llm_provider.py` - LLM provider abstraction (litellm)
  - `workspace/service.py` - Git operations & repo mapping
  - `persistence/` - Database models, repositories, migrations
  - `agents/` - Agent orchestration (sub-agents, compaction, summarization)
  - `runtime.py` - Core execution loop
  - `loop.py` - Agent loop with tool calling
  - `loop_detection.py` - Infinite loop detection
  - `coordinator.py` - Multi-agent coordination

### Frontend (TypeScript/React)
- **tui/** - React-based terminal UI
  - `src/components/` - UI components (Input, Display, StatusBar, etc.)
  - `src/services/` - Transport layer, providers, state management
  - `src/hooks/` - Custom hooks (useScenario, useAutocomplete)
  - `src/App.tsx` - Main application entry

### Key Features
- Scenario-based agent workflows (captain-crewmate pattern)
- Real-time LLM streaming via WebSockets
- Tool execution with risk level classification
- Workspace awareness (git integration, repo maps)
- Memory management with summarization
- Session persistence with SQLite
- Multi-provider support via litellm
- Compact/TUI-optimized display with ANSI handling

## Technology Stack
- **Backend**: Python 3.11+, FastAPI, litellm, SQLite, websockets
- **Frontend**: React, TypeScript, Ink (TUI framework)
- **Protocol**: JSON-RPC over WebSocket
- **Providers**: OpenAI, Anthropic, Google, OpenRouter, custom adapters

## Development
- See `server/tests/` for backend test suite
- See `tui/` for frontend components
- Configuration via `.env.example` and `pyproject.toml`
