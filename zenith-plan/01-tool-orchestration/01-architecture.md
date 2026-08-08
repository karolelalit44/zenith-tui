# Tool Orchestration — Architecture

## Components

- `TurnOrchestrator`: owns a turn from accepted prompt through completion/cancellation.
- `IntentRouter`: returns `answer`, `clarify`, `plan`, or `execute`, confidence, risks, and capability hints.
- `CapabilityCatalog`: compact descriptors grouped by workspace discovery, read/search, edit, execution, VCS, web/MCP, task, and sub-agent domains.
- `ToolCatalog`: loads full tool definitions and schemas only for selected capabilities.
- `ToolPolicyEngine`: evaluates mode, workspace, permission, risk, user decision, and provider restrictions.
- `ToolScheduler`: enforces concurrency groups, timeouts, cancellation, ordering, and resource budgets.
- `InvocationRepository`: persists calls and result references.
- `ProviderToolAdapter`: translates canonical tool contracts into provider-specific request/response formats.

## Contracts

```text
CapabilityDescriptor
  id, name, short_description, domains[], search_terms[]
  risk_level, read_only, cost_class, latency_class

ToolDefinition
  name, capability_id, description
  input_schema, output_schema, modes[]
  permission_scope, concurrency_group, timeout_ms

IntentDecision
  action, confidence, rationale_code
  capability_ids[], missing_information[], risk_flags[]

ToolInvocation
  id, session_id, turn_run_id, parent_invocation_id
  tool_name, arguments_json, status, approval_state
  attempt, started_at, completed_at, result_ref, error_code
```

## Request flow

1. Persist prompt and create a `TurnRun` with an idempotency key.
2. Apply deterministic fast paths for empty/greeting/explicit command inputs.
3. Run the lightweight router with no full tool schemas.
4. If `answer`, call the response model without tools.
5. If `clarify`, create a clarification thread and stop execution.
6. If `plan` or `execute`, resolve capability IDs to a bounded schema set.
7. Assemble context and call the provider through `ProviderToolAdapter`.
8. Validate all returned calls against the exact offered set and policy snapshot.
9. Request approval when required; otherwise schedule safe independent calls concurrently.
10. Persist compact results, append canonical tool messages, and continue until terminal state.

## Lazy-loading strategy

Tools are loaded on demand to keep per-prompt schema tokens small. Implemented:

- Two always-on discovery meta-tools: `discover_capabilities` (compact catalog of capabilities/tools) and `get_tool_definition('<name>')` (full schema + metadata). When the model requests a definition, the next provider request includes that tool's schema.
- `SchemaResolver` (`server/toolkit/resolver.py`) tracks the bounded active schema set per run: seed = mode core tools + discovery meta-tools, expansion on `get_tool_definition` or escalation, capped at `MAX_ACTIVE_TOOLS_PER_TURN` with LRU eviction that always retains the discovery tools.
- Schema tokens are counted in the context budget (`ContextManager.set_aux_tokens`) so summarization reflects offered tools.
- Reactive escalation remains: a registered-but-unoffered tool guessed by the model is promoted into the active set.
- WS `tools.list` advertises exactly the same offered set as the loop (mode core + discovery meta-tools).

Remaining:

- **Dynamic schema mode:** intent router selects capabilities up front, then the first request receives only the resolved schemas.
- **Static compatibility mode:** expose only meta-tools; after selection, start a new provider request with resolved schemas.
- Capability caching by registry version.

Never represent unavailable tools in the prompt as executable.

## Safety and scheduling

- Read-only tools may run concurrently when they do not share a constrained resource.
- Mutating tools serialize by workspace unless declared transaction-safe.
- Shell, deletion, external writes, and credential access require explicit policy outcomes.
- Cancellation propagates from turn to scheduler to subprocess/job.
- Retries require idempotency classification; mutating tools do not retry automatically without a safe token.
- Sub-agents receive scoped capabilities, budgets, workspace roots, and a parent run ID.
