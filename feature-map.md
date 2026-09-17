# Feature Inventory

| Feature | Sub‑Feature | Purpose | Dependencies |
|--------|-------------|---------|--------------|
| Terminal Chat UI | Slash Commands | Provide quick system actions via `/…` commands | Agent Loop, Session Management |
| Terminal Chat UI | Streaming Output | Deliver real‑time LLM responses to the terminal | Agent Loop, Session Management |
| Terminal Chat UI | Prompt History | Navigate and reuse previous messages | Session Management |
| Terminal Chat UI | Context Menu | Offer quick actions on past messages | Agent Loop |
| Agent Loop | Tool Registry | Discover and register available tools | LLM Provider |
| Agent Loop | Tool Execution Engine | Safely execute tools and capture output | Security & Access Control |
| Agent Loop | Result Handling | Normalize tool outputs for the LLM | LLM Provider |
| Agent Loop | Tool Safety Guardrails | Prevent malicious or harmful tool usage | Security & Access Control |
| Prompt Planning | Prompt Templates | Reusable prompt skeletons | LLM Provider |
| Prompt Planning | Dynamic Context Injection | Inject session history and tool docs into prompts | Session Management |
| Prompt Planning | Plan Generation | Generate LLM‑driven action plans | LLM Provider |
| LLM Provider | Provider Registry | Register and switch LLM services | – |
| LLM Provider | Streaming Support | Receive partial tokens from LLMs | – |
| LLM Provider | Error Handling | Retry logic and back‑off for provider calls | – |
| Session Management | Session Store | Persist conversations and state | Storage Layer |
| Session Management | Compaction | Clean old or unused sessions | Storage Layer |
| Session Management | Export/Import | Backup or share sessions | Storage Layer |
