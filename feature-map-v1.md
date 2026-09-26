# Zenith Feature Map

Comprehensive inventory of features and capabilities across the Zenith codebase, detailing sub-levels and their architectural residence (`Server`, `TUI`, or split between both).

---

## 1. Agent Orchestration & Execution

| Feature | Sub-Level / Component | Resides In | Description (One-Liner) |
| :--- | :--- | :--- | :--- |
| **Captain Orchestrator** | Task Envelope & Delegation Engine | `Server` | Coordinates specialist agents, plans work breakdown, and synthesizes final deliverables. |
| **Captain Orchestrator UI** | Captain Block & Pinned Orchestration Card | `TUI` | Displays real-time multi-agent delegation status, active specialist, and sub-task progress. |
| **Specialist Delegation** | Scout & Specialist Runners | `Server` | Spawns isolated specialist loops for codebase exploration, deep search, and inspection. |
| **Specialist Delegation UI** | Explore Crew Card | `TUI` | Visualizes background explorer agents and their findings in the terminal. |
| **Agent Loop** | Turn Execution & Message Cycle | `Server` | Orchestrates LLM prompt construction, response parsing, tool calling, and state updates. |
| **Reasoning Stream** | Stream Parser & Event Dispatcher | `Server` | Extracts `<thought>` and reasoning tokens from LLM output in real time. |
| **Reasoning Stream UI** | Thinking Block | `TUI` | Displays collapsible, animated terminal blocks for live model reasoning. |
| **Operating Modes** | Plan Mode Prompt & Guardrails | `Server` | Restricts agent to read-only tools and analysis plans without modifying files. |
| **Operating Modes** | Build Mode Prompt & Execution | `Server` | Enables full filesystem mutations, command executions, and implementation tools. |
| **Operating Modes UI** | Mode Select Screen & Indicator | `TUI` | Lets users toggle between Plan and Build modes with hotkeys and visual badges. |
| **Plan Ready** | Plan Ready Block | `TUI` | Highlights when a structured plan is ready for user approval before execution begins. |
| **Loop Detection & Recovery** | Stagnation Detector & Salvage Pass | `Server` | Detects repetitive tool-call loops and triggers self-correction or recovery prompts. |
| **Turn Manifest** | Turn Manifest Card | `TUI` | Summarizes changed files, executed commands, and key deliverables per turn. |

---

## 2. Tool Engine & Capabilities

| Feature | Sub-Level / Component | Resides In | Description (One-Liner) |
| :--- | :--- | :--- | :--- |
| **Bash Tool** | Command Runner & Shell Session | `Server` | Executes shell commands in a managed process with timeout and output capture. |
| **Bash Tool UI** | Tool Step Card & Trace Block | `TUI` | Renders executed shell commands, exit codes, and expandable output logs. |
| **Command Safety** | Shell AST Validator & Path Guard | `Server` | Intercepts dangerous bash commands and blocks unauthorized filesystem destruction. |
| **Background Jobs** | Job Spawner & Process Pool | `Server` | Launches asynchronous background tasks that continue running across turns. |
| **Background Jobs** | Job Output & Kill Tools | `Server` | Inspects stdout/stderr streams of background jobs or terminates them on demand. |
| **File Read Tool** | File Content & Outline Reader | `Server` | Reads full files, slices line ranges, or generates structural outlines. |
| **File Write Tool** | Atomic File Creator | `Server` | Creates new files or completely overwrites existing files atomically. |
| **File Edit Tool** | Chunk Patcher & Replacement Engine | `Server` | Applies contiguous block replacements with exact matching and safety checks. |
| **File Mutation Queue** | Mutation Queue & Atomic Commit | `Server` | Queues and coordinates multiple file modifications before flushing to disk. |
| **File Diff UI** | File Diff Block | `TUI` | Renders syntax-highlighted unified diffs of file creations and modifications. |
| **File Delete Tool** | Safe File Removal | `Server` | Safely deletes specified files after validating repository boundaries. |
| **Code Search Tools** | Grep & Glob Matching | `Server` | Performs regex content searches and wildcard path matching across the workspace. |
| **Directory Listing Tool** | Filesystem Explorer | `Server` | Traverses directory trees with depth control and formatting. |
| **Directory Listing UI** | Directory Listing Card | `TUI` | Renders tree-structured directory hierarchies directly in the chat view. |
| **Web Tools** | Web Search & Web Fetch | `Server` | Queries search engines and fetches/cleans web pages into readable markdown text. |
| **Todo Tool** | Tool Handler & State Manager | `Server` | Manages agent todo items, active task status, and completion state. |
| **Todo Tool UI** | Pinned Todo Card & Board Block | `TUI` | Renders interactive checklists and persistent progress cards in the terminal. |
| **Auto-Linting** | Post-Mutation Linter Middleware | `Server` | Automatically runs configured linters on changed files and feeds errors back to the agent. |
| **Tool Catalog & Metrics** | Registry & Schema Token Counter | `Server` | Dynamically measures tool schema token cost and registers available capabilities. |

---

## 3. Session Management & Memory

| Feature | Sub-Level / Component | Resides In | Description (One-Liner) |
| :--- | :--- | :--- | :--- |
| **Session Persistence** | Session File & Store Repository | `Server` | Saves and loads complete conversation history, tool calls, and run states to disk. |
| **Session Browser UI** | Session Browser Modal | `TUI` | Lists past sessions with metadata, allowing switching, resuming, or deletion. |
| **Session Compaction** | Context Pruning Engine | `Server` | Truncates old message turns and builds compaction summaries when token limits near. |
| **Session Compaction UI** | Compaction Modal & Flow Block | `TUI` | Displays visual indicators and progress blocks during automated context compaction. |
| **Running Summary** | Incremental Summarizer Service | `Server` | Continuously maintains a condensed narrative of previous turns to preserve context. |
| **Running Summary UI** | Final Summary Card | `TUI` | Presents concise turn summaries and key decisions taken by the agent. |
| **Session Export** | Session Exporter Service | `Server` | Formats and exports conversation sessions into JSON or Markdown files. |
| **Session Export UI** | Markdown Exporter | `TUI` | Client-side export utility generating downloadable markdown logs of current chat. |
| **Session Status** | Session State & Lifecycle Tracker | `Server` | Tracks active, paused, compacted, or error states across the current session. |
| **Session Status UI** | Session Status Line | `TUI` | Persistent status bar showing current mode, active model, branch, and health. |

---

## 4. Workspace & Code Intelligence

| Feature | Sub-Level / Component | Resides In | Description (One-Liner) |
| :--- | :--- | :--- | :--- |
| **Repository Map** | Codebase Tree & Symbol Mapper | `Server` | Builds a compact AST-based outline of definitions and symbols across the repo. |
| **Workspace Search** | Indexed Workspace Query Engine | `Server` | Fast text and path indexing for lightning-quick repository queries. |
| **Git Integration** | Git Command & Diff Inspector | `Server` | Inspects repository branch, commit history, working tree status, and diffs. |
| **Git Context UI** | Git Status Service | `TUI` | Displays current git branch and dirty working tree indicators in the status bar. |
| **Ignore Engine** | .zenithignore & .gitignore Parser | `Server` | Prevents agents and search tools from reading sensitive, build, or ignored files. |
| **File Picker UI** | File Picker Modal & Search List | `TUI` | Fuzzy-searchable modal to browse and select files to attach into context. |
| **LSP Integration** | Language Server Protocol Client | `Server` | Connects to language servers for code diagnostics, references, and definitions. |
| **MCP Integration** | Model Context Protocol Hub | `Server` | Discovers and invokes tools and resources from external MCP servers. |

---

## 5. LLM Providers & Resource Management

| Feature | Sub-Level / Component | Resides In | Description (One-Liner) |
| :--- | :--- | :--- | :--- |
| **Provider Registry** | Multi-Provider Engine | `Server` | Manages connections to Anthropic, OpenAI, Gemini, and custom OpenAI-compatible endpoints. |
| **Provider Selection UI** | Provider Picker & Flow | `TUI` | Interactive screen to select, configure, and switch active LLM providers. |
| **Model Picker UI** | Model Selection Screen | `TUI` | Lists supported models with context window limits and capabilities for selection. |
| **Setup Wizard UI** | First-Run Onboarding Flow | `TUI` | Guides new users through provider selection, API key entry, and initial setup. |
| **API Key Prompt UI** | Secure Key Input Screen | `TUI` | Securely prompts for and validates provider API keys during setup or switching. |
| **Local LLM UI** | Local Endpoint Form | `TUI` | Dedicated configuration UI for Ollama, LM Studio, and custom local servers. |
| **Token Tracking** | Token Counter & Usage Store | `Server` | Measures prompt, completion, and cache tokens consumed per turn and session. |
| **Token Usage UI** | Usage Modal & Cost Breakdown | `TUI` | Displays token usage statistics, estimated costs, and cumulative session metrics. |
| **Context Gauge** | Token Estimation Service | `TUI` | Computes live occupancy percentage of the active model's maximum context window. |
| **Context Modal UI** | Context Inspector Modal | `TUI` | Visualizes context window consumption broken down by system, tools, and history. |

---

## 6. Terminal UI & User Interaction

| Feature | Sub-Level / Component | Resides In | Description (One-Liner) |
| :--- | :--- | :--- | :--- |
| **Calm Mode** | Minimalist View Setting | `TUI` | Hides intermediate tool executions to provide a distraction-free conversation view. |
| **Composer** | Multi-Line Text Input Buffer | `TUI` | Supports multi-line prompt editing, cursor navigation, and submission shortcuts. |
| **Mention Autocomplete** | @-Mention Dropdown | `TUI` | Autocompletes file paths and symbols inline as the user types `@` in the composer. |
| **Prompt History** | Input History Navigator | `TUI` | Cycles through previous user prompts using up/down arrow keys in the composer. |
| **Command Palette** | Slash Command Registry & Palette | `TUI` | Lists and triggers slash commands (`/plan`, `/build`, `/model`, `/help`, etc.). |
| **Terminal Markdown** | ANSI & Syntax Highlighting Engine | `TUI` | Renders rich markdown, code blocks, bullet points, and headers in the terminal. |
| **Theme System** | Color Palettes & Swatches | `TUI` | Provides multiple terminal themes (e.g., Zenith Dark, Emerald, Solarized) with previews. |
| **Settings Modal** | User Preferences Modal | `TUI` | Toggles auto-approve tools, collapsed thinking blocks, and active theme. |
| **Help Modal** | Keybinding & Command Reference | `TUI` | Displays keyboard shortcuts, available slash commands, and navigation tips. |
| **Overlay Manager** | Modal & Screen Stack Hook | `TUI` | Manages keyboard focus and rendering priority across stacked modals and dialogs. |
| **Scroll Engine** | Terminal Scroll State & Indicator | `TUI` | Handles mouse-wheel and keyboard scrolling with visual top/bottom indicators. |
| **Error Handling UI** | Error Boundary & Warning Blocks | `TUI` | Catches React rendering crashes and formats server error payloads cleanly. |

---

## 7. Transport & Infrastructure

| Feature | Sub-Level / Component | Resides In | Description (One-Liner) |
| :--- | :--- | :--- | :--- |
| **WebSocket Server** | FastAPI WebSocket Transport | `Server` | High-performance full-duplex socket for real-time events, streams, and commands. |
| **WebSocket Client** | Reconnecting WebSocket Service | `TUI` | Manages connection lifecycle, auto-reconnect, and heartbeat with the server. |
| **Event Adapter** | Domain Event Serializer | `Server` | Translates internal domain events into standardized JSON event payloads. |
| **Raw Event Mapper** | Scenario & UI Event Dispatcher | `TUI` | Maps incoming server events to interactive UI blocks, cards, and state changes. |
| **Server CLI** | Click Command Line Interface | `Server` | Provides terminal commands to run the server (`serve`), inspect status, and list tools. |
| **User Profile Store** | Profile & Settings Persistence | `Server` | Persists user settings, theme preferences, and developer overrides in JSON storage. |
| **User Profile Service** | Client Profile Cache & Sync | `TUI` | Reads and writes user preferences locally with fallback to defaults. |
