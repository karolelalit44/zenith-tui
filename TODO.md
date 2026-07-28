# Zenith Architecture RFC: Production-Ready Target Architecture

## Current Status

### Phase 1: 24-Task Improvement Roadmap ✅ COMPLETE
All 24 tasks completed (12 implemented, 6 cancelled, 6 deferred then implemented):
- #1 Git context, #2 XML prompt, #3 Few-shot examples, #4 Context files
- #5 Loop detection, #6 Background jobs, #7 Tree-sitter repo map
- #8 SQLite sessions, #9 LSP integration, #10 Auto-lint
- #11 Background summarization, #12 Streaming bash, #13 Multi-edit
- #14 Question tool, #15 MCP client, #16 Sub-agent
- #17 Cancel-on-entry, #18 Prompt caching, #19 Banned commands
- #20 Todo tool, #21 File tracking, #22 Auto-commit
- #23 Provider prefixes, #24 Semantic rename via LSP

Tool count expanded: 8 → 17 (bash, file_read, file_write, file_edit, file_delete, glob, grep, webfetch, job_output, job_kill, multi_edit, question, todo, lsp_diagnostics, lsp_definition, lsp_rename, agent)

### Phase 2: Architecture Audit ✅ COMPLETE
100 findings identified and addressed through architecture overhaul.

### Phase 3: Architecture Design + Implementation ✅ COMPLETE
All 9 implementation phases done. 248 tests passing.

#### What Was Built
| Layer | Files | Status |
|-------|-------|--------|
| core/ | domain.py, events.py, message.py, session.py, errors.py | ✅ |
| config/ | service.py ~~(deleted)~~, feature_flags.py ~~(deleted)~~ | ✅ → now just settings.py, loader.py, providers.py, env.py |
| session/ | service.py (SessionService + DefaultSessionService) | ✅ |
| permission/ | service.py, ~~grants.py (deleted)~~ | ✅ → now just service.py |
| workspace/ | service.py (WorkspaceService + DefaultWorkspaceService) | ✅ |
| providers/ | base.py, llm_provider.py, registry.py, retry.py | ✅ |
| tools/ | base.py, registry.py, middleware/{safety,permission,validation,logging_mw}.py | ✅ |
| agent/ | templates.py, runtime.py, coordinator.py, validation.py, llm_stream.py, tool_executor.py | ✅ |
| transport/ | protocol.py, websocket.py, handlers.py, prompt.py | ✅ |
| app.py | AppContainer (DI wiring) | ✅ |
| main.py | CLI (serve, status, tools) | ✅ |
| frontend/ | App.tsx (169 lines), OverlayRouter, WelcomeView | ✅ |
| tests/ | 248 tests (163 original + 85 new) | ✅ |
| docs/ | ARCHITECTURE.md | ✅ |

#### Refactoring Complete
- `agent/loop.py`: 767 → 231 lines (70% reduction) — extracted to validation.py, llm_stream.py, tool_executor.py
- `transport/websocket.py`: 462 → 101 lines (78% reduction) — extracted to handlers.py, prompt.py
- `App.tsx`: 336 → 169 lines (50% reduction) — extracted to OverlayRouter.tsx, WelcomeView.tsx
# Zenith Architecture RFC: Production-Ready Target Architecture

## Current Status

### Phase 1: 24-Task Improvement Roadmap ✅ COMPLETE
All 24 tasks completed (12 implemented, 6 cancelled, 6 deferred then implemented):
- #1 Git context, #2 XML prompt, #3 Few-shot examples, #4 Context files
- #5 Loop detection, #6 Background jobs, #7 Tree-sitter repo map
- #8 SQLite sessions, #9 LSP integration, #10 Auto-lint
- #11 Background summarization, #12 Streaming bash, #13 Multi-edit
- #14 Question tool, #15 MCP client, #16 Sub-agent
- #17 Cancel-on-entry, #18 Prompt caching, #19 Banned commands
- #20 Todo tool, #21 File tracking, #22 Auto-commit
- #23 Provider prefixes, #24 Semantic rename via LSP

Tool count expanded: 8 → 17 (bash, file_read, file_write, file_edit, file_delete, glob, grep, webfetch, job_output, job_kill, multi_edit, question, todo, lsp_diagnostics, lsp_definition, lsp_rename, agent)

### Phase 2: Architecture Audit ✅ COMPLETE
100 findings identified and addressed through architecture overhaul.

### Phase 3: Architecture Design + Implementation ✅ COMPLETE
All 9 implementation phases done. 248 tests passing.

#### What Was Built
| Layer | Files | Status |
|-------|-------|--------|
| core/ | domain.py, events.py, message.py, session.py, errors.py | ✅ |
| config/ | service.py ~~(deleted)~~, feature_flags.py ~~(deleted)~~ | ✅ → now just settings.py, loader.py, providers.py, env.py |
| session/ | service.py (SessionService + DefaultSessionService) | ✅ |
| permission/ | service.py, ~~grants.py (deleted)~~ | ✅ → now just service.py |
| workspace/ | service.py (WorkspaceService + DefaultWorkspaceService) | ✅ |
| providers/ | base.py, llm_provider.py, registry.py, retry.py | ✅ |
| tools/ | base.py, registry.py, middleware/{safety,permission,validation,logging_mw}.py | ✅ |
| agent/ | templates.py, runtime.py, coordinator.py, validation.py, llm_stream.py, tool_executor.py | ✅ |
| transport/ | protocol.py, websocket.py, handlers.py, prompt.py | ✅ |
| app.py | AppContainer (DI wiring) | ✅ |
| main.py | CLI (serve, status, tools) | ✅ |
| frontend/ | App.tsx (169 lines), OverlayRouter, WelcomeView | ✅ |
| tests/ | 248 tests (163 original + 85 new) | ✅ |
| docs/ | ARCHITECTURE.md | ✅ |

#### Refactoring Complete
- `agent/loop.py`: 767 → 231 lines (70% reduction) — extracted to validation.py, llm_stream.py, tool_executor.py
- `transport/websocket.py`: 462 → 101 lines (78% reduction) — extracted to handlers.py, prompt.py
- `App.tsx`: 336 → 169 lines (50% reduction) — extracted to OverlayRouter.tsx, WelcomeView.tsx

#### Frontend Tasks ✅ COMPLETE
- ✅ Frontend: Created `src/services/eventBus.ts` — typed pub/sub event bus
- ✅ Frontend: Created `src/context/useStore.tsx` — centralized state management
- ✅ Frontend: Simplified `src/hooks/useScenario.ts` (150→118 lines)
- ✅ Frontend: Added reconnect strategy to `WebSocketClient.ts` (jitter + max delay cap)
- ✅ Performance benchmarking — `src/services/perf.ts` utility created

---

### Phase 4: Repository Consolidation + Architecture Audit ✅ COMPLETE

#### Migration Tasks
- [x] Moved `backend/*` → Root level modules (`agent`, `config`, `core`, `db`, `lsp`, `mcp`, `permission`, `providers`, `session`, `skills`, `tools`, `transport`, `workspace`)
- [x] Bulk renamed imports and packages in `pyproject.toml`
- [x] Updated `tsconfig.json` and build scripts
- [x] Fixed `ProviderRepository.ts` import path
- [x] Updated `.gitignore` for `data/*` runtime storage
- [x] Cleaned stale runtime files from root/data
- [x] Verified Python package installation (`zenith = "main:cli"`)
- [x] Verified TypeScript typecheck (`tsc --noEmit`) — 0 errors
- [x] Verified Python test suite (`pytest`) — 248/248 passed
- [x] Verified TypeScript test suite (`vitest`) — 70/70 passed
- [x] Fixed 2 pre-existing test failures (`App.test.tsx` and `backendScenarioProvider.test.ts`)

#### Dead Code Removal
- [x] Deleted `config/feature_flags.py` (95 lines, never used)
- [x] Deleted `permission/grants.py` (135 lines, never imported)
- [x] Deleted `config/service.py` (363 lines, duplicate ToolConfig, unused ConfigService)
- [x] Cleaned duplicate ToolConfig definitions

#### Data Organization
- [x] Created `data/` directory for runtime data (`data/.gitkeep`)
- [x] Updated DB path defaults (`ZENITH_DB_PATH` → `data/zenith.db`)

#### Architecture Fixes
- [x] Eliminated raw `sqlite3.connect()` calls — route through `Database` connection class
- [x] Decoupled transport RPC handlers (`transport/handlers.py` and `transport/prompt.py`)
- [x] Refactored `app.py` dependency injection container

#### Documentation & Deliverables
- [x] Updated `ARCHITECTURE.md` to reflect new consolidated structure
- [x] Generated comprehensive Architecture Audit & Refactoring Artifact

#### Validation
- [x] Full build + test + runtime verification (318 total automated tests passing)

---

## 1. Executive Summary

This RFC defines the target architecture for Zenith, addressing 100 findings from the architecture audit. The design transforms Zenith from a monolithic structure with god objects into a modular, event-driven system supporting 500+ tools, multiple LLM providers, concurrent agents, background tasks, workflows, plugins, MCP servers, and long-running sessions.

**Key Design Principles:**
- **Service-oriented**: Each domain has a clear Service interface
- **Event-driven**: Decoupled components via pub/sub event bus
- **Middleware-based**: Tool execution through composable middleware chain
- **Dependency injection**: No singletons, explicit dependency wiring
- **Protocol-first**: Shared JSON-RPC contract between frontend/backend
- **Testable**: Every component mockable and independently testable

---

## 2. Architectural Domains

### 2.1 Domain Map

```
┌─────────────────────────────────────────────────────────────────────┐
│                          TRANSPORT DOMAIN                           │
│  WebSocket Server • JSON-RPC Dispatch • Protocol Definitions       │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          COORDINATOR DOMAIN                         │
│  Session Management • Provider Selection • Agent Lifecycle          │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                ┌───────────────────┼───────────────────┐
                ▼                   ▼                   ▼
┌───────────────────────┐ ┌───────────────────────┐ ┌───────────────────────┐
│     AGENT DOMAIN      │ │   PROVIDER DOMAIN     │ │    TOOL DOMAIN        │
│  Prompt Building      │ │  LLM Abstraction      │ │  Registry             │
│  Context Management   │ │  Token Counting       │ │  Middleware Chain      │
│  Stream Processing    │ │  Retry Logic          │ │  Schema Generation    │
│  Loop Detection       │ │  Model Selection      │ │  Mode Enforcement     │
└───────────────────────┘ └───────────────────────┘ └───────────────────────┘
                │                   │                   │
                ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          EVENT BUS DOMAIN                           │
│  Pub/Sub Broker • Event Persistence • Fan-Out • Observability       │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                ┌───────────────────┼───────────────────┐
                ▼                   ▼                   ▼
┌───────────────────────┐ ┌───────────────────────┐ ┌───────────────────────┐
│  PERMISSION DOMAIN    │ │   SESSION DOMAIN      │ │  WORKSPACE DOMAIN     │
│  Request/Grant/Deny   │ │  History Management   │ │  Git Operations       │
│  Persistent Grants    │ │  Summarization        │ │  File Tracking        │
│  Hook Integration     │ │  Export               │ │  Repo Map             │
└───────────────────────┘ └───────────────────────┘ └───────────────────────┘
                │                   │                   │
                ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          CONFIG DOMAIN                              │
│  Settings Service • Provider Catalog • Environment Variables        │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Domain Boundaries

| Domain | Backend Modules | Frontend Modules | Shared Contract |
|--------|----------------|------------------|-----------------|
| **Transport** | `transport/` | `services/backend/` | JSON-RPC methods |
| **Coordinator** | `agent/coordinator.py` | `hooks/useScenario.ts` | Session/Prompt events |
| **Agent** | `agent/` | N/A | Event stream |
| **Provider** | `providers/` | `services/providers/` | Provider config |
| **Tool** | `tools/` | N/A | Tool schema |
| **Event Bus** | `core/events.py` | `services/eventBus.ts` | Event types |
| **Permission** | `permission/` | `components/ConfirmationCard.tsx` | Permission request |
| **Session** | `session/` | `hooks/useConversation.ts` | Session data |
| **Workspace** | `workspace/` | `services/fileExplorerService.ts` | Git/Files |
| **Config** | `config/` | `services/providers/ProviderRepository.ts` | Settings |

---

## 3. Core Interfaces

### 3.1 Transport Domain

```python
# zenith/transport/protocol.py

class JsonRpcMethod(str, Enum):
    # Session methods
    SESSION_CREATE = "session.create"
    SESSION_LIST = "session.list"
    SESSION_RESUME = "session.resume"
    SESSION_EXPORT = "session.export"
    
    # Prompt methods
    PROMPT_SEND = "prompt.send"
    PROMPT_CANCEL = "prompt.cancel"
    
    # Provider methods
    PROVIDER_VALIDATE = "provider.validate"
    PROVIDER_MODELS = "provider.models"
    PROVIDER_LIST = "provider.list"
    
    # Tool methods
    TOOLS_LIST = "tools.list"
    
    # Workspace methods
    WORKSPACE_STATUS = "workspace.status"
    WORKSPACE_DIFF = "workspace.diff"
    WORKSPACE_LOG = "workspace.log"
    WORKSPACE_REPO_MAP = "workspace.repo_map"
    
    # Permission methods
    PERMISSION_RESPONSE = "permission.response"
    
    # Health
    HEALTH = "health"

class TransportService(ABC):
    @abstractmethod
    async def start(self, host: str, port: int) -> None: ...
    
    @abstractmethod
    async def stop(self) -> None: ...
    
    @abstractmethod
    async def broadcast(self, event: Event) -> None: ...
    
    @abstractmethod
    def get_connections(self) -> list[Connection]: ...
```

### 3.2 Coordinator Domain

```python
# zenith/agent/coordinator.py

class AgentRole(str, Enum):
    CODER = "coder"
    TASK = "task"
    REVIEWER = "reviewer"

class CoordinatorService(ABC):
    @abstractmethod
    async def create_session(self, title: str | None = None) -> Session: ...
    
    @abstractmethod
    async def list_sessions(self) -> list[Session]: ...
    
    @abstractmethod
    async def resume_session(self, session_id: str) -> Session: ...
    
    @abstractmethod
    async def handle_prompt(
        self, 
        session_id: str, 
        prompt: str, 
        mode: ScenarioMode,
        role: AgentRole = AgentRole.CODER
    ) -> AsyncIterator[Event]: ...
    
    @abstractmethod
    def cancel_current(self) -> None: ...
    
    @abstractmethod
    async def spawn_agent(
        self, 
        parent_session_id: str,
        role: AgentRole,
        config: AgentConfig
    ) -> str: ...  # returns child session_id
    
    @abstractmethod
    async def get_agent_status(self, session_id: str) -> AgentStatus: ...
```

### 3.3 Agent Domain

```python
# zenith/agent/runtime.py

class AgentRuntime(ABC):
    @abstractmethod
    async def process_prompt(
        self,
        prompt: str,
        session: Session,
        history: list[Message],
        tools: ToolExecutor,
        provider: ProviderService,
        config: ConfigService
    ) -> AsyncIterator[Event]: ...
    
    @abstractmethod
    def cancel(self) -> None: ...
    
    @abstractmethod
    def get_state(self) -> AgentState: ...

class PromptBuilder(ABC):
    @abstractmethod
    async def build_system_prompt(
        self,
        role: AgentRole,
        workspace_root: Path,
        context_files: list[Path],
        config: ConfigService
    ) -> str: ...
    
    @abstractmethod
    async def build_user_prompt(
        self,
        prompt: str,
        repo_map: str | None,
        file_context: list[Path]
    ) -> str: ...

class ContextManager(ABC):
    @abstractmethod
    async def fit_to_budget(
        self,
        messages: list[Message],
        budget_tokens: int,
        preserve_system: bool = True
    ) -> list[Message]: ...
    
    @abstractmethod
    def get_summary(self) -> str | None: ...
    
    @abstractmethod
    def get_dropped_messages(self) -> list[Message]: ...
```

### 3.4 Provider Domain

```python
# zenith/providers/base.py

class ProviderService(ABC):
    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        model: str,
        tools: list[ToolSchema] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None
    ) -> ProviderResponse: ...
    
    @abstractmethod
    async def stream(
        self,
        messages: list[Message],
        model: str,
        tools: list[ToolSchema] | None = None
    ) -> AsyncIterator[ProviderChunk]: ...
    
    @abstractmethod
    async def validate_config(self, config: ProviderConfig) -> ValidationResult: ...
    
    @abstractmethod
    async def list_models(self, provider: str | None = None) -> list[ModelInfo]: ...
    
    @abstractmethod
    def count_tokens(self, messages: list[Message], model: str) -> int: ...

class ProviderResponse(BaseModel):
    content: str | None
    tool_calls: list[ToolCall]
    usage: TokenUsage
    finish_reason: FinishReason
    cached: bool = False

class ProviderChunk(BaseModel):
    delta: str | None
    tool_call_delta: ToolCallDelta | None
    usage: TokenUsage | None
```

### 3.5 Tool Domain

```python
# zenith/tools/base.py

class ToolMiddleware(ABC):
    @abstractmethod
    async def before_execute(
        self, 
        tool_name: str, 
        params: dict[str, Any],
        context: ToolContext
    ) -> ToolMiddlewareDecision: ...
    
    @abstractmethod
    async def after_execute(
        self,
        tool_name: str,
        params: dict[str, Any],
        result: ToolResult,
        context: ToolContext
    ) -> ToolResult: ...

class ToolMiddlewareDecision(BaseModel):
    allow: bool
    reason: str | None = None
    modified_params: dict[str, Any] | None = None
    modified_result: ToolResult | None = None

class ToolContext(BaseModel):
    session_id: str
    workspace_root: Path
    mode: ScenarioMode
    agent_role: AgentRole
    permissions: PermissionService

class ToolExecutor(ABC):
    @abstractmethod
    def add_middleware(self, middleware: ToolMiddleware, priority: int = 0) -> None: ...
    
    @abstractmethod
    def remove_middleware(self, middleware: ToolMiddleware) -> None: ...
    
    @abstractmethod
    async def execute(
        self,
        tool_name: str,
        params: dict[str, Any],
        context: ToolContext
    ) -> ToolResult: ...
    
    @abstractmethod
    def get_schema(self, tool_name: str) -> ToolSchema: ...
    
    @abstractmethod
    def list_schemas(self, mode: ScenarioMode | None = None) -> list[ToolSchema]: ...

class BaseTool(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...
    
    @property
    @abstractmethod
    def description(self) -> str: ...
    
    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]: ...
    
    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW
    
    @property
    def modes(self) -> list[ScenarioMode]:
        return [ScenarioMode.BUILD, ScenarioMode.PLAN]
    
    @abstractmethod
    async def execute(
        self, 
        params: dict[str, Any], 
        context: ToolContext
    ) -> ToolResult: ...
    
    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=self.parameters
        )
```

### 3.6 Event Bus Domain

```python
# zenith/core/events.py

class DeliveryMode(Enum):
    LOSSY = "lossy"           # Drop if buffer full (default)
    BLOCKING = "blocking"     # Block until delivered
    PERSISTENT = "persistent" # Store and deliver later

class EventBus(ABC):
    @abstractmethod
    def publish(
        self, 
        event: Event, 
        mode: DeliveryMode = DeliveryMode.LOSSY
    ) -> None: ...
    
    @abstractmethod
    def subscribe(
        self, 
        event_type: EventKind | None = None,
        session_id: str | None = None
    ) -> AsyncIterator[Event]: ...
    
    @abstractmethod
    def unsubscribe(self, subscription_id: str) -> None: ...
    
    @abstractmethod
    async def get_persistent_events(
        self, 
        session_id: str,
        since: datetime | None = None
    ) -> list[Event]: ...

class Event(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    kind: EventKind
    session_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
    data: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### 3.7 Permission Domain

```python
# zenith/permission/service.py

class PermissionDecision(Enum):
    ALLOW = "allow"
    DENY = "deny"
    PERSISTENT_ALLOW = "persistent_allow"
    PERSISTENT_DENY = "persistent_deny"

class PermissionRequest(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tool_name: str
    description: str
    risk_level: RiskLevel
    params: dict[str, Any]
    session_id: str
    timestamp: datetime = Field(default_factory=datetime.now)

class PermissionGrant(BaseModel):
    tool_name: str
    decision: PermissionDecision
    expires_at: datetime | None = None
    session_id: str | None = None  # None = global

class PermissionService(ABC):
    @abstractmethod
    async def request(
        self,
        tool_name: str,
        description: str,
        risk_level: RiskLevel,
        params: dict[str, Any],
        session_id: str
    ) -> PermissionDecision: ...
    
    @abstractmethod
    def grant_persistent(
        self,
        tool_name: str,
        decision: PermissionDecision,
        session_id: str | None = None
    ) -> None: ...
    
    @abstractmethod
    def revoke_persistent(self, tool_name: str) -> None: ...
    
    @abstractmethod
    def get_grants(self, session_id: str) -> list[PermissionGrant]: ...
    
    @abstractmethod
    def clear_session(self, session_id: str) -> None: ...
```

### 3.8 Session Domain

```python
# zenith/session/service.py

class SessionService(ABC):
    @abstractmethod
    async def create(self, title: str | None = None) -> Session: ...
    
    @abstractmethod
    async def get(self, session_id: str) -> Session | None: ...
    
    @abstractmethod
    async def list_active(self) -> list[Session]: ...
    
    @abstractmethod
    async def add_message(
        self, 
        session_id: str, 
        message: Message
    ) -> None: ...
    
    @abstractmethod
    async def get_history(
        self, 
        session_id: str,
        limit: int | None = None
    ) -> list[Message]: ...
    
    @abstractmethod
    async def summarize(
        self, 
        session_id: str,
        max_tokens: int = 4000
    ) -> str: ...
    
    @abstractmethod
    async def export_markdown(
        self, 
        session_id: str
    ) -> str: ...
    
    @abstractmethod
    async def delete(self, session_id: str) -> None: ...
```

### 3.9 Workspace Domain

```python
# zenith/workspace/service.py

class WorkspaceService(ABC):
    @abstractmethod
    async def get_git_status(self) -> GitStatus: ...
    
    @abstractmethod
    async def get_diff(self, ref: str | None = None) -> str: ...
    
    @abstractmethod
    async def get_log(self, limit: int = 10) -> list[GitCommit]: ...
    
    @abstractmethod
    async def commit(self, message: str, files: list[Path] | None = None) -> str: ...
    
    @abstractmethod
    async def get_repo_map(self, max_tokens: int = 1000) -> str: ...
    
    @abstractmethod
    def track_file(self, path: Path) -> None: ...
    
    @abstractmethod
    def get_tracked_files(self) -> list[Path]: ...
    
    @abstractmethod
    def get_file_history(self, path: Path) -> list[FileVersion]: ...
    
    @abstractmethod
    async def get_context_files(self) -> list[Path]: ...
    
    @abstractmethod
    async def run_linter(
        self, 
        file_path: Path,
        linter: str | None = None
    ) -> LintResult: ...
```

### 3.10 Config Domain

```python
# zenith/config/service.py

class ConfigService(ABC):
    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any: ...
    
    @abstractmethod
    def set(self, key: str, value: Any) -> None: ...
    
    @abstractmethod
    def subscribe(
        self, 
        key: str | None = None,
        callback: Callable[[str, Any, Any], None] | None = None
    ) -> Callable[[], None]: ...  # returns unsubscribe function
    
    @abstractmethod
    async def validate(self) -> ValidationResult: ...
    
    @property
    @abstractmethod
    def active_provider(self) -> ProviderConfig: ...
    
    @property
    @abstractmethod
    def workspace_root(self) -> Path: ...
    
    @property
    @abstractmethod
    def models(self) -> list[ModelInfo]: ...
```

---

## 4. Execution Flow

### 4.1 Prompt Processing Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CLIENT (Frontend)                           │
│  User Input → useScenario.sendPrompt() → WebSocketClient.send()    │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ JSON-RPC: prompt.send
┌─────────────────────────────────────────────────────────────────────┐
│                    TRANSPORT DOMAIN (WebSocket)                     │
│  ZenithHandler.handle_prompt() → CoordinatorService.handle_prompt()│
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    COORDINATOR DOMAIN                                │
│  1. Validate session exists                                         │
│  2. Get/create agent for session                                    │
│  3. Load history from SessionService                                │
│  4. Build context from WorkspaceService                             │
│  5. Call AgentRuntime.process_prompt()                              │
│  6. Stream events to EventBus                                       │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    AGENT DOMAIN (AgentRuntime)                      │
│  1. PromptBuilder.build_system_prompt()                             │
│  2. PromptBuilder.build_user_prompt()                               │
│  3. ContextManager.fit_to_budget()                                  │
│  4. LoopDetector.check()                                            │
│  5. ProviderService.stream() → AsyncIterator[ProviderChunk]         │
│  6. For each chunk:                                                 │
│     a. If content → publish EventKind.THINKING                      │
│     b. If tool_call → ToolExecutor.execute()                        │
│        └── Middleware chain: before → execute → after                │
│     c. If error → publish EventKind.ERROR                           │
│     d. Check LoopDetector → break if loop detected                  │
│  7. Publish EventKind.SUCCESS or EventKind.ERROR                    │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    TOOL DOMAIN (ToolExecutor)                       │
│  Middleware Chain:                                                  │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐            │
│  │ SafetyCheck  │ → │ Permission   │ → │ Tool.execute │            │
│  │ Middleware   │   │ Middleware   │   │              │            │
│  └──────────────┘   └──────────────┘   └──────────────┘            │
│         │                   │                   │                   │
│         ▼                   ▼                   ▼                   │
│  CommandSafety    PermissionService    ToolRegistry.get()           │
│  .assess_risk()   .request()           .execute()                   │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    EVENT BUS DOMAIN                                  │
│  EventBus.publish(event, DeliveryMode.LOSSY)                        │
│  ├── Subscribers: TransportService (→ WebSocket broadcast)          │
│  ├── Subscribers: SessionService (→ persist to DB)                  │
│  └── Subscribers: ObservabilityService (→ logs/metrics)             │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ JSON-RPC: event notification
┌─────────────────────────────────────────────────────────────────────┐
│                         CLIENT (Frontend)                           │
│  WebSocketClient.onMessage() → BackendScenarioProvider.mapEvent()   │
│  → useConversation.addEvent() → ScenarioRenderer.render()          │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.2 Permission Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                    TOOL EXECUTION (in ToolExecutor)                  │
│  ToolMiddleware.before_execute() called                             │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    PERMISSION MIDDLEWARE                             │
│  1. Check if tool requires permission (risk_level > LOW)            │
│  2. Check PermissionService.get_grants() for existing grant         │
│  3. If no grant → PermissionService.request()                       │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    PERMISSION SERVICE                               │
│  1. Check persistent grants (session-level or global)               │
│  2. If no persistent grant → Publish EventKind.CONFIRMATION         │
│  3. Wait for user response (with timeout)                           │
│  4. Return PermissionDecision                                       │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ EventKind.CONFIRMATION
┌─────────────────────────────────────────────────────────────────────┐
│                         CLIENT (Frontend)                           │
│  ConfirmationCard renders with Approve/Deny buttons                 │
│  User clicks → permission.response JSON-RPC call                    │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ JSON-RPC: permission.response
┌─────────────────────────────────────────────────────────────────────┐
│                    PERMISSION SERVICE                               │
│  1. Receive response                                               │
│  2. Optionally grant_persistent() if "remember" checked             │
│  3. Return PermissionDecision to ToolMiddleware                     │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    TOOL EXECUTION CONTINUES                         │
│  If ALLOW → Tool.execute()                                          │
│  If DENY → Return ToolResult with error message                    │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.3 Sub-Agent Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                    PARENT AGENT (AgentRuntime)                      │
│  ToolExecutor.execute("agent", {task: "...", role: "task"})         │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    AGENT TOOL MIDDLEWARE                             │
│  1. CoordinatorService.spawn_agent()                                │
│  2. Create child session with parent_session_id                     │
│  3. Create child AgentRuntime with role="task"                      │
│  4. Return child_session_id immediately                             │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ (background)
┌─────────────────────────────────────────────────────────────────────┐
│                    CHILD AGENT (AgentRuntime)                       │
│  1. Process prompt in background                                    │
│  2. Publish events to EventBus with child_session_id                │
│  3. When complete → Publish EventKind.AGENT_COMPLETE                │
│  4. Parent can check status via CoordinatorService.get_agent_status()│
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ EventKind.AGENT_COMPLETE
┌─────────────────────────────────────────────────────────────────────┐
│                    PARENT AGENT                                     │
│  ToolResult contains child_session_id and status                    │
│  Parent can:                                                        │
│  - Continue with child's results                                    │
│  - Spawn another child                                              │
│  - Wait for child to complete                                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 5. Event Architecture

### 5.1 Event Kinds

```python
class EventKind(str, Enum):
    # Core events
    THINKING = "thinking"           # LLM content stream
    TOOL_CALL = "tool_call"         # Tool invocation started
    TOOL_RESULT = "tool_result"     # Tool execution completed
    ERROR = "error"                 # Error occurred
    WARNING = "warning"             # Warning message
    SUCCESS = "success"             # Task completed successfully
    
    # Confirmation events
    CONFIRMATION = "confirmation"   # Permission request
    CONFIRMATION_RESPONSE = "confirmation_response"  # User response
    
    # Progress events
    PROGRESS = "progress"           # Progress bar/update
    
    # Agent events
    AGENT_SPAWNED = "agent_spawned"     # Sub-agent created
    AGENT_COMPLETE = "agent_complete"   # Sub-agent finished
    AGENT_FAILED = "agent_failed"       # Sub-agent failed
    
    # Session events
    SESSION_CREATED = "session_created"
    SESSION_RESUMED = "session_resumed"
    SESSION_SUMMARIZED = "session_summarized"
    
    # Provider events
    PROVIDER_SWITCHED = "provider_switched"
    PROVIDER_ERROR = "provider_error"
    
    # System events
    SYSTEM_READY = "system_ready"
    SYSTEM_SHUTDOWN = "system_shutdown"
```

### 5.2 Event Schema

```python
class Event(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    kind: EventKind
    session_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
    
    # Content fields (varies by kind)
    content: str | None = None              # For THINKING
    tool_name: str | None = None            # For TOOL_CALL, TOOL_RESULT
    tool_params: dict[str, Any] | None = None  # For TOOL_CALL
    tool_result: ToolResult | None = None   # For TOOL_RESULT
    error: ErrorDetail | None = None        # For ERROR
    confirmation_id: str | None = None      # For CONFIRMATION
    progress: ProgressDetail | None = None  # For PROGRESS
    agent_session_id: str | None = None     # For AGENT_*
    
    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict)
    parent_event_id: str | None = None      # For correlated events
```

### 5.3 Event Flow Diagram

```
AgentRuntime                EventBus               TransportService
     │                          │                          │
     │── publish(THINKING) ────▶│                          │
     │                          │── broadcast() ──────────▶│── WebSocket
     │                          │                          │
     │── publish(TOOL_CALL) ───▶│                          │
     │                          │── broadcast() ──────────▶│── WebSocket
     │                          │                          │
     │── publish(TOOL_RESULT) ─▶│                          │
     │                          │── broadcast() ──────────▶│── WebSocket
     │                          │                          │
     │── publish(SUCCESS) ─────▶│                          │
     │                          │── broadcast() ──────────▶│── WebSocket
     │                          │                          │
     │                          │── persist() ────────────▶│── SQLite
```

---

## 6. State Model

### 6.1 Agent State Machine

```
┌─────────────────────────────────────────────────────────────────────┐
│                         AGENT STATES                                │
└─────────────────────────────────────────────────────────────────────┘

                          ┌──────────────┐
                          │    IDLE      │
                          └──────┬───────┘
                                 │ process_prompt()
                                 ▼
                          ┌──────────────┐
                          │  PROCESSING  │
                          └──────┬───────┘
                                 │
                 ┌───────────────┼───────────────┐
                 │               │               │
                 ▼               ▼               ▼
          ┌────────────┐  ┌────────────┐  ┌────────────┐
          │  STREAMING │  │ TOOL_CALL  │  │  WAITING   │
          │  (LLM)     │  │            │  │ (Permission│
          └─────┬──────┘  └─────┬──────┘  └─────┬──────┘
                │               │               │
                └───────────────┼───────────────┘
                                │
                                ▼
                         ┌──────────────┐
                         │  COMPLETED   │
                         └──────────────┘

Transitions:
- IDLE → PROCESSING: User sends prompt
- PROCESSING → STREAMING: LLM starts generating
- STREAMING → TOOL_CALL: LLM requests tool use
- TOOL_CALL → STREAMING: Tool completes, LLM continues
- PROCESSING → WAITING: Tool requires permission
- WAITING → TOOL_CALL: Permission granted
- WAITING → IDLE: Permission denied
- STREAMING → COMPLETED: LLM finishes
- TOOL_CALL → COMPLETED: Final tool completes
- Any → IDLE: Cancel requested
- Any → COMPLETED (error): Error occurred
```

### 6.2 Session State Machine

```
┌─────────────────────────────────────────────────────────────────────┐
│                         SESSION STATES                              │
└─────────────────────────────────────────────────────────────────────┘

                          ┌──────────────┐
                          │   CREATED    │
                          └──────┬───────┘
                                 │ first prompt
                                 ▼
                          ┌──────────────┐
                          │   ACTIVE     │
                          └──────┬───────┘
                                 │
                 ┌───────────────┼───────────────┐
                 │               │               │
                 ▼               ▼               ▼
          ┌────────────┐  ┌────────────┐  ┌────────────┐
          │  RESUMED   │  │ SUMMARIZED │  │  EXPORTED  │
          └─────┬──────┘  └─────┬──────┘  └─────┬──────┘
                │               │               │
                └───────────────┼───────────────┘
                                │
                                ▼
                         ┌──────────────┐
                         │   ARCHIVED   │
                         └──────────────┘

Transitions:
- CREATED → ACTIVE: First prompt sent
- ACTIVE → ACTIVE: More prompts
- ACTIVE → SUMMARIZED: History too long
- ACTIVE → EXPORTED: User exports
- SUMMARIZED → RESUMED: User resumes
- RESUMED → ACTIVE: More prompts
- Any → ARCHIVED: User deletes
```

### 6.3 LSP State Machine

```
┌─────────────────────────────────────────────────────────────────────┐
│                          LSP STATES                                 │
└─────────────────────────────────────────────────────────────────────┘

                          ┌──────────────┐
                          │  DISCONNECTED│
                          └──────┬───────┘
                                 │ start()
                                 ▼
                          ┌──────────────┐
                          │  STARTING    │
                          └──────┬───────┘
                                 │ initialized
                                 ▼
                          ┌──────────────┐
                          │   RUNNING    │◀──────────────┐
                          └──────┬───────┘               │
                                 │                       │
                 ┌───────────────┼───────────────┐       │
                 │               │               │       │
                 ▼               ▼               ▼       │
          ┌────────────┐  ┌────────────┐  ┌────────────┐│
          │  RESTARTING│  │  STOPPING   │  │  ERROR     ││
          └─────┬──────┘  └─────┬──────┘  └─────┬──────┘│
                │               │               │       │
                └───────────────┼───────────────┘       │
                                │                       │
                                ▼                       │
                         ┌──────────────┐               │
                         │  DISCONNECTED│───────────────┘
                         └──────────────┘

Transitions:
- DISCONNECTED → STARTING: start() called
- STARTING → RUNNING: Server initialized
- RUNNING → RESTARTING: Crash detected
- RESTARTING → RUNNING: Restart successful
- RUNNING → STOPPING: stop() called
- STOPPING → DISCONNECTED: Server stopped
- RUNNING → ERROR: Fatal error
- ERROR → RESTARTING: Retry attempted
- ERROR → DISCONNECTED: Max retries exceeded
```

### 6.4 MCP State Machine

```
┌─────────────────────────────────────────────────────────────────────┐
│                          MCP STATES                                 │
└─────────────────────────────────────────────────────────────────────┘

                          ┌──────────────┐
                          │  DISCONNECTED│
                          └──────┬───────┘
                                 │ connect()
                                 ▼
                          ┌──────────────┐
                          │  CONNECTING  │
                          └──────┬───────┘
                                 │ connected
                                 ▼
                          ┌──────────────┐
                          │  HANDSHAKING │
                          └──────┬───────┘
                                 │ initialized
                                 ▼
                          ┌──────────────┐
                          │   RUNNING    │◀──────────────┐
                          └──────┬───────┘               │
                                 │                       │
                 ┌───────────────┼───────────────┐       │
                 │               │               │       │
                 ▼               ▼               ▼       │
          ┌────────────┐  ┌────────────┐  ┌────────────┐│
          │ RECONNECTING│  │  CLOSING   │  │  ERROR     ││
          └─────┬──────┘  └─────┬──────┘  └─────┬──────┘│
                │               │               │       │
                └───────────────┼───────────────┘       │
                                │                       │
                                ▼                       │
                         ┌──────────────┐               │
                         │  DISCONNECTED│───────────────┘
                         └──────────────┘

Transitions:
- DISCONNECTED → CONNECTING: connect() called
- CONNECTING → HANDSHAKING: TCP/WebSocket connected
- HANDSHAKING → RUNNING: MCP initialize handshake complete
- RUNNING → RECONNECTING: Connection lost
- RECONNECTING → RUNNING: Reconnection successful
- RUNNING → CLOSING: close() called
- CLOSING → DISCONNECTED: Connection closed
- RUNNING → ERROR: Protocol error
- ERROR → RECONNECTING: Retry with backoff
- ERROR → DISCONNECTED: Max retries exceeded
```

---

## 7. Tool Runtime Architecture

### 7.1 Middleware Chain

```
┌─────────────────────────────────────────────────────────────────────┐
│                    TOOL EXECUTION PIPELINE                          │
└─────────────────────────────────────────────────────────────────────┘

Request: execute("bash", {"command": "rm -rf /"}, context)
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  MIDDLEWARE 1: SafetyCheckMiddleware (priority=100)                 │
│  - Assess command risk via CommandSafety.assess_risk()              │
│  - If risk > threshold → deny with explanation                     │
│  - If risk == CRITICAL → always deny                               │
└─────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  MIDDLEWARE 2: PermissionMiddleware (priority=90)                   │
│  - Check if tool requires permission (risk_level > LOW)            │
│  - Check existing grants                                           │
│  - If no grant → request via PermissionService                     │
│  - If denied → return error                                        │
└─────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  MIDDLEWARE 3: ValidationMiddleware (priority=80)                   │
│  - Validate parameters against schema                              │
│  - Check file paths exist                                          │
│  - Sanitize inputs                                                 │
└─────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  MIDDLEWARE 4: LoggingMiddleware (priority=70)                      │
│  - Log tool invocation with params                                 │
│  - Start timer                                                     │
│  - Record to EventBus                                              │
└─────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  TOOL EXECUTION                                                    │
│  - ToolRegistry.get("bash").execute(params, context)               │
│  - Returns ToolResult                                              │
└─────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  MIDDLEWARE 4 (after): LoggingMiddleware                            │
│  - Log completion with duration                                    │
│  - Record result to EventBus                                       │
└─────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  MIDDLEWARE 3 (after): ValidationMiddleware                         │
│  - Validate result matches expected schema                         │
└─────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  MIDDLEWARE 2 (after): PermissionMiddleware                         │
│  - No-op (permission already granted)                              │
└─────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  MIDDLEWARE 1 (after): SafetyCheckMiddleware                        │
│  - No-op                                                           │
└─────────────────────────────────────────────────────────────────────┘
    │
    ▼
Result: ToolResult(output="...", success=True)
```

### 7.2 Tool Registration

```python
# zenith/tools/registry.py

class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        self._middleware: list[tuple[int, ToolMiddleware]] = []
        self._sorted = False
    
    def register(self, tool: BaseTool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool
    
    def add_middleware(self, middleware: ToolMiddleware, priority: int = 0) -> None:
        """Add middleware to the chain."""
        self._middleware.append((priority, middleware))
        self._sorted = False
    
    def _sort_middleware(self) -> None:
        """Sort middleware by priority (higher = earlier)."""
        if not self._sorted:
            self._middleware.sort(key=lambda x: x[0], reverse=True)
            self._sorted = True
    
    async def execute(
        self,
        tool_name: str,
        params: dict[str, Any],
        context: ToolContext
    ) -> ToolResult:
        """Execute tool with middleware chain."""
        tool = self._tools.get(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                output=f"Tool '{tool_name}' not found"
            )
        
        self._sort_middleware()
        
        # Before middleware
        current_params = params
        for _, middleware in self._middleware:
            decision = await middleware.before_execute(
                tool_name, current_params, context
            )
            if not decision.allow:
                return ToolResult(
                    success=False,
                    output=decision.reason or "Tool execution denied"
                )
            if decision.modified_params:
                current_params = decision.modified_params
        
        # Execute tool
        result = await tool.execute(current_params, context)
        
        # After middleware (reverse order)
        current_result = result
        for _, middleware in reversed(self._middleware):
            current_result = await middleware.after_execute(
                tool_name, current_params, current_result, context
            )
        
        return current_result
    
    def get_schema(self, tool_name: str) -> ToolSchema | None:
        """Get tool schema."""
        tool = self._tools.get(tool_name)
        return tool.get_schema() if tool else None
    
    def list_schemas(
        self, 
        mode: ScenarioMode | None = None
    ) -> list[ToolSchema]:
        """List all tool schemas, optionally filtered by mode."""
        schemas = []
        for tool in self._tools.values():
            if mode is None or mode in tool.modes:
                schemas.append(tool.get_schema())
        return schemas
```

### 7.3 Built-in Middleware

```python
# zenith/tools/middleware/safety.py

class SafetyCheckMiddleware(ToolMiddleware):
    def __init__(self, config: ConfigService):
        self._config = config
    
    async def before_execute(
        self,
        tool_name: str,
        params: dict[str, Any],
        context: ToolContext
    ) -> ToolMiddlewareDecision:
        """Check tool safety."""
        if tool_name == "bash":
            command = params.get("command", "")
            risk = CommandSafety.assess_risk(command)
            
            if risk == RiskLevel.CRITICAL:
                return ToolMiddlewareDecision(
                    allow=False,
                    reason=f"Critical risk command: {command}"
                )
            
            # Check if command is banned
            if CommandSafety.is_banned(command):
                return ToolMiddlewareDecision(
                    allow=False,
                    reason=f"Banned command: {command}"
                )
        
        return ToolMiddlewareDecision(allow=True)

# zenith/tools/middleware/permission.py

class PermissionMiddleware(ToolMiddleware):
    def __init__(self, permission_service: PermissionService):
        self._permission_service = permission_service
    
    async def before_execute(
        self,
        tool_name: str,
        params: dict[str, Any],
        context: ToolContext
    ) -> ToolMiddlewareDecision:
        """Check permission."""
        # Get tool risk level from registry
        tool = context.tool_registry.get_tool(tool_name)
        if not tool:
            return ToolMiddlewareDecision(allow=True)
        
        if tool.risk_level == RiskLevel.LOW:
            return ToolMiddlewareDecision(allow=True)
        
        # Request permission
        decision = await self._permission_service.request(
            tool_name=tool_name,
            description=tool.description,
            risk_level=tool.risk_level,
            params=params,
            session_id=context.session_id
        )
        
        if decision in (
            PermissionDecision.ALLOW,
            PermissionDecision.PERSISTENT_ALLOW
        ):
            return ToolMiddlewareDecision(allow=True)
        
        return ToolMiddlewareDecision(
            allow=False,
            reason=f"Permission denied for {tool_name}"
        )

# zenith/tools/middleware/validation.py

class ValidationMiddleware(ToolMiddleware):
    async def before_execute(
        self,
        tool_name: str,
        params: dict[str, Any],
        context: ToolContext
    ) -> ToolMiddlewareDecision:
        """Validate parameters."""
        # Validate params against JSON schema
        # Check file paths exist
        # Sanitize inputs
        return ToolMiddlewareDecision(allow=True)
    
    async def after_execute(
        self,
        tool_name: str,
        params: dict[str, Any],
        result: ToolResult,
        context: ToolContext
    ) -> ToolResult:
        """Validate result."""
        # Ensure result matches expected schema
        return result

# zenith/tools/middleware/logging.py

class LoggingMiddleware(ToolMiddleware):
    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus
        self._start_times: dict[str, float] = {}
    
    async def before_execute(
        self,
        tool_name: str,
        params: dict[str, Any],
        context: ToolContext
    ) -> ToolMiddlewareDecision:
        """Log tool invocation."""
        start_time = time.time()
        self._start_times[tool_name] = start_time
        
        self._event_bus.publish(Event(
            kind=EventKind.TOOL_CALL,
            session_id=context.session_id,
            tool_name=tool_name,
            tool_params=params
        ))
        
        return ToolMiddlewareDecision(allow=True)
    
    async def after_execute(
        self,
        tool_name: str,
        params: dict[str, Any],
        result: ToolResult,
        context: ToolContext
    ) -> ToolResult:
        """Log tool completion."""
        start_time = self._start_times.pop(tool_name, time.time())
        duration = time.time() - start_time
        
        self._event_bus.publish(Event(
            kind=EventKind.TOOL_RESULT,
            session_id=context.session_id,
            tool_name=tool_name,
            tool_result=result,
            metadata={"duration": duration}
        ))
        
        return result
```

---

## 8. Prompt System

### 8.1 Template Engine

```python
# zenith/agent/templates.py

class PromptTemplate:
    def __init__(self, template: str):
        self._template = template
        self._variables: dict[str, str] = {}
    
    def set(self, key: str, value: str) -> "PromptTemplate":
        """Set a template variable."""
        self._variables[key] = value
        return self
    
    def render(self) -> str:
        """Render template with variables."""
        result = self._template
        for key, value in self._variables.items():
            result = result.replace(f"{{{{{key}}}}}", value)
        return result

class PromptBuilder:
    def __init__(self, config: ConfigService):
        self._config = config
        self._templates: dict[str, PromptTemplate] = {}
    
    def load_templates(self, directory: Path) -> None:
        """Load all .md files as templates."""
        for file in directory.glob("*.md"):
            template = PromptTemplate(file.read_text())
            self._templates[file.stem] = template
    
    async def build_system_prompt(
        self,
        role: AgentRole,
        workspace_root: Path,
        context_files: list[Path],
        config: ConfigService
    ) -> str:
        """Build system prompt."""
        # Load base template for role
        template = self._templates.get(f"system_{role.value}")
        if not template:
            template = self._templates.get("system")
        
        # Set variables
        template.set("workspace_root", str(workspace_root))
        template.set("date", datetime.now().isoformat())
        template.set("platform", sys.platform)
        
        # Load context files
        context_content = []
        for file in context_files:
            if file.exists():
                content = file.read_text()
                context_content.append(f"## {file.name}\n\n{content}")
        
        template.set("context_files", "\n\n".join(context_content))
        
        # Load tool descriptions
        tool_descriptions = self._load_tool_descriptions()
        template.set("tools", tool_descriptions)
        
        return template.render()
    
    async def build_user_prompt(
        self,
        prompt: str,
        repo_map: str | None,
        file_context: list[Path]
    ) -> str:
        """Build user prompt."""
        parts = [prompt]
        
        if repo_map:
            parts.append(f"\n\n## Repository Map\n\n{repo_map}")
        
        if file_context:
            file_contents = []
            for file in file_context:
                if file.exists():
                    content = file.read_text()
                    file_contents.append(f"### {file.name}\n\n```\n{content}\n```")
            parts.append(f"\n\n## File Context\n\n" + "\n\n".join(file_contents))
        
        return "".join(parts)
    
    def _load_tool_descriptions(self) -> str:
        """Load tool descriptions."""
        # Load from tool .md files or generate from schema
        pass
```

### 8.2 Prompt Files Structure

```
zenith/agent/prompts/
├── system.md                    # Base system prompt
├── system_coder.md              # Coder-specific additions
├── system_task.md               # Task agent additions
├── system_reviewer.md           # Reviewer agent additions
├── tools/
│   ├── bash.md                  # Bash tool description
│   ├── file_read.md             # File read tool description
│   ├── file_write.md            # File write tool description
│   ├── file_edit.md             # File edit tool description
│   ├── glob.md                  # Glob tool description
│   ├── grep.md                  # Grep tool description
│   ├── webfetch.md              # Web fetch tool description
│   ├── agent.md                 # Sub-agent tool description
│   └── ...                      # Other tool descriptions
├── examples/
│   ├── few_shot_1.md            # Few-shot example 1
│   ├── few_shot_2.md            # Few-shot example 2
│   └── ...                      # Other examples
└── sections/
    ├── git_context.md           # Git context section
    ├── repo_map.md              # Repo map section
    ├── file_context.md          # File context section
    └── ...                      # Other sections
```

### 8.3 Prompt Template Example

```markdown
<!-- zenith/agent/prompts/system.md -->
You are Zenith, an AI coding assistant. You help users with software engineering tasks.

## Current Date
{{date}}

## Platform
{{platform}}

## Workspace
{{workspace_root}}

## Context Files
{{context_files}}

## Available Tools
{{tools}}

## Guidelines
- Always think before acting
- Use tools to gather information before making changes
- Verify your work with tests when possible
- Explain your reasoning

## Response Format
- Use markdown for formatting
- Be concise but thorough
- Show code changes in diff format when appropriate
```

---

## 9. Dependency Graph

### 9.1 Backend Dependencies

```
┌─────────────────────────────────────────────────────────────────────┐
│                    DEPENDENCY GRAPH (Top-Down)                      │
└─────────────────────────────────────────────────────────────────────┘

Level 0 (Foundation):
├── core/events.py          (EventBus, Event, EventKind)
├── core/errors.py          (Exception hierarchy)
├── core/message.py         (Message model)
└── core/session.py         (Session model)

Level 1 (Services):
├── config/service.py       (ConfigService)
├── session/service.py      (SessionService)
├── permission/service.py   (PermissionService)
└── workspace/service.py    (WorkspaceService)

Level 2 (Providers):
├── providers/base.py       (ProviderService)
├── providers/llm.py        (LLMProvider implements ProviderService)
└── providers/registry.py   (ProviderRegistry)

Level 3 (Tools):
├── tools/base.py           (BaseTool, ToolMiddleware, ToolExecutor)
├── tools/registry.py       (ToolRegistry implements ToolExecutor)
├── tools/middleware/        (SafetyCheck, Permission, Validation, Logging)
└── tools/                  (BashTool, FileReadTool, etc.)

Level 4 (Agent):
├── agent/templates.py      (PromptBuilder)
├── agent/context.py        (ContextManager)
├── agent/loop_detection.py (LoopDetector)
├── agent/runtime.py        (AgentRuntime)
└── agent/coordinator.py    (CoordinatorService)

Level 5 (Transport):
├── transport/protocol.py   (JsonRpcMethod, protocol types)
├── transport/server.py     (FastAPI app)
├── transport/websocket.py  (WebSocket handler)
└── transport/              (Middleware, startup, shutdown)

Level 6 (Application):
├── main.py                 (CLI entry point)
└── app.py                  (Application container, DI wiring)
```

### 9.2 Frontend Dependencies

```
┌─────────────────────────────────────────────────────────────────────┐
│                    DEPENDENCY GRAPH (Top-Down)                      │
└─────────────────────────────────────────────────────────────────────┘

Level 0 (Foundation):
├── types/scenario.ts       (Event types, ScenarioEvent)
├── types/startup.ts        (Startup types)
└── services/scenario/types.ts (ScenarioProvider interface)

Level 1 (Services):
├── services/backend/WebSocketClient.ts (WebSocket transport)
├── services/data/CommandService.ts     (Command registry)
├── services/data/StartupService.ts     (Backend validation)
├── services/providers/ProviderService.ts (Provider state)
└── services/providers/ProviderRepository.ts (Provider config)

Level 2 (Hooks):
├── hooks/useScenario.ts    (Scenario lifecycle)
├── hooks/useConversation.ts (Turn management)
├── hooks/useOverlayManager.ts (Modal stack)
├── hooks/useAutocomplete.ts (Input state)
└── hooks/useProvider.ts    (Provider state)

Level 3 (Components):
├── components/Display/Scenario/ (Event renderers)
├── components/Input/            (Input components)
├── components/ErrorBoundary.tsx (Error handling)
└── components/ui/               (Reusable UI)

Level 4 (Screens):
├── screens/Welcome/        (Welcome screen)
├── screens/SetupWizard/    (Provider setup)
├── screens/ModeSelect/     (Mode selection)
├── screens/Help/           (Help modal)
├── screens/Settings/       (Settings modal)
└── screens/Context/        (Context modal)

Level 5 (Application):
├── context/AppContext.tsx   (App state context)
├── App.tsx                  (Root component)
└── index.tsx                (Entry point)
```

### 9.3 Implementation Order

Based on the dependency graph, the implementation should proceed in this order:

**Phase 1: Foundation (Week 1-2)**
1. Core event system (`core/events.py`) - EventBus, Event model
2. Core models (`core/message.py`, `core/session.py`) - Data models
3. Core errors (`core/errors.py`) - Exception hierarchy

**Phase 2: Services (Week 3-4)**
4. Config service (`config/service.py`) - Configuration management
5. Session service (`session/service.py`) - Session CRUD
6. Permission service (`permission/service.py`) - Permission system
7. Workspace service (`workspace/service.py`) - Git/files

**Phase 3: Providers (Week 5)**
8. Provider base (`providers/base.py`) - Provider interface
9. LLM provider (`providers/llm.py`) - LiteLLM implementation
10. Provider registry (`providers/registry.py`) - Provider factory

**Phase 4: Tools (Week 6-7)**
11. Tool base (`tools/base.py`) - Tool interface, middleware
12. Tool registry (`tools/registry.py`) - Tool execution
13. Tool middleware (`tools/middleware/`) - Safety, permission, validation, logging
14. Individual tools (`tools/`) - Refactor existing tools

**Phase 5: Agent (Week 8-9)**
15. Prompt templates (`agent/templates.py`) - Template engine
16. Context manager (`agent/context.py`) - Context window management
17. Loop detection (`agent/loop_detection.py`) - Loop detection
18. Agent runtime (`agent/runtime.py`) - Agent execution
19. Coordinator (`agent/coordinator.py`) - Orchestration

**Phase 6: Transport (Week 10)**
20. Protocol (`transport/protocol.py`) - JSON-RPC types
21. WebSocket handler (`transport/websocket.py`) - WebSocket transport
22. Server (`transport/server.py`) - FastAPI app

**Phase 7: Integration (Week 11-12)**
23. Application container (`app.py`) - DI wiring
24. Main entry (`main.py`) - CLI entry point
25. Frontend services refactoring
26. Frontend hooks refactoring
27. Frontend components refactoring

**Phase 8: Testing (Week 13-14)**
28. Unit tests for all services
29. Integration tests for agent loop
30. E2E tests for WebSocket protocol
31. Performance testing

**Phase 9: Documentation (Week 15)**
32. Architecture documentation
33. API documentation
34. Developer guide
35. Migration guide
```

---

## 10. Migration Strategy

### 10.1 Incremental Migration Approach

The migration will follow a **Strangler Fig Pattern**, where new components are built alongside existing ones, and traffic is gradually migrated.

#### **Phase 1: Foundation (Non-Breaking)**
- Add new core models alongside existing ones
- Create EventBus that wraps existing event emission
- Add new service interfaces without implementations
- **Risk**: Low - additive changes only

#### **Phase 2: Parallel Implementation**
- Implement new services alongside existing code
- Create adapters that bridge old and new interfaces
- Run both systems in parallel with feature flags
- **Risk**: Medium - increased complexity

#### **Phase 3: Gradual Migration**
- Migrate one domain at a time (e.g., start with ConfigService)
- Update consumers to use new services
- Deprecate old code paths
- **Risk**: Medium - breaking changes possible

#### **Phase 4: Cleanup**
- Remove old code paths
- Remove adapters and bridges
- Update all documentation
- **Risk**: Low - cleanup only

### 10.2 Feature Flags

```python
# zenith/config/feature_flags.py

class FeatureFlag(Enum):
    USE_NEW_EVENT_BUS = "use_new_event_bus"
    USE_NEW_CONFIG_SERVICE = "use_new_config_service"
    USE_NEW_SESSION_SERVICE = "use_new_session_service"
    USE_NEW_PERMISSION_SERVICE = "use_new_permission_service"
    USE_NEW_TOOL_EXECUTOR = "use_new_tool_executor"
    USE_NEW_AGENT_RUNTIME = "use_new_agent_runtime"
    USE_NEW_COORDINATOR = "use_new_coordinator"
    USE_NEW_PROMPT_BUILDER = "use_new_prompt_builder"

class FeatureFlagService:
    def __init__(self, config: ConfigService):
        self._config = config
        self._overrides: dict[FeatureFlag, bool] = {}
    
    def is_enabled(self, flag: FeatureFlag) -> bool:
        """Check if feature flag is enabled."""
        if flag in self._overrides:
            return self._overrides[flag]
        
        # Check config
        value = self._config.get(f"feature_flag.{flag.value}")
        return value if isinstance(value, bool) else False
    
    def set_override(self, flag: FeatureFlag, enabled: bool) -> None:
        """Override feature flag."""
        self._overrides[flag] = enabled
```

### 10.3 Adapter Pattern

```python
# zenith/transport/adapters/legacy_handler.py

class LegacyHandlerAdapter:
    """Adapter that bridges old ZenithHandler with new CoordinatorService."""
    
    def __init__(
        self,
        coordinator: CoordinatorService,
        event_bus: EventBus
    ):
        self._coordinator = coordinator
        self._event_bus = event_bus
    
    async def handle_prompt(
        self,
        session_id: str,
        prompt: str,
        mode: ScenarioMode
    ) -> AsyncIterator[Event]:
        """Handle prompt using new coordinator."""
        async for event in self._coordinator.handle_prompt(
            session_id, prompt, mode
        ):
            yield event
    
    async def create_session(
        self,
        title: str | None = None
    ) -> Session:
        """Create session using new coordinator."""
        return await self._coordinator.create_session(title)
```

### 10.4 Testing Strategy

```python
# tests/unit/test_agent_runtime.py

class TestAgentRuntime:
    @pytest.fixture
    def mock_provider(self):
        return Mock(spec=ProviderService)
    
    @pytest.fixture
    def mock_tool_executor(self):
        return Mock(spec=ToolExecutor)
    
    @pytest.fixture
    def mock_event_bus(self):
        return Mock(spec=EventBus)
    
    @pytest.fixture
    def runtime(self, mock_provider, mock_tool_executor, mock_event_bus):
        return AgentRuntime(
            provider=mock_provider,
            tool_executor=mock_tool_executor,
            event_bus=mock_event_bus
        )
    
    @pytest.mark.asyncio
    async def test_process_prompt_publishes_thinking_event(
        self, runtime, mock_provider, mock_event_bus
    ):
        # Arrange
        mock_provider.stream.return_value = AsyncIterator([
            ProviderChunk(delta="Hello", tool_call_delta=None, usage=None)
        ])
        
        session = Session(id="test", title="Test")
        history = []
        
        # Act
        events = []
        async for event in runtime.process_prompt(
            "Test prompt", session, history
        ):
            events.append(event)
        
        # Assert
        mock_event_bus.publish.assert_any_call(
            Event(kind=EventKind.THINKING, session_id="test", content="Hello")
        )
    
    @pytest.mark.asyncio
    async def test_process_prompt_executes_tool(
        self, runtime, mock_provider, mock_tool_executor, mock_event_bus
    ):
        # Arrange
        mock_provider.stream.return_value = AsyncIterator([
            ProviderChunk(
                delta=None,
                tool_call_delta=ToolCallDelta(
                    id="call_123",
                    name="bash",
                    arguments='{"command": "ls"}'
                ),
                usage=None
            )
        ])
        
        mock_tool_executor.execute.return_value = ToolResult(
            success=True,
            output="file1.txt\nfile2.txt"
        )
        
        session = Session(id="test", title="Test")
        history = []

        
        # Act
        events = []
        async for event in runtime.process_prompt(
            "List files", session, history
        ):
            events.append(event)
        
        # Assert
        mock_tool_executor.execute.assert_called_once_with(
            "bash",
            {"command": "ls"},
            ToolContext(session_id="test", workspace_root=ANY, mode=ANY, agent_role=ANY, permissions=ANY)
        )
```

---

## 11. RFC Summary

### 11.1 Problem Statement
Zenith's current architecture suffers from:
- God objects (AgentLoop 767 lines, ZenithHandler 437 lines)
- No permission system (inline confirm_callback)
- No event bus (direct emit calls)
- No middleware chain (hardcoded validation)
- Singletons everywhere (testing difficult)
- Hardcoded values (prompts, configs, linters)
- Tight coupling (private attribute access)
- No context threading (config scattered)

### 11.2 Solution
Implement a service-oriented architecture with:
- **10 domains** with clear boundaries
- **12 core service interfaces** (AgentRuntime, ProviderService, ToolExecutor, EventBus, PermissionService, SessionService, WorkspaceService, ConfigService, CoordinatorService, PromptBuilder, ContextManager, LoopDetector)
- **Middleware chain** for tool execution
- **Event-driven** communication via pub/sub
- **Dependency injection** container
- **Protocol-first** approach with shared JSON-RPC contract

### 11.3 Implementation Plan
- **15 weeks** total
- **9 phases** (Foundation → Services → Providers → Tools → Agent → Transport → Integration → Testing → Documentation)
- **Strangler Fig pattern** for incremental migration
- **Feature flags** for safe rollout
- **Adapter pattern** for backward compatibility

### 11.4 Success Metrics
- AgentLoop reduced from 767 lines to <200 lines
- 100% of tool calls go through middleware chain
- All 163 existing tests pass
- New test coverage >80%
- Zero breaking changes to frontend protocol
- Performance neutral or better (latency, memory)

### 11.5 Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| Breaking frontend protocol | High | Shared schema, versioned JSON-RPC |
| Performance regression | Medium | Benchmarking in CI, feature flags |
| Testing gaps | Medium | TDD approach, integration tests |
| Scope creep | High | Strict phase boundaries, MVP focus |
| Team adoption | Medium | Documentation, examples, code review |

---

## 12. Key Files to Modify

### Backend Files
| File | Original Lines | Final Lines | Target | Status |
|------|---------------|-------------|--------|--------|
| `zenith/agent/loop.py` | 767 | 231 | <200 | ✅ Extracted to validation.py, llm_stream.py, tool_executor.py |
| `zenith/transport/websocket.py` | 437 | 101 | <200 | ✅ Extracted to handlers.py, prompt.py |
| `zenith/core/events.py` | ~100 | 194 | ~300 | ✅ EventBus, subscriptions added |
| `zenith/tools/base.py` | 36 | 73 | ~150 | ✅ ToolMiddleware, ToolContext added |
| `zenith/tools/registry.py` | ~100 | 116 | ~200 | ✅ Middleware chain execution added |
| `zenith/config/settings.py` | ~100 | 85 | ~200 | ✅ ConfigService interface added |

### New Backend Files
| File | Purpose | Status |
|------|---------|--------|
| `zenith/agent/coordinator.py` | Orchestration, session management | ✅ |
| `zenith/agent/runtime.py` | Agent execution loop | ✅ |
| `zenith/agent/templates.py` | Prompt template engine | ✅ |
| `zenith/permission/service.py` | Permission system | ✅ |
| `zenith/permission/grants.py` | Grant persistence | ✅ |
| `zenith/tools/middleware/__init__.py` | Middleware package | ✅ |
| `zenith/tools/middleware/safety.py` | Safety check middleware | ✅ |
| `zenith/tools/middleware/permission.py` | Permission middleware | ✅ |
| `zenith/tools/middleware/validation.py` | Validation middleware | ✅ |
| `zenith/tools/middleware/logging_mw.py` | Logging middleware | ✅ |
| `zenith/config/feature_flags.py` | Feature flag system | ✅ |
| `zenith/app.py` | Application container | ✅ |

### Frontend Files
| File | Original Lines | Final Lines | Target | Status |
|------|---------------|-------------|--------|--------|
| `src/App.tsx` | 336 | 169 | <200 | ✅ Extracted to OverlayRouter.tsx, WelcomeView.tsx |
| `src/hooks/useScenario.ts` | ~200 | 118 | ~150 | ✅ Simplified with extracted helpers |
| `src/services/backend/WebSocketClient.ts` | 208 | 210 | ~150 | ✅ Reconnect with jitter + max delay cap |

### New Frontend Files
| File | Purpose | Status |
|------|---------|--------|
| `src/services/eventBus.ts` | Client-side event bus | ✅ |
| `src/hooks/useStore.ts` | Centralized state management | ✅ (as `src/context/useStore.tsx`) |
| `src/routes/OverlayRouter.tsx` | Overlay/modal routing | ✅ |

---

## 13. Appendix A: Current Architecture Strengths

1. **Clean frontend/backend separation** via WebSocket/JSON-RPC
2. **Well-defined event system** with 9 event kinds
3. **Universal LLM provider** via LiteLLM
4. **Solid tool abstraction** with BaseTool ABC and ToolRegistry
5. **Pydantic models** for type safety across backend
6. **163 backend tests + 103 frontend tests** - good coverage baseline
7. **Ink TUI with React** - component-based UI
8. **Static rendering** for completed turns - performance optimization
9. **Loop detection** via SHA-256 sliding window
10. **Recoverable error handling** via RecoverableAgentLoop wrapper
11. **Context file support** (AGENTS.md, CRUSH.md, etc.)
12. **9 themes** with token-driven theme system

## 14. Appendix B: Crush Patterns Applied

| Crush Pattern | Zenith Implementation | Priority |
|---------------|----------------------|----------|
| Pub/Sub Broker | EventBus with typed subscriptions | High |
| Service Interfaces | 12 core service ABCs | High |
| Hook System | ToolMiddleware chain | High |
| Permission Service | PermissionService with grants | High |
| Coordinator Pattern | CoordinatorService | High |
| Config as Service | ConfigService with subscriptions | Medium |
| File Tracker | WorkspaceService.track_file() | Medium |
| LSP State Machine | State machine in LspManager | Low |

## 15. Appendix C: Aider Patterns Applied

| Aider Pattern | Zenith Implementation | Priority |
|---------------|----------------------|----------|
| Template Method (Coder) | AgentRuntime with PromptBuilder | Medium |
| Prompt Files | prompts/*.md template files | Medium |
| Chat Summary | SessionService.summarize() | Medium |
| Tree-sitter Linter | WorkspaceService.run_linter() | Low |
| RepoMap | WorkspaceService.get_repo_map() | Low |

---

**Document Version**: 2.0
**Last Updated**: 2026-07-28
**Status**: Repository Consolidation + Architecture Audit In Progress

---

## 16. Phase 5: Model Interaction Maturity — 52 Work Items

Comprehensive audit of static/hardcoded values in the model interaction layer.
Each item compares Our App vs Aider vs Crush with a recommended fix.

### 16.1 Model Parameters

| # | Issue | Our App | Aider | Crush | Recommended | File |
|---|---|---|---|---|---|---|
| 1 | Static temperature `0.7` | Hardcoded in `LLMProvider.__init__` | Per-model `use_temperature` in `model-settings.yml` — `True`/`False`/`float` | User override > catalog default via `cmp.Or` | Per-model in catalog + user override. Reasoning models = 0, creative = 1.0 | `providers/llm_provider.py:152` |
| 2 | Gemini temperature hack | `if model.startswith("gemini-3") or "gemini-2.5": temp = 1.0` | No provider-specific hacks | No provider-specific hacks | Remove hack. Add `temperature` per model in catalog | `providers/llm_provider.py:197-200` |
| 3 | Static max_tokens output `4096` | Hardcoded in `LLMProvider.__init__` | Fetched from litellm's `model_prices_and_context_window.json` | `model.CatwalkCfg.DefaultMaxTokens` from catalog, user override via `model.ModelCfg.MaxTokens` | Per-model in catalog. 4096 is way too low for 16K/32K/64K models | `providers/llm_provider.py:151` |
| 4 | Static max_tokens fallback `128000` | Hardcoded in `list_models_typed()` | N/A — always fetched | N/A — always from catalog | Read from catalog `context_window` field | `providers/llm_provider.py:503-504` |
| 5 | Static enable_thinking `False` | Hardcoded in `LLMProvider.__init__` | Per-model `reasoning_tag` in `model-settings.yml` | `model.CanReason` + `model.ReasoningLevels` from catalog | Per-model in catalog | `providers/llm_provider.py:155` |
| 6 | Static reasoning_budget `None` | Hardcoded in `LLMProvider.__init__` | N/A — uses `reasoning_tag` to strip reasoning output | `model.DefaultReasoningEffort` from catalog | Per-model in catalog | `providers/llm_provider.py:156` |

### 16.2 Context Window

| # | Issue | Our App | Aider | Crush | Recommended | File |
|---|---|---|---|---|---|---|
| 7 | Static max_context_tokens `128000` | Static in `BootstrapDefaults` | Fetched from litellm JSON DB + OpenRouter API, cached 24h | `catwalk.Model.ContextWindow` from catalog + auto-discovery enrichers | Per-model from catalog. 128K is wrong for GPT-4 (8K), Gemini (1M), Groq (128K) | `config/settings.py:101-103` |
| 8 | Static response reserve ratio `0.7` | Hardcoded | `max_chat_history_tokens = min(max(max_input_tokens / 16, 1024), 8192)` | Adaptive: 20K buffer for 200K+ models, 20% ratio for smaller | Adaptive based on model size | `agent/context.py:11` |
| 9 | Static prompt buffer tokens `500` | Hardcoded | N/A — uses token counting directly | N/A | Could be dynamic based on system prompt size | `agent/context.py:12` |
| 10 | Static summary framing tokens `4` | Hardcoded | N/A | N/A | Minor — keep as-is | `agent/context.py:13` |

### 16.3 Context Management

| # | Issue | Our App | Aider | Crush | Recommended | File |
|---|---|---|---|---|---|---|
| 11 | Static summary threshold `0.8` | Static in `BootstrapDefaults` | Runtime `ContextWindowExceededError` detection | Adaptive: 20K buffer for 200K+ models, 20% for smaller | Adaptive based on model context window size | `config/settings.py:104-106` |
| 12 | No runtime context detection | Only checks before LLM call | Pre-check + runtime `ContextWindowExceededError` + `FinishReasonLength` | `StopWhen` condition checked after every step | Add runtime context exhaustion detection | `agent/loop.py` |
| 13 | No FinishReasonLength handling | Not handled | Catches `FinishReasonLength`, tries assistant prefill continuation | N/A | Handle output length limits gracefully | `agent/llm_stream.py` |

### 16.4 Retry & Rate Limits

| # | Issue | Our App | Aider | Crush | Recommended | File |
|---|---|---|---|---|---|---|
| 14 | Count-based retries (not time-based) | `3` env var, stream `2` hardcoded | Time-based: retry until `RETRY_TIMEOUT = 60s` | Delegated to `fantasy` library | Switch to time-based (60s) like Aider | `providers/retry.py:50`, `agent/llm_stream.py:17` |
| 15 | Base delay too high `0.5s` | `0.5s` env var | Starts at `0.125s` | Delegated to `fantasy` | 0.125s start is better for fast providers | `providers/retry.py:52` |
| 16 | Max delay too low `10s` | `10s` env var | `60s` (`RETRY_TIMEOUT`) | Delegated to `fantasy` | Increase to 60s — free tier needs longer waits | `providers/retry.py:53` |
| 17 | Stream retry count `2` | Hardcoded | Time-based (same 60s) | Delegated to `fantasy` | Time-based like Aider | `agent/llm_stream.py:17` |
| 18 | String-based error classification | `"429" in msg or "rate limit" in msg` | litellm's `LiteLLMExceptions` classifies automatically | `fantasy.ProviderError` with `StatusCode` field | Use litellm's error classification | `providers/llm_provider.py:111` |
| 19 | Retry-After header parsing incomplete | Parsed from `exc.response.headers` | litellm handles internally | Delegated to `fantasy` | Also parse from litellm error response | `providers/llm_provider.py:113-119` |
| 20 | Rate limit fallback uses count-based delay | `e.retry_after or (2 ** attempt)` | `retry_delay *= 2` starting at 0.125s | Delegated | Use provider's retry-after when available | `agent/llm_stream.py:86` |

### 16.5 Token Counting

| # | Issue | Our App | Aider | Crush | Recommended | File |
|---|---|---|---|---|---|---|
| 21 | Token counter model mismatch | `tiktoken` with `cl100k_base` fallback | `tiktoken` via `model.token_count()` | Heuristic: `(len(s) + 3) / 4` | tiktoken is fine, but need model-specific encodings | `providers/token_counter.py:30-35` |
| 22 | Message framing tokens | `+4` per message, `+2` for reply priming | Uses litellm's accurate framing | Heuristic only | Minor — keep as-is | `providers/token_counter.py:61-62` |
| 23 | No usage fallback for zero-usage providers | If tiktoken fails, uses `len(text) // 4` heuristic | N/A — tiktoken always available | `fallbackStepUsage()` when provider returns zero usage | Add fallback when provider returns zero usage | `providers/token_counter.py:66-68` |

### 16.6 Model Capabilities

| # | Issue | Our App | Aider | Crush | Recommended | File |
|---|---|---|---|---|---|---|
| 24 | Static FC support detection | `function_calling: true/false` in catalog per model | `edit_format` per model (whole/diff/udiff/tool etc.) | `catwalk.Model` capabilities auto-discovered | Auto-detect via litellm or provider API | `config/provider_catalog.json` |
| 25 | Static thinking/reasoning support | `thinking: true/false` in catalog | `reasoning_tag` per model | `catwalk.Model.CanReason` + `ReasoningLevels` | Per-model in catalog (already done, but static) | `config/provider_catalog.json` |
| 26 | No image/vision support tracking | Not tracked | Not explicitly tracked | `catwalk.Model.SupportsImages` auto-discovered from Ollama/LMStudio | Add to catalog + auto-discovery | `config/provider_catalog.json` |
| 27 | No auto-discovery of model capabilities | Manual `provider_catalog.json` maintenance | Fetched from BerriAI's GitHub JSON DB + OpenRouter API | Per-provider `Enricher` interface: Ollama, LMStudio, litellm, oMLX, llama.cpp | Add enricher pattern for auto-discovery | `config/provider_catalog.json` |

### 16.7 Per-Model Behavior

| # | Issue | Our App | Aider | Crush | Recommended | File |
|---|---|---|---|---|---|---|
| 28 | No edit_format per model | All models use same prompt format | `edit_format` per model: whole/diff/udiff/editor-diff/editor-whole/tool/tool-interleaved | N/A (different architecture) | Add per-model prompt format adaptation | `agent/prompts.py` |
| 29 | No weak/editor model strategy | Single model for everything (expensive model for commit messages, summaries) | `weak_model` for cheap tasks, `editor_model` for file editing | `largeModel` + `smallModel` two-tier strategy | Two-tier: cheap model for summaries/commits | `providers/llm_provider.py` |
| 30 | No extra_params per model | Not supported | `extra_params` per model in `model-settings.yml` | `ProviderOptions` map | Add per-model extra params | `providers/llm_provider.py` |
| 31 | No system_prompt_prefix per model | Not supported | `system_prompt_prefix` per model | `SystemPromptPrefix` in `ProviderConfig` | Add per-model system prompt prefix | `agent/prompts.py` |
| 32 | No use_system_prompt flag | Always uses system prompt | `use_system_prompt: bool` per model | N/A | Add per-model flag | `agent/prompts.py` |
| 33 | No streaming flag per model | Always streams | `streaming: bool` per model | N/A | Add per-model flag | `providers/llm_provider.py` |

### 16.8 Provider-Specific

| # | Issue | Our App | Aider | Crush | Recommended | File |
|---|---|---|---|---|---|---|
| 34 | Global litellm.drop_params | `True` globally | N/A — litellm handles | N/A | Per-model instead of global | `providers/llm_provider.py:179` |
| 35 | No provider-specific adapters | Single `LLMProvider` via litellm | Single `Coder` class with `edit_format` variations | `Enricher` interface per provider for auto-discovery | Add enricher pattern | `providers/llm_provider.py` |
| 36 | No API key template refresh | Static API key | Static API key | `refreshApiKeyTemplate()` for dynamic keys | Low priority — add if needed | `providers/llm_provider.py` |

### 16.9 Agent Loop

| # | Issue | Our App | Aider | Crush | Recommended | File |
|---|---|---|---|---|---|---|
| 37 | Safety net iterations `100` | Hardcoded | No max — runs until LLM stops or context exhausted | No max — `StopWhen` conditions | Keep as safety net only (already done) | `agent/loop.py` |
| 38 | Reflection error limit `6` | Hardcoded | `max_reflections = 3` for lint/test retry | N/A | Dynamic based on task complexity | `agent/validation.py:9` |
| 39 | Post-completion iterations `2` | Hardcoded | N/A — single pass | N/A | Keep as-is | `agent/loop.py:179` |
| 40 | Loop detection window `10`/`5` | `10` steps, `5` max repeats | N/A | `loopDetectionWindowSize = 10`, `loopDetectionMaxRepeats = 5` | Match Crush (already done) | `agent/loop_detection.py:16-17` |
| 41 | Static task completion signals | Static regex `COMPLETION_SIGNALS` | N/A | N/A | Dynamic based on mode | `agent/validation.py:22` |

### 16.10 Tool Execution

| # | Issue | Our App | Aider | Crush | Recommended | File |
|---|---|---|---|---|---|---|
| 42 | Static max tool output `10000` | Configurable but static default | N/A — full output | N/A | Dynamic based on model context | `config/settings.py:71-73` |
| 43 | Static tool result truncation `200` | Hardcoded for metadata | N/A | N/A | Dynamic | `agent/tool_executor.py:50` |
| 44 | Static bash timeout `30s` | Default in ToolConfig | N/A | N/A | Keep configurable | `config/settings.py:65-67` |
| 45 | Static auto-background `60s` | Hardcoded | N/A | N/A | Keep configurable | `tools/bash.py:32` |

### 16.11 Transport

| # | Issue | Our App | Aider | Crush | Recommended | File |
|---|---|---|---|---|---|---|
| 46 | Static WS keepalive `30s` | Hardcoded | N/A (CLI) | SSE reconnect: 250ms initial, 10s max with exponential backoff | Keep as-is | `transport/websocket.py:115` |
| 47 | Static stale timeout `600_000ms` | Hardcoded | N/A (CLI) | N/A | Keep configurable | `src/services/backend/BackendScenarioProvider.ts:5` |
| 48 | No WS reconnect exponential backoff | `2000ms` hardcoded | N/A | `sseReconnectMaxBackoff = 10s` with exponential backoff | Add exponential backoff | `src/services/backend/BackendScenarioProvider.ts:239` |

### 16.12 Error Handling

| # | Issue | Our App | Aider | Crush | Recommended | File |
|---|---|---|---|---|---|---|
| 49 | String-based error classification | String matching on error message | litellm's `LiteLLMExceptions` automatic classification | `fantasy.ProviderError` with `StatusCode` | Use litellm's classification | `providers/llm_provider.py:106-123` |
| 50 | 401 handling is basic | Just raises `AuthenticationError` | litellm handles + URL opening for API key | OAuth refresh + API key template refresh | Add user-friendly 401 guidance | `providers/llm_provider.py:109-110` |
| 51 | No context window error handling | Not specifically handled | `ContextWindowExceededError` → auto-truncate + retry | `StopWhen` condition prevents reaching limit | Add runtime detection | `agent/loop.py` |
| 52 | No FinishReasonLength recovery | Not handled | Catches `FinishReasonLength`, tries assistant prefill continuation | N/A | Handle output length limits gracefully | `agent/llm_stream.py` |

### Priority Grouping

**P0 — Critical (models output wrong/truncated results):**
- #3: Static max_tokens `4096` — truncates outputs
- #7: Static max_context_tokens `128000` — wrong for most models
- #1: Static temperature `0.7` — wrong for reasoning/creative models
- #12: No runtime context detection
- #13: No FinishReasonLength handling

**P1 — High (immature retry/rate-limit behavior):**
- #14: Count-based retries → time-based
- #16: Max delay `10s` → `60s`
- #18: String-based error classification → litellm classification
- #20: Rate limit fallback
- #49: Error classification
- #51: Context window error handling
- #52: FinishReasonLength recovery

**P2 — Medium (missing per-model intelligence):**
- #2: Gemini temp hack removal
- #4: Static max_tokens fallback
- #5: Static enable_thinking
- #6: Static reasoning_budget
- #8: Static response reserve ratio
- #11: Static summary threshold
- #24-27: Model capabilities auto-discovery
- #28-33: Per-model behavior (edit_format, weak model, extra_params, etc.)
- #34-35: Provider-specific adapters
- #38: Dynamic reflection error limit

**P3 — Low (nice-to-have improvements):**
- #9: Dynamic prompt buffer
- #10: Summary framing tokens (keep as-is)
- #15: Base delay adjustment
- #17: Stream retry count
- #19: Retry-After header parsing
- #21-23: Token counting improvements
- #36: API key template refresh
- #37: Safety net iterations (keep as-is)
- #39: Post-completion iterations (keep as-is)
- #40-41: Loop detection (already done)
- #42-45: Tool execution tuning
- #46-48: Transport improvements
- #50: 401 handling
