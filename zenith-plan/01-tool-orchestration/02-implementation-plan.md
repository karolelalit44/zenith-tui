# Tool Orchestration — Implementation Plan

## Stage 1: Inventory and canonical metadata — DONE

- Inventory every built-in, MCP, background, LSP, and sub-agent tool.
- Add capability, risk, read-only, timeout, concurrency, and permission metadata to the base tool contract.
- Validate unique names, valid JSON schemas, bounded descriptions, and mode declarations at startup.
- Record current total schema tokens per provider/model as the benchmark (baseline: 1407 tokens / 19 tools on `cl100k_base`).

## Stage 2: Durable turn and invocation model

- Add `turn_runs`, `tool_invocations`, and `tool_results` persistence.
- Store large results in content-addressed blob storage and keep previews/checksums in SQLite.
- Add stable correlation IDs to every runtime event.
- Make prompt submission idempotent across websocket retries.

## Stage 3: Router and capability catalog — catalog done, router pending

- Catalog: 16 `CapabilityDescriptor`s including `tool_discovery`; compact descriptors cached by registry version (cache pending).
- Router (pending): deterministic direct-response rules for greetings and explicit non-workspace questions; structured model routing for ambiguous requests.
- Confidence thresholds: low-confidence direct answers may include a minimal read-only discovery set; mutating execution must never be inferred from weak routing alone.

## Stage 4: Selective schema execution — groundwork done

- On-demand discovery meta-tools implemented: `discover_capabilities` + `get_tool_definition`.
- `SchemaResolver` implements the bounded active schema set, LRU eviction, mode filtering, and schema-token accounting (wired into `ContextManager`).
- Reactive escalation preserved; WS `tools.list` now matches the loop's offered set.
- Remaining: capability→schema resolution driven by the intent router; native and compatibility provider adapters; remove request-time dependence on the full registry when the router is live.

## Stage 5: Scheduler and policy

- Centralize validation, approvals, cancellation, timeout, concurrency, retry, and result compaction.
- Define explicit policies for read, write, delete, command, network, MCP, and sub-agent operations.
- Ensure plan/read-only modes cannot reach mutating execution paths.

## Stage 6: Sub-agents and optimization

- Model child work as child `TurnRun` records rather than special untracked events.
- Enforce aggregate parent/child token, time, step, and concurrency budgets.
- Add routing quality evaluation and per-tool latency/success metrics.
- Tune catalog descriptions and schema bundles from recorded failures rather than prompt guesswork.
