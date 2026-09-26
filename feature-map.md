# Feature Inventory

| Feature | SubFeature | Resides In | Purpose | Dependencies |
|--------|-------------|------------|---------|--------------|
| Terminal Chat UI | Slash Commands | TUI | Provide quick system actions via `/` commands | Agent Loop, Command Registry |
| Terminal Chat UI | Streaming Output | TUI | Deliver real-time LLM responses to the terminal | WebSocket Client, Agent Loop |
| Terminal Chat UI | Prompt History | TUI | Navigate and reuse previous prompt inputs | Input Buffer |
| Terminal Chat UI | Context Menu / File Picker | TUI | Browse and attach workspace files into context | File Explorer, Workspace Index |
| Terminal Chat UI | Multi-Line Input | TUI | Edit multi-line prompts with cursor navigation and shortcuts | Terminal Keyboard, Text Buffer |
| Terminal Chat UI | Mention Autocomplete | TUI | Autocomplete `@` file paths and symbols inline | File Explorer, Workspace Index |
| Terminal Chat UI | Terminal Markdown | TUI | Render syntax-highlighted markdown and code blocks | ANSI Engine |
| Terminal Chat UI | Theme System | TUI | Switch terminal color palettes with swatch previews | User Profile, Settings |
| Terminal Chat UI | Scroll Engine | TUI | Scroll viewport with visual top/bottom indicators | Terminal Dimensions |
| Terminal Chat UI | Overlay Manager | TUI | Manage focus and stacking for modal dialogs | React Ink |
| Terminal Chat UI | Error Boundary | TUI | Catch React crashes and display diagnostic cards | Theme System |
| Calm Mode | View Toggle | TUI | Hide intermediate tool steps for a minimal terminal view | User Profile, Scenario Renderer |
| Operating Modes | Plan Mode Prompt | Server | Restrict agent to read-only analysis without file changes | Prompt Templates, LLM Provider |
| Operating Modes | Build Mode Prompt | Server | Enable full filesystem mutations and command execution | Prompt Templates, LLM Provider |
| Operating Modes UI | Mode Selector | TUI | Toggle between Plan and Build modes via hotkeys | Mode Data, WebSocket Transport |
| Operating Modes UI | Plan Ready Block | TUI | Display structured plans awaiting user execution approval | Mode Selector, Agent Loop |
| Agent Orchestrator | Captain Orchestrator | Server | Coordinate specialist agents and synthesize deliverables | Task Envelope, LLM Provider |
| Agent Orchestrator UI | Captain Block & Pinned Card | TUI | Display live multi-agent delegation status and progress | WebSocket Transport, Captain Orchestrator |
| Specialist Delegation | Scout Runner | Server | Spawn isolated scout loops for repository exploration | Specialist Registry, Agent Loop |
| Specialist Delegation UI | Explore Crew Card | TUI | Visualize background explorer agents and findings | WebSocket Transport, Specialist Delegation |
| Agent Loop | Execution Engine | Server | Orchestrate prompt building, response parsing, and tool calls | LLM Provider, Toolkit |
| Agent Loop | Reasoning Stream | Server | Parse `<thought>` and reasoning tokens in real time | LLM Provider, Event Adapter |
| Agent Loop UI | Thinking Block | TUI | Display collapsible animated thinking blocks | Theme System, Reasoning Stream |
| Agent Loop | Loop Detection & Recovery | Server | Detect repetitive tool-call loops and trigger salvage pass | Agent Loop, Run State |
| Agent Loop UI | Turn Manifest Card | TUI | Summarize changed files, executed commands, and deliverables | Scenario Renderer, Agent Loop |
| Tool Engine | Tool Registry | Server | Discover, validate, and register available agent tools | Toolkit Catalog |
| Tool Engine | Tool Execution Engine | Server | Safely execute tools and capture stdout/stderr | Command Safety, Path Validator |
| Tool Engine | Result Handling | Server | Normalize and truncate tool outputs for the LLM | LLM Provider, Token Counter |
| Tool Engine | Tool Safety Guardrails | Server | Prevent malicious commands and unauthorized file deletions | Shell AST Validator |
| Tool Engine | Auto-Linting Middleware | Server | Run linters on mutated files and feed diagnostics to agent | Toolkit Middleware |
| Tool Engine UI | Tool Trace & Step Card | TUI | Render tool execution steps, statuses, and expandable logs | Scenario Renderer, Tool Engine |
| Bash Tool | Shell Execution Engine | Server | Execute shell commands in a managed process session | Process Pool, Command Safety |
| Bash Tool UI | Command Step Card | TUI | Render command cards with exit codes and output drawers | Terminal Markdown, Bash Tool |
| Background Jobs | Job Spawner & Process Pool | Server | Spawn and manage asynchronous long-running background tasks | Process Pool |
| Background Jobs UI | Job Output & Kill Cards | TUI | Display background job status and output streams | WebSocket Transport, Background Jobs |
| File Read Tool | Content & Outline Reader | Server | Read file contents, slices, or structural outlines | Workspace Index |
| File Write Tool | Atomic File Creator | Server | Create new files or overwrite files atomically | Storage Layer |
| File Edit Tool | Chunk Patcher Engine | Server | Apply contiguous chunk replacements with exact matching | Storage Layer, Auto-Linting |
| File Mutation Queue | Atomic Batch Committer | Server | Queue and coordinate multiple file mutations atomically | Storage Layer |
| File Diff UI | File Diff Block | TUI | Render syntax-highlighted unified diffs of file edits | Terminal Markdown, File Edit Tool |
| File Delete Tool | Boundary Validator & Deleter | Server | Safely delete files within workspace boundaries | Path Validator |
| Code Search Tool | Grep & Glob Search | Server | Perform regex content searches and wildcard path matching | Workspace Index |
| Directory Listing Tool | Filesystem Tree Traversal | Server | Traverse and format filesystem directory trees | Workspace Index |
| Directory Listing UI | Directory Listing Card | TUI | Render tree-structured directory hierarchies in chat | Scenario Renderer, Directory Listing Tool |
| Web Tools | Web Search & Web Fetch | Server | Query search engines and fetch readable web markdown | HTTP Client, HTML Parser |
| Todo Tool | Task State Manager | Server | Track agent task items, active statuses, and completions | Todo State, Storage Layer |
| Todo Tool UI | Pinned Todo Card & Board | TUI | Render interactive checklists and persistent progress cards | Scenario Renderer, Todo Tool |
| Prompt Planning | Prompt Templates | Server | Reusable prompt skeletons for system, plan, and build flows | LLM Provider |
| Prompt Planning | Dynamic Context Injection | Server | Inject session history, repo map, and tool docs into prompts | Session Management, Workspace |
| Prompt Planning | Plan Generation | Server | Generate structured, executable action plans | LLM Provider, Prompt Templates |
| LLM Provider | Provider Registry | Server | Register, configure, and switch LLM services | Configuration Layer |
| LLM Provider | Streaming Support | Server | Stream token-by-token responses and thoughts from providers | HTTP/SSE Client |
| LLM Provider | Error Handling & Retries | Server | Retry logic and back-off for rate limits and network errors | Base Provider |
| LLM Provider | Token Counting | Server | Measure prompt, completion, and cache tokens consumed | Provider Registry |
| LLM Provider UI | Provider Picker & Flow | TUI | Select, configure, and validate active LLM providers | Provider Registry, WebSocket Transport |
| LLM Provider UI | Model Selection Screen | TUI | List available models with context limits and capabilities | Provider Selection UI |
| LLM Provider UI | Setup Wizard | TUI | Guide first-run onboarding, provider setup, and key entry | User Profile, Provider Selection UI |
| LLM Provider UI | API Key Prompt | TUI | Securely capture and validate provider API keys | Provider Selection UI |
| LLM Provider UI | Local LLM Form | TUI | Configure local endpoints for Ollama and LM Studio | Provider Selection UI |
| LLM Provider UI | Token Usage Modal | TUI | Display token metrics, estimated costs, and session usage | Token Counting, Token Usage Service |
| LLM Provider UI | Context Inspector Modal | TUI | Visualize context occupancy and token limits | Token Estimation Service |
| Session Management | Session Store | Server | Persist conversations, tool calls, and run states to disk | Storage Layer |
| Session Management UI | Session Browser Modal | TUI | Browse, resume, or delete saved conversation sessions | Session Store, WebSocket Transport |
| Session Management | Compaction Engine | Server | Prune old turns and build summaries when token limits near | Storage Layer, LLM Provider |
| Session Management UI | Compaction Modal & Flow | TUI | Display visual indicators and modals during context compaction | Compaction Engine, WebSocket Transport |
| Session Management | Running Summary Service | Server | Continuously maintain a rolling narrative of conversation turns | LLM Provider, Session Store |
| Session Management UI | Final Summary Card | TUI | Display concise turn summaries and key decisions taken | Scenario Renderer, Running Summary |
| Session Management | Export / Import Service | Server | Backup and export session conversations to JSON or Markdown | Storage Layer |
| Session Management UI | Markdown Exporter | TUI | Export current conversation to markdown files | Session Management |
| Session Management | Session Status Tracker | Server | Track active, paused, compacted, or error states | Run State |
| Session Management UI | Session Status Line | TUI | Persistent status bar with model, branch, and health indicators | Session Status, Git Context |
| Workspace Intelligence | Repository Map | Server | Generate AST-based outlines of symbols across the workspace | Tree-Sitter / Parser |
| Workspace Intelligence | Workspace Search | Server | Fast indexed text and symbol search across the codebase | Workspace Index |
| Workspace Intelligence | Git Integration | Server | Inspect git branch, commit log, status, and diffs | Git CLI |
| Workspace Intelligence UI | Git Status Line | TUI | Display branch name and dirty working tree status | Git Integration, Status Line |
| Workspace Intelligence | Ignore Rules Engine | Server | Filter files using `.zenithignore` and `.gitignore` rules | Path Validator |
| Workspace Intelligence | LSP Client | Server | Connect to language servers for diagnostics and definitions | LSP Transport |
| Workspace Intelligence | MCP Hub | Server | Connect to external Model Context Protocol servers for tools | MCP Transport |
| Transport & Infrastructure | WebSocket Server | Server | Full-duplex WebSocket server for events and streaming | FastAPI, Uvicorn |
| Transport & Infrastructure | WebSocket Client | TUI | Reconnecting client for real-time bi-directional messaging | Transport Layer |
| Transport & Infrastructure | Event Pipeline | Server | Translate internal domain events into wire protocol events | Domain Events |
| Transport & Infrastructure | Event Mapper | TUI | Map incoming wire events to UI blocks and state updates | Backend Scenario Provider |
| Transport & Infrastructure | Server CLI | Server | Command-line interface to start, inspect, and test server | Click, Uvicorn |
| Transport & Infrastructure | User Profile Store | Server | Persist developer preferences and overrides in JSON files | Storage Layer |
| Transport & Infrastructure UI | User Profile Service | TUI | Manage developer settings, tool auto-approval, and theme | User Profile Store |
