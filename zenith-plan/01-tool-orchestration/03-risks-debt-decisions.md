# Tool Orchestration — Risks, Debt, and Decisions

## Key complications

- A model cannot invoke an ordinary tool whose schema was never exposed; lazy loading therefore requires a routing call or meta-tool, not prompt wording alone.
- Routing adds latency. The direct-response fast path and catalog caching must offset that cost.
- Different providers encode tools, forced choice, parallel calls, and streaming deltas differently.
- MCP servers may expose large or unstable catalogs and must be namespaced, filtered, versioned, and health-checked.
- Tool descriptions can become prompt injection surfaces when sourced externally.

## Existing debt to resolve

- Registry filtering mixes availability, mode, and MCP policy concerns.
- The agent loop owns routing, streaming, execution, compaction, recovery, and stopping logic.
- Invocation state is not normalized for reliable replay and analytics.
- The question tool uses process-global callback state.
- Tool results are embedded in conversational content and may be truncated without durable references.

## Decisions

- Use capability routing plus request-specific schemas; do not send the complete registry by default.
- Keep canonical internal tool schemas and translate at provider boundaries.
- Treat tool authorization as server policy, never as a model decision.
- Use bounded concurrency and budgets; no unbounded recursive agents.
- Store external/MCP descriptions as untrusted data and sanitize them before model exposure.
- Preserve an escape hatch that lets the model request an additional capability, with policy validation.

## Failure handling

- Router unavailable: fall back to a conservative minimal read-only set, never all mutating tools.
- Invalid/hallucinated call: reject, record, tell the model which offered tools are valid, and allow one correction.
- Tool timeout: cancel, persist partial diagnostics, and return a typed failure.
- Provider lacks tool support: answer directly or fail with a capability error; do not simulate unsafe execution.
- Reconnect during approval/tool execution: restore by invocation ID and do not duplicate execution.
