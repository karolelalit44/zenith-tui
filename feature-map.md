# Zenith Feature Map

Inventory of every capability in the Zenith codebase, where it resides, and what it depends on.

| Feature | Sub-Level / Component | Resides In | Description (One-Liner) | Depends On |
| :--- | :--- | :--- | :--- | :--- |
| **Captain Orchestrator** | Task Envelope & Delegation Engine | `Server` | Coordinates specialist agents, plans work breakdown, and synthesizes final deliverables. | Specialist Delegation, Provider Registry |
| **Captain Orchestrator UI** | Captain Block & Pinned Orchestration Card | `TUI` | Displays real-time multi-agent delegation status, active specialist, and sub-task progress. | Captain Orchestrator, WebSocket Client |
| **Specialist Delegation** | Scout & Specialist Runners | `Server` | Spawns isolated specialist loops for codebase exploration, deep search, and inspection. | Agent Loop, Session Persistence |
| **Specialist Delegation UI** | Explore Crew Card | `TUI` | Visualizes background explorer agents and their findings in the terminal. | Specialist Delegation, WebSocket Client |
| **Agent Loop** | Turn Execution & Message Cycle | `Server` | Orchestrates LLM prompt construction, response parsing, tool calling, and state updates. | Provider Registry, Tool Execution |
| **Reasoning Stream** | Stream Parser & Event Dispatcher | `Server` | Extracts `<thought>` and reasoning tokens from LLM output in real time. | Response Streaming, Event Adapter |
| **Reasoning Stream UI** | Thinking Block | `TUI` | Displays collapsible, animated terminal blocks for live model reasoning. | Reasoning Stream, Theme System |
| **Operating Modes** | Plan Mode Prompt & Guardrails | `Server` | Restricts the agent to read-only tools and analysis plans without modifying files. | Prompt Templates, Tool Execution |
| **Operating Modes** | Build Mode Prompt & Execution | `Server` | Enables full filesystem mutations, command executions, and implementation tools. | Prompt Templates, Tool Execution |
| **Operating Modes UI** | Mode Select Screen & Indicator | `TUI` | Lets users toggle between Plan and Build modes with hotkeys and visual badges. | Operating Modes, WebSocket Client |
| **Plan Ready** | Plan Ready Block | `TUI` | Informational display of the session plan when a build first adopts it. Zenith has no interactive approval gate — the block never blocks execution. | Plan Generation, Operating Modes UI |
| **Loop Detection & Recovery** | Stagnation Detector & Salvage Pass | `Server` | Detects repetitive tool-call loops and triggers self-correction or recovery prompts. | Agent Loop, Session Status |
| **Turn Manifest** | Turn Manifest Card | `TUI` | Summarizes changed files, executed commands, and key deliverables per turn. | Agent Loop, Scenario Renderer |
| **Prompt Templates** | Reusable Prompt Skeletons | `Server` | Reusable prompt skeletons for system, plan, and build flows, composed per turn. | Provider Registry |
| **Dynamic Context Injection** | Session History, Repo Map & Tool Docs | `Server` | Injects session history, repository map, and live tool documentation into the system prompt. | Session Persistence, Repository Map |
| **Plan Generation** | Structured Plan Writer | `Server` | Captures the model's structured plan output as the session's build context. | Prompt Templates, Session Persistence |
| **Tool Catalog** | Tool Registry & Schema Token Counter | `Server` | Registers available capabilities and measures the token cost of their schemas. | Provider Registry |
| **Capability Discovery** | Discover Capabilities & Get Tool Definition | `Server` | The two registered tools that let the agent list and inspect tools it has not been offered. | Tool Catalog |
| **Tool Execution** | Tool Execution Engine | `Server` | Safely executes a resolved tool call and captures its result, metadata, and duration. | Command Safety, Path Validator |
| **Result Handling** | Output Normalization & Truncation | `Server` | Normalizes and truncates tool output to a per-tool budget before it reaches the model. | Provider Registry, Token Tracking |
| **Command Safety** | Destructive-Command Blocker | `Server` | Hard-blocks destructive shell commands by program name and pattern. There are no permission tiers and no approval flow — a command is either blocked outright or it runs. | Tool Execution |
| **Ignore Rules Engine** | `.zenithignore` Parser | `Server` | Treats ignored paths as nonexistent across read, write, edit, delete and patch; a refused mutation names the ignore rule rather than reporting a missing file. | Tool Execution |
| **Auto-Linting** | Post-Mutation Linter Middleware | `Server` | Automatically runs configured linters on changed files and feeds errors back to the agent. | Tool Execution |
| **Bash Tool** | Command Runner & Shell Session | `Server` | Executes shell commands in a managed process with timeout and output capture. | Command Safety, Background Jobs |
| **Background Jobs** | Job Spawner & Process Pool | `Server` | Launches asynchronous background tasks that continue running across turns. | Bash Tool |
| **Background Jobs** | Job Output & Kill Tools | `Server` | Inspects or terminates a job; retained output is bounded per stream and in aggregate, and a job whose middle was dropped is flagged as such. | Background Jobs |
| **Background Jobs UI** | Job Output & Kill Cards | `TUI` | Displays background job status, retained output, and a kill control. | Background Jobs, WebSocket Client |
| **File Read Tool** | File Content & Outline Reader | `Server` | Reads full files, slices line ranges, or generates structural outlines, with per-slice read caching. | Repository Map |
| **File Write Tool** | Atomic File Creator | `Server` | Creates new files or completely overwrites existing files atomically. | File Mutation Queue |
| **File Edit Tool** | Chunk Patcher & Replacement Engine | `Server` | Applies search-and-replace with a widening match ladder, splicing only the matched range so untouched line endings survive byte-for-byte. | File Mutation Queue, Auto-Linting |
| **Apply Patch Tool** | Multi-File Patch Applier | `Server` | Applies Add/Update/Delete hunks across several files behind a dry run, with a per-path snapshot and rollback when a later hunk fails. | File Mutation Queue |
| **File Mutation Queue** | Mutation Queue & Atomic Commit | `Server` | Serializes concurrent filesystem mutations per workspace so a mutation cannot be interleaved. | Tool Execution |
| **File Delete Tool** | Safe File Removal | `Server` | Safely deletes files and directories after validating repository boundaries. | Ignore Rules Engine, File Mutation Queue |
| **Code Search Tools** | Grep & Glob Matching | `Server` | Performs regex content searches and wildcard path matching, skipping binary content. | Workspace Search |
| **Directory Listing Tool** | Filesystem Explorer | `Server` | Traverses directory trees with depth control and formatting. | Workspace Search |
| **Web Tools** | Web Search & Web Fetch | `Server` | Queries search engines and fetches pages into readable markdown. Every request, cache hits included, passes the SSRF guard first. | WebSocket Server, Ignore Rules Engine |
| **Todo Tool** | Tool Handler & State Manager | `Server` | Manages agent todo items, active task status, and completion state. A board's lifetime is the request, not the session, so a new turn starts clean. | Session Status |
| **Tool Trace UI** | Tool Trace & Step Card | `TUI` | Renders tool execution steps, statuses, and expandable logs for any tool. | Tool Execution, Scenario Renderer |
| **Bash Tool UI** | Command Step Card | `TUI` | Renders shell command cards with exit codes and an output drawer. | Bash Tool, Terminal Markdown |
| **File Diff UI** | File Diff Block | `TUI` | Renders syntax-highlighted unified diffs of file creations and modifications. | File Edit Tool, Terminal Markdown |
| **Directory Listing UI** | Directory Listing Card | `TUI` | Renders tree-structured directory hierarchies directly in the chat view. | Directory Listing Tool, Scenario Renderer |
| **Todo Tool UI** | Pinned Todo Card & Board Block | `TUI` | Renders interactive checklists and progress cards; both surfaces share one row limit so they cannot disagree. | Todo Tool, Scenario Renderer |
| **Session Persistence** | Session File & Store Repository | `Server` | Saves and loads complete conversation history, tool calls, and run states to disk. | User Profile Store |
| **Session Browser UI** | Session Browser Modal | `TUI` | Lists past sessions with metadata, allowing switching, resuming, or deletion. | Session Persistence, WebSocket Client |
| **Session Compaction** | Context Pruning Engine | `Server` | Truncates old message turns and builds compaction summaries when token limits near. Tool payloads the model cannot reconstruct — file contents and task state — are never reduced to digests. | Token Tracking, Agent Loop |
| **Session Compaction UI** | Compaction Modal & Flow Block | `TUI` | Displays visual indicators and progress blocks during automated context compaction. | Session Compaction, WebSocket Client |
| **Running Summary** | Incremental Summarizer Service | `Server` | Continuously maintains a condensed narrative of previous turns to preserve context. | Session Persistence, Provider Registry |
| **Running Summary UI** | Final Summary Card | `TUI` | Presents concise turn summaries and key decisions taken by the agent. | Running Summary, Scenario Renderer |
| **Session Export** | Session Exporter Service | `Server` | Formats and exports conversation sessions into JSON or Markdown files. | Session Persistence |
| **Session Export UI** | Markdown Exporter | `TUI` | Client-side export utility generating downloadable markdown logs of current chat. | Session Export |
| **Session Status** | Session State & Lifecycle Tracker | `Server` | Tracks active, paused, compacted, or error states across the current session. | Session Persistence, Agent Loop |
| **Session Status UI** | Session Status Line | `TUI` | Persistent status bar showing current mode, active model, branch, and health. | Session Status, Git Context UI |
| **Repository Map** | Codebase Tree & Symbol Mapper | `Server` | Builds a compact AST-based outline of definitions and symbols across the repo. | Tree-Sitter |
| **Workspace Search** | Indexed Workspace Query Engine | `Server` | Fast text and path indexing for lightning-quick repository queries. | Ignore Rules Engine |
| **Git Integration** | Git Command & Diff Inspector | `Server` | Inspects repository branch, commit history, working tree status, and diffs. | Git CLI |
| **Git Context UI** | Git Status Service | `TUI` | Displays current git branch and dirty working tree indicators in the status bar. | Git Integration, Session Status UI |
| **File Picker UI** | File Picker Modal & Search List | `TUI` | Fuzzy-searchable modal to browse and select workspace files to attach into context. | Directory Listing Tool, Workspace Search |
| **Provider Registry** | Multi-Provider Engine | `Server` | Manages connections to Anthropic, OpenAI, Gemini, and custom OpenAI-compatible endpoints. | User Profile Store |
| **Response Streaming** | Token-by-Token Delivery | `Server + TUI` | Streams model output incrementally to the terminal, closing the thinking block the moment content begins and dropping private trailing reasoning. | Provider Registry, WebSocket Server |
| **Provider Retries** | Error Handling & Back-off | `Server` | Retries transient provider failures such as rate limits, stream stalls, and network errors. | Provider Registry |
| **Token Tracking** | Token Counter & Usage Store | `Server` | Measures prompt, completion, and cache tokens consumed per turn and session. | Provider Registry |
| **Provider Selection UI** | Provider Picker & Flow | `TUI` | Interactive screen to select, configure, and switch active LLM providers. | Provider Registry, WebSocket Client |
| **Model Picker UI** | Model Selection Screen | `TUI` | Lists supported models with context window limits and capabilities for selection. | Provider Selection UI |
| **Setup Wizard UI** | First-Run Onboarding Flow | `TUI` | Guides new users through provider selection, API key entry, and initial setup. | Provider Selection UI |
| **API Key Prompt UI** | Secure Key Input Screen | `TUI` | Securely prompts for and validates provider API keys during setup or switching. | Provider Selection UI |
| **Local LLM UI** | Local Endpoint Form | `TUI` | Dedicated configuration UI for Ollama, LM Studio, and custom local servers. | Provider Selection UI |
| **Token Usage UI** | Usage Modal & Cost Breakdown | `TUI` | Displays token usage statistics, estimated costs, and cumulative session metrics. | Token Tracking |
| **Context Gauge** | Token Estimation Service | `TUI` | Computes live occupancy percentage of the active model's maximum context window. | Token Tracking |
| **Context Modal UI** | Context Inspector Modal | `TUI` | Visualizes context window consumption broken down by system, tools, and history. | Context Gauge, Session Compaction |
| **Command Palette** | Slash Command Registry & Palette | `TUI` | Lists and triggers slash commands (`/plan`, `/build`, `/model`, `/help`, …). | Composer |
| **Composer** | Multi-Line Text Input Buffer | `TUI` | Supports multi-line prompt editing, cursor navigation, and submission shortcuts. | Terminal Keyboard |
| **Mention Autocomplete** | @-Mention Dropdown | `TUI` | Autocompletes file paths and symbols inline as the user types `@` in the composer. | File Picker UI, Composer |
| **Prompt History** | Input History Navigator | `TUI` | Cycles through previous user prompts using arrow keys in the composer. | Composer |
| **Terminal Markdown** | ANSI & Syntax Highlighting Engine | `TUI` | Renders rich markdown, code blocks, bullet points, and headers in the terminal. | ANSI Engine |
| **Theme System** | Color Palettes & Swatches | `TUI` | Provides multiple terminal themes with previews. | User Profile Service |
| **Settings Modal** | User Preferences Modal | `TUI` | Toggles auto-approve tools, collapsed thinking blocks, and active theme. | User Profile Service |
| **Help Modal** | Keybinding & Command Reference | `TUI` | Displays keyboard shortcuts, available slash commands, and navigation tips. | Command Palette |
| **Overlay Manager** | Modal & Screen Stack Hook | `TUI` | Manages keyboard focus and rendering priority across stacked modals and dialogs. | React Ink |
| **Scroll Engine** | Terminal Scroll State & Indicator | `TUI` | Handles mouse-wheel and keyboard scrolling with visual top/bottom indicators. | Terminal Dimensions |
| **Error Handling UI** | Error Boundary & Warning Blocks | `TUI` | Catches React rendering crashes and formats server error payloads cleanly. | Theme System |
| **Calm Mode** | Minimalist View Setting | `TUI` | Hides intermediate tool executions to provide a distraction-free conversation view. | Scenario Renderer |
| **WebSocket Server** | FastAPI WebSocket Transport | `Server` | High-performance full-duplex socket for real-time events, streams, and commands. | Event Adapter |
| **WebSocket Client** | Reconnecting WebSocket Service | `TUI` | Manages connection lifecycle, auto-reconnect, and heartbeat with the server. | WebSocket Server |
| **Event Adapter** | Domain Event Serializer | `Server` | Translates internal domain events into standardized JSON event payloads, stripping internal metadata. | Domain Events |
| **Raw Event Mapper** | Scenario & UI Event Dispatcher | `TUI` | Maps incoming server events to interactive UI blocks, cards, and state changes. | Event Adapter, Scenario Renderer |
| **Server CLI** | Click Command Line Interface | `Server` | Provides terminal commands to run the server, inspect status, and list tools. | WebSocket Server, Tool Catalog |
| **User Profile Store** | Profile & Settings Persistence | `Server` | Persists user settings, theme preferences, and developer overrides in JSON storage. | Storage Layer |
| **User Profile Service** | Client Profile Cache & Sync | `TUI` | Reads and writes user preferences locally with fallback to defaults. | User Profile Store |
