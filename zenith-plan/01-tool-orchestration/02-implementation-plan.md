# Tool Orchestration — Implementation Plan

## Stage 1: Inventory and canonical metadata

- Inventory every built-in, MCP, background, LSP, and sub-agent tool.
- Add capability, risk, read-only, timeout, concurrency, and permission metadata to the base tool contract.
- Validate unique names, valid JSON schemas, bounded descriptions, and mode declarations at startup.
- Record current total schema tokens per provider/model as the benchmark.

## Stage 2: Durable turn and invocation model

- Add `turn_runs`, `tool_invocations`, and `tool_results` persistence.
- Store large results in content-addressed blob storage and keep previews/checksums in SQLite.
- Add stable correlation IDs to every runtime event.
- Make prompt submission idempotent across websocket retries.

## Stage 3: Router and capability catalog

- Implement deterministic direct-response rules for greetings and explicit non-workspace questions.
- Implement structured model routing for ambiguous requests.
- Cache the compact capability catalog by registry version.
- Add confidence thresholds: low-confidence direct answers may include a minimal read-only discovery set; mutating execution must never be inferred from weak routing alone.

## Stage 4: Selective schema execution

- Resolve router capabilities to the smallest initial tool set.
- Allow controlled schema expansion when the model identifies a missing capability.
- Implement native and compatibility provider adapters.
- Remove request-time dependence on sending the entire registry.

## Stage 5: Scheduler and policy

- Centralize validation, approvals, cancellation, timeout, concurrency, retry, and result compaction.
- Define explicit policies for read, write, delete, command, network, MCP, and sub-agent operations.
- Ensure plan/read-only modes cannot reach mutating execution paths.

## Stage 6: Sub-agents and optimization

- Model child work as child `TurnRun` records rather than special untracked events.
- Enforce aggregate parent/child token, time, step, and concurrency budgets.
- Add routing quality evaluation and per-tool latency/success metrics.
- Tune catalog descriptions and schema bundles from recorded failures rather than prompt guesswork.
