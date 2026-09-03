# Tool Service

## Overview

How tools are declared, registered, invoked, and how their results are fed back to the model. This is a major over-engineering point in zenith.

### How opencode does it

- `tool/tool.ts` defines `Tool.Def { id, description, parameters (Schema), execute(args, ctx) }`.
- `tool/registry.ts` resolves the available tools for a given agent + model.
- `session/tools.ts` (`SessionTools.resolve`) converts registry tools into AI-SDK `tool()` entries, wiring:
  - `execute` â†’ decode args via `Schema.decodeUnknownEffect` â†’ on failure raise `InvalidArgumentsError` (which is fed back to model as tool result: "please rewrite input to satisfy schema").
  - Output truncation via a single `Truncate` service.
  - `metadata()` and `ask()` (permission) context helpers.
  - MCP tools are bridged into the same registry.
- `beforeToolCall` / `afterToolCall` hooks are the plugin points.
- Per-tool truncation: `tool/truncate.ts` + `truncation-dir` â€” output beyond a limit is truncated, the full output written to a file path, and the model told where to read it.

### How codex does it

- `ToolSpec { name, namespace, parameters (JsonSchema), output_schema }`.
- `ToolRouter` resolves a tool call to its runtime.
- `ToolCall { tool_name, call_id, payload, ... }` with `ToolPayload` variants (Function/ToolSearch/Custom).
- Namespaces: `functions:` (default), `collaboration:` (subagents), `_mcp_` (MCP).
- `execute_tool_call` runs write/edit/apply_patch/exec/shell.
- Parallel tool calls via `parallel_tool_calls: true`.
- No intent router, no dynamic tool discovery, no risk/cost/latency taxonomy. Permissioning is done separately (native sandbox + turn-granted permissions).

### What zenith has today

**Files (server/toolkit/):**
- `base.py` â€” `BaseTool` with heavy metadata: `capability_id`, `read_only`, `timeout_ms`, `concurrency_group`, `permission_scope`, `domains`, `risk_level`, `cost_class`, `latency_class`.
- `registry.py` â€” `ToolRegistry` with mode-gating, MCP allow-listing, param validation, middleware chain.
- `resolver.py` â€” `SchemaResolver`, dynamic discovery (`discover_capabilities`, `get_tool_definition`), `MAX_ACTIVE_TOOLS_PER_TURN = 12`, escalation via `request_tool`.
- `router.py` â€” `IntentRouter.classify` â†’ `IntentKind` (DIRECT_RESPONSE / READ_ONLY_DISCOVERY / EXECUTION_MUTATION), threshold 0.85.
- `executor.py` â€” `execute_tool`, validate, redact params/PII, build metadata, format output, validate rejection.
- `middleware/` â€” `hooks.py`, `logging.py`, `plan_write.py`, `safety.py`.

**Tools (server/toolkit/tools/):** file_read, file_write, file_edit, multi_edit, file_delete, glob, grep, list_dir, bash, background, job_output, job_kill, todo, mcp_tool, lsp_*, code_graph_tools, explore_tool, webfetch, websearch, _html_text.

**5-layer stack:** registry + resolver + router + executor + middleware. Each tool also carries a domain taxonomy (risk/cost/latency/capability).

### What is correct

- The tool idea itself and the individual tool implementations (read/write/edit/glob/grep/bash/etc.).

### What is wrong / over-engineered / incorrect / missing

**Over-engineered (remove):**
- `IntentRouter` â€” opencode/codex do not classify intent.
- `resolver.py` dynamic discovery (`discover_capabilities`, `get_tool_definition`, `MAX_ACTIVE_TOOLS_PER_TURN`). opencode/codex build the tool list statically per agent/model.
- The domain taxonomy (`risk_level`, `cost_class`, `latency_class`, `capability_id`, `concurrency_group`, `permission_scope`, `domains`). opencode/codex use a single `Permission.ask`/sandbox, not a metadata taxonomy.
- The middleware chain (hooks/logging/plan_write/safety) as a separate layer. Reduces to `beforeToolCall`/`afterToolCall` hooks + `permission.ask`.
- `EPHEMERAL_TOOL_WINDOW_SIZE`, `TOOL_DIGEST_MAX_CHARS` â€” ephemeral window and digest logic.

**Incorrect / missing:**
- No `InvalidArgumentsError`-style feedback for invalid args (opencode feeds "please rewrite input" back to the model).
- No unified truncation service (relies on heavy-output isolation + per-tool caps).
- Duplicate-call blocking / file-write-replay blocking / read-caching (in session_workspace) are not in opencode/codex.

## What we will do

Build a single tool abstraction: name, description, parameter schema, execute function.
- A registry resolves tools for the active agent/model (static list, not dynamic discovery).
- Parameters decoded/validated by the schema layer; invalid args fed back to the model as a rewrite request.
- Tool output truncated by one Truncate service; oversized output written to a file path and referenced.
- `beforeToolCall` / `afterToolCall` hooks.
- A Permission layer (`ask`) for gating.
- MCP tools bridged into the same registry.

### Decision (2026-08-31) — phased execution (Mars, module 03 owner)

Per `progress.md` §11 this runs additively in **Phase 1 (interface-lock, no removal)**;
the REMOVE list below is executed in **Phase 3** once consumers (02 prompt_sending, 01
turn/loop) and Jupiter's 23 (blocked on 03) may adopt the new shape. Phase 1 has therefore:
- **ADDED (interface-lock), in `server/toolkit/base.py`:**
  - `ToolDef` — opencode `Tool.Def` {name, description, parameters, execute} equivalent
    (docstring cross-refs opencode `tool/tool.ts` / codex `ToolSpec`).
  - `InvalidToolArgumentsError` + `decode_parameters()` — schema decode/validate that
    raises → "please rewrite input to satisfy schema", matching opencode
    `Schema.decodeUnknownEffect` -> `InvalidArgumentsError`.
  - `truncate_output()` — one unified Truncate service (single limit
    `MAX_TOOL_OUTPUT_BASELINE`, not the legacy tier taxonomy), returning
    `(kept, truncated)` so callers can persist the full payload and point the model at it.
  - `ToolDefResult` + `run_tool_def(tool, args, workspace_root, max_output_chars)` — the
    execution-resolve helper (opencode `SessionTools.resolve` intent): schema-decode args,
    feed `InvalidToolArgumentsError` back to the model on failure, execute, then truncate
    oversized text via `truncate_output`. Composes the whole decode→execute→truncate flow
    for a `ToolDef`.
  - Added `MAX_TOOL_OUTPUT_BASELINE` import only; no constants changed.
- **NOT removed yet (Phase 3):** `router.py` (IntentRouter), `resolver.py` dynamic
  discovery / `MAX_ACTIVE_TOOLS_PER_TURN`, domain/risk/cost/latency taxonomy,
  `middleware/` chain, `EPHEMERAL_TOOL_WINDOW_SIZE` / `TOOL_DIGEST_MAX_CHARS`.
  These are live-wired through `server/toolkit/executor.py` + registry today; do NOT
  delete during Phase 1.
- **LOCK:** CCS file `server/toolkit/base.py` held by Mars (module 03) during the
  additive edit; released on completion. No `constants.py` change made.

### Decision (2026-09-01) - Phase 2 production wiring (Mars)

- **LIVE:** `ToolRegistry.get_definition(name)` adapts an existing `BaseTool`
  registration to `ToolDef` without changing tool-owned modules.
- **LIVE:** `executor.execute_tool()` resolves the definition, decodes arguments
  with `decode_parameters()`, delegates mode/MCP permission checks plus existing
  before/after hooks to the registry, executes the tool, and applies exactly one
  `truncate_output()` before returning the existing `ToolResult` form.
- **Compatibility:** all callers retain the `execute_tool(...) -> (ToolResult,
  duration_ms)` signature; direct legacy `ToolRegistry.execute()` callers remain
  available while consumers migrate.
- **Validation:** editor diagnostics are clean for `registry.py`, `executor.py`,
  and focused Module 03 tests. A focused pytest run is blocked because this
  repository has no Dockerfile or Compose entrypoint and local execution is not
  permitted by the workspace runtime policy.


## What we will REMOVE
- `router.py` (IntentRouter)
- `resolver.py` (dynamic discovery, MAX_ACTIVE_TOOLS_PER_TURN, capability discovery)
- Domain/risk/cost/latency taxonomy
- `middleware/` chain (collapse to hooks + permission)
- `EPHEMERAL_TOOL_WINDOW_SIZE`, `TOOL_DIGEST_MAX_CHARS`
- Duplicate-call blocking / replay-blocking / read-cache (handled in session_state)

## Regex audit
| Regex | opencode/codex uses it? | Action |
|---|---|---|
| (none specific here) | â€” | â€” |

## Verification / signoff
- [x] Single Tool abstraction (additive `ToolDef` interface-locked in base.py)
- [~] Static registry (no dynamic discovery) — Phase 3 removal of resolver
- [x] Invalid args fed back as rewrite request (InvalidToolArgumentsError + decode_parameters)
- [x] Unified truncation service (truncate_output, single limit)
- [x] Execution-resolve helper (run_tool_def: decode → execute → truncate; invalid args fed back)
- [~] before/after hooks + permission.ask — Phase 3 collapse of middleware chain
- [~] MCP bridged into same registry — retained in legacy registry today
- [x] ruff + pytest (module tests, 13 base + 5 resolve = 18 new; core toolkit 115 regression green) for additive Phase-1 changes
- [x] Production executor uses ToolDef lookup -> decode -> existing gate/hooks -> execute -> truncate
- [~] Phase-2 focused pytest blocked by the Docker-only runtime policy; focused editor diagnostics pass

## Status: Interface-Locked (Phase 1 additive; Phase 2 executor wiring live); router/resolver/taxonomy/middleware removal pending Phase 3

---

## Module report (§9 template)

```
Module: 03 tool_service
Status change: Pending → Interface-Locked (Phase 1 additive; Phase 2 live wiring)
WHAT: Added the opencode Tool.Def-aligned contract to server/toolkit/base.py:
      ToolDef (name/description/parameters/execute), InvalidToolArgumentsError +
      decode_parameters (schema decode -> "please rewrite" feedback), and
      truncate_output (unified single-limit Truncate service), plus ToolDefResult +
      run_tool_def (the SessionTools.resolve-style decode->execute->truncate helper
      that feeds invalid args back to the model). `ToolRegistry.get_definition`
      now adapts every BaseTool registration to that contract, and `execute_tool`
      uses it in the production path before existing registry gates and one
      output truncation.
WHY: Mirrors opencode tool/tool.ts Tool.Def, session/tools.ts
      Schema.decodeUnknownEffect -> InvalidArgumentsError, and tool/truncate.ts.
      Codex equivalent: ref_code/codex/codex-rs/tools/src/tool_spec.rs
      (`ToolSpec`) and tool_executor.rs (`ToolExecutor::spec` + `handle`),
      which keep model schema and executable runtime coupled.
    FILES: server/toolkit/base.py, server/toolkit/registry.py,
      server/toolkit/executor.py, server/tests/test_tool_service.py,
      agent_engine_redesign/tool_service/feature.md
KEPT/REMOVED: additive interface added; NO removals this phase (router.py, resolver.py,
      taxonomy, middleware chain, ephemeral-window/digest constants all stay for Phase 3
      after consumers adopt the new shape).
EXPECTED BEHAVIOUR: model-triggered executions now perform ToolDef lookup, schema validation,
  existing mode/MCP + hook gates, BaseTool execution, and one output truncation before
  returning the unchanged ToolResult/event payload. Unknown tools, invalid arguments,
  returned failures, and unexpected exceptions remain model-facing ToolResult failures.
OUTCOME / TEST EVIDENCE: Added focused coverage for valid execution, unknown tool,
  schema-invalid arguments, ToolResult failures, unexpected exceptions, and truncation.
  Editor diagnostics PASS for all touched production/test files. Focused executable pytest is
  BLOCKED: no Dockerfile/Compose entrypoint exists and local execution is disallowed.
SHARED-FILE IMPACT: server/toolkit/base.py is CCS (owner 03). LOCK held by Mars during the
      additive edit then released; added MAX_TOOL_OUTPUT_BASELINE import only; no constant
      added/renamed. No other shared files touched.
DEPENDENCIES: locked handoff to Jupiter 12 and Mars 04/05/16/20/23: keep BaseTool registration,
  and use execute_tool for model-triggered calls. Phase 3 removes legacy router/resolver/taxonomy
  only after consumer searches prove the new path is exclusive.
```

Next: Phase 2 wires ToolDef/decode/truncate/run_tool_def into consumers; Phase 3 performs the REMOVE list
under coordination. Needs interfaces of consumers (01/02 loop) for full Done.
