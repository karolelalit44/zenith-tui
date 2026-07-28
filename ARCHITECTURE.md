# Zenith Architecture

Service-oriented, event-driven architecture for the Zenith AI coding assistant.

## Layer Structure

```
Level 0 (Foundation):   core/         — Domain types, events, messages, sessions, errors
Level 1 (Services):     config/       — Configuration management
                        session/      — Session CRUD and state
                        permission/   — Permission grants
                        workspace/    — Git, repo map, context
Level 2 (Providers):    providers/    — LLM abstraction, registry, retry
Level 3 (Tools):        tools/        — Tool execution, middleware chain
Level 4 (Agent):        agent/        — Runtime, coordinator, templates, loop detection
Level 5 (Transport):    transport/    — JSON-RPC protocol, WebSocket, FastAPI
Level 6 (Application):  app.py        — DI container
                        main.py       — CLI entry
```

## Key Interfaces

| Interface | Location | Purpose |
|-----------|----------|---------|
| `ConfigLoader` | `config/loader.py` | Provider credentials, app settings, env variables |
| `SessionService` | `session/service.py` | Session lifecycle, message tracking |
| `PermissionService` | `permission/service.py` | Request/grant/deny permissions |
| `WorkspaceService` | `workspace/service.py` | Git, tracker, repo map, context |
| `ProviderService` | `providers/base.py` | Typed LLM completion + streaming |
| `AgentRuntime` | `agent/runtime.py` | Multi-step prompt → LLM → tools loop |
| `CoordinatorService` | `agent/coordinator.py` | Orchestrate sessions + agents |
| `TransportService` | `transport/protocol.py` | Connection management + broadcast |
| `ToolMiddleware` | `tools/base.py` | Cross-cutting tool concerns |

## Middleware Chain

Tools execute through ordered middleware:

```
before_execute → Tool.execute → after_execute
                    ↓ (on error)
              on_error (recovery)
```

Built-in middleware: SafetyCheck → Validation → Permission → Logging

## Event System

`AsyncEventBus` provides typed pub/sub with delivery modes (lossy, blocking, persistent).
Events flow: AgentLoop → EventBus → TransportService → WebSocket clients.

## DI Container

`AppContainer` wires all services in `app.py`:
```python
container = AppContainer.create(config)
await container.start()   # connects DB, creates repos
await container.stop()    # closes DB
```
