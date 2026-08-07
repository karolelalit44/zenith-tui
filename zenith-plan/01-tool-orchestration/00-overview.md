# Tool Orchestration — Overview

## Objective

Make tool use automatic, selective, provider-aware, observable, and safe. Simple conversation must use no tools; repository work must discover and invoke the necessary capabilities without user selection.

## Current state

- `ToolRegistry` stores concrete tools and can filter schemas by mode and MCP allowlists.
- The agent loop constructs allowed schemas before the model call and executes calls through middleware.
- Tools already cover filesystem, search, editing, shell, LSP, MCP, jobs, questions, todos, and sub-agents.
- Prompt instructions tell the model to answer general queries directly, but there is no explicit intent/capability routing stage.
- Schema selection is mode/config driven, not request driven. Cost, latency, and schema-token impact are not first-class selection inputs.
- Tool execution records are mainly events/messages rather than durable, queryable invocation entities.

## Scope

- Capability catalog and searchable tool metadata.
- Prompt intent routing and request-specific schema loading.
- Provider-specific tool calling compatibility.
- Safe execution, permissions, concurrency, budgets, retries, cancellation, and sub-agents.
- Durable invocation records and metrics.

Out of scope for the first release: autonomous third-party plugin installation, remote multi-tenant workers, and unbounded agent swarms.

## Success criteria

- Greetings and knowledge questions add zero tool schemas to the final response path when routing confidence is high.
- Codebase requests select only the smallest capability set needed to begin, with later expansion allowed.
- No unknown or disallowed tool can execute even if the model hallucinates a call.
- Tool calls, approvals, results, errors, durations, and token overhead survive restart and session resume.
- Provider fallbacks preserve behavior when native dynamic tool calling is unavailable.

## Dependencies

- Versioned turn/event contracts from persistent sessions.
- Context budgets from context optimization.
- Approval and clarification boundaries.
- Cross-cutting tracing, security, and cost metrics.
