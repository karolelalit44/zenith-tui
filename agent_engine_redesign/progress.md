# AI Engine Redesign — Master Progress & Parallel-Work Coordination

> **Authoritative operating document.** All modules/features in `agent_engine_redesign/`
> are implemented by **multiple agents working in parallel**. This file defines the
> module inventory, the dependency graph, the file-ownership map, the claim/lock
> protocol, the shared-file access rules, the status lifecycle, the validation
> gates, and the definition-of-done. **Read it fully before claiming any module.**

---

## 0. Scope (user directive)

For now we fix ONLY zenith's **existing** modules and make them **workable**, while
replicating the behavior / underlying logic of the reference engines **opencode**
and **codex**. NEW or advanced features — **skills, MCP/LSP, permissions,
subagents-orchestrator** — are **OUT OF SCOPE** (their design docs remain in the
folder for reference but are NOT active work). Keep the current `explore` tool as-is.

**Hard rules (never break, for every agent):**
- Do **NOT** commit any changes and do not use Git Commands.
- Do **NOT** add new advanced/module features outside the in-scope list.
- Preserve the WebSocket JSON-RPC transport boundary the TUI depends on (only change
  event *content* via the event-adapter, never break TUI compatibility).
- Fix first; remove core function only when a module's feature doc says to REMOVE it.

---

## 1. Story: From user typing to response delivery (architecture map)

```
User types prompt
  → prompt_sending  (build parts, resolve file/agent attachments)
    → context       (assemble system prompt + fragments + history)
      → turn/loop   (stream LLM, decide continue/stop/compact)
        → tool_service     (tool registry, schema decode, dispatch)
          → file_operations  (read/write/edit, mutation queue)
          → command_runner    (PTY exec, live output, wait)
            → command_output_response (capture, truncate, stream back)
          → thinking_reasoning  (reasoning parts, delta merge)
        → markdown_render  (assistant text → rendered output)
      → transport_event_contract (WebSocket events → TUI)
    → session_state (persist turn, store parts)
      → todo (todo tool)
```

---

## 2. Module inventory, status, dependency graph & parallel lanes

`Dep` = modules whose consumers depend on this module. `Needs` = modules this module needs done first (or a stable interface to).

| # | Module | Folder | Status | Priority | Effort | Needs | Blocked-by |
|---|--------|--------|--------|----------|--------|-------|-----------|
| 01 | turn/loop | `turn/` | Interface-Locked | P0 | XL | 02,03 | — (first consumer) |
| 02 | prompt_sending | `prompt_sending/` | In-Progress | P0 | M | 15 | 01 |
| 03 | tool_service | `tool_service/` | Interface-Locked | P0 | L | — | — |
| 04 | file_operations | `file_operations/` | Interface-Locked | P0 | M | — | 03 |
| 05 | command_runner | `command_runner/` | Interface-Locked | P0 | L | — | 03 |
| 06 | context | `context/` | Interface-Locked | P1 | L | 13,15 | 02 |
| 07 | session_state | `session_state/` | Interface-Locked | P1 | M | — | 01 |
| 08 | thinking_reasoning | `thinking_reasoning/` | Interface-Locked | P1 | S | 13 | 01 |
| 09 | markdown_render | `markdown_render/` | Interface-Locked | P1 | M | — | 08 |
| 10 | transport_event_contract | `transport_event_contract/` | Review | P0 | M | — | 01,09 |
| 11 | subagents_orchestrator | `subagents_orchestrator/` | **OUT OF SCOPE** | — | — | — | — |
| 12 | todo | `todo/` | Review | P2 | S | — | 03 |
| 13 | provider_layer | `provider_layer/` | Interface-Locked | P0 | L | — | — |
| 14 | config_management | `config_management/` | Interface-Locked | P1 | M | — | — |
| 15 | prompts | `prompts/` | Interface-Locked | P0 | M | 13 | — |
| 16 | workspace_repo_map | `workspace_repo_map/` | Interface-Locked | P1 | L | — | 03 |
| 17 | skills | `skills/` | **OUT OF SCOPE** | — | — | — | — |
| 18 | mcp | `mcp/` | **OUT OF SCOPE** | — | — | — | — |
| 19 | lsp | `lsp/` | **OUT OF SCOPE** | — | — | — | — |
| 20 | web_tools | `web_tools/` | Interface-Locked | P1 | M | — | 03 |
| 21 | storage | `storage/` | In-Progress (Blocked) | P2 | M | — | 07 |
| 22 | permissions | `permissions/` | **OUT OF SCOPE** | — | — | — | — |
| 23 | toolkit_helpers | `toolkit_helpers/` | In-Progress (Blocked) | P1 | M | — | 03 |

### Parallel lanes (what can run concurrently)
Agents may run these **lanes in parallel**; keep each module's files to its lane (see §4).

- **Lane A (loop core):** 01 → 02 → 10 (serial within lane; 10 needs 01/09).
- **Lane B (tools):** 03 → {04, 05, 16, 20} (tool platform first, then dependent tools).
- **Lane C (context & model):** 13 → 15, then 06; 08 → 09.
- **Lane D (state & infra):** 07 → 21; 14; 23; 12.
- **Independent, can start now:** 03, 13, 14, 07, 12, 21, 23 (no upstream).

**Rule:** a module whose `Blocked-by` lists a module is in a different lane may begin
its **design/interface** work immediately, but must NOT edit code a blocked-on module
owns until that module's interface is declared stable (§3 transition to `Interface-Locked`).

---

## 3. Status lifecycle (state machine)

Every module moves through these states. **Only one agent owns a module at a time**
(move it to `In-Progress` when you claim it).

```
Pending ──claim──▶ In-Progress ──interface done──▶ Interface-Locked
   ▲                    │                               │
   │                    └──implement + self-test──▶ Review ──▶ Done
   └──────────── unclaim (release) ◀───────────────────────┘
```

| State | Meaning | Who can set it |
|---|---|---|
| `Pending` | Not started; available to claim | anyone |
| `In-Progress` | Claimed; agent actively editing this module's files | claiming agent only |
| `Interface-Locked` | Public API/contracts decided & stable; dependents may code against it, but only the owner edits the files | owner only |
| `Review` | Implementation done; self-tested; awaiting review | owner |
| `Done` | Passed all validation gates in §7; accepted by reviewer | reviewer |
| `Blocked` | Waiting on another module/decision; state is `In-Progress` + note | owner |
| `OUT OF SCOPE` | Not active work | coordinator only |

**Claim protocol (must follow):**
1. Before editing, move the module's Status to `In-Progress` and list yourself as **Owner** in §8.
2. Do NOT claim two modules at once unless they are independent leaf modules (S effort).
3. If a module is `In-Progress` by another agent, do NOT edit its owned files. Work elsewhere or wait.
4. When done, set `Review`, fill the **report template** (§9) in the module's feature doc or in §8, and notify.

---

## 4. File-ownership map (who may edit which files)

An agent may **only** modify files in its module's ownership set, **plus**:
- files it owns via a separate claim, or
- adding NEW files under its own module folder in `agent_engine_redesign/` (design docs) or a scoped `server/` subpackage it owns.

Files NOT in any ownership set (shared) fall under §5 rules.

| # Module | Owned files (authoritative editor) |
|---|---|
| 01 turn/loop | `server/agents/loop.py`, `recovery.py`, `validation.py`, `loop_detection.py` |
| 02 prompt_sending | `server/agents/prompt_executor.py` |
| 13 provider_layer | `server/providers/base.py`, `llm_provider.py`, `registry.py`, `parser.py`, `token_counter.py`, `validation.py`, `server/api/provider_validation.py`, `validation_state.py`, `server/agents/provider_adapters.py` |
| 15 prompts | `server/agents/prompts.py` |
| 03 tool_service | `server/toolkit/base.py`, `registry.py`, `executor.py`, `resolver.py`, `router.py`, `discovery.py`, `schema_metrics.py`, `registry_validation.py`, `server/toolkit/middleware/hooks.py`, `logging.py`, `plan_write.py` |
| 04 file_operations | `server/toolkit/tools/file_read.py`, `file_write.py`, `file_edit.py`, `file_delete.py`, `multi_edit.py`, `glob.py`, `grep.py`, `list_dir.py` |
| 05 command_runner | `server/toolkit/tools/bash.py`, `background.py`, `job_output.py`, `job_kill.py`, `server/shell_runner.py` |
| 06 context | `server/agents/context.py`, `compaction.py`, `compaction_service.py`, `running_summary.py`, `summarizer.py` |
| 07 session_state | `server/domain/session.py`, `domain/domain.py`, `agents/run_state.py`, `agents/session_state.py`, `agents/session_workspace.py`, `server/sessions/service.py` |
| 08 thinking_reasoning | `server/agents/llm_stream.py` |
| 09 markdown_render | `server/providers/responder.py` |
| 10 transport_event_contract | `server/api/server.py`, `websocket.py`, `handlers.py`, `protocol.py`, `schemas.py`, `middleware.py`, `startup.py`, `shutdown.py`, `server/domain/events.py`, `message.py`, `errors.py`, `hooks.py` |
| 12 todo | `server/toolkit/tools/todo.py`, `server/agents/todo_state.py` |
| 14 config_management | `server/config/constants.py`, `settings.py`, `env.py`, `loader.py`, `providers.py` (see §5 — constants.py is CCS) |
| 16 workspace_repo_map | `server/workspace/*.py`, `server/toolkit/tools/code_graph_tools.py` |
| 20 web_tools | `server/toolkit/tools/webfetch.py`, `websearch.py`, `_html_text.py` |
| 21 storage | `server/storage/*.py`, `server/sessions/export.py`, `import_service.py` |
| 23 toolkit_helpers | `server/toolkit/auto_lint.py`, `catalog.py`, `command_result.py`, `command_safety.py`, `digest.py`, `param_normalizer.py`, `path_validator.py` |

> `main.py`, `server/toolkit/tools/__init__.py` (tool registration index), and `server/toolkit/__init__.py` are **coordinator-owned** (see §5, CCS).

---

## 5. Shared / cross-cutting files (concurrency-critical)

These files are read or symbol-wise edited by MANY modules. Treat them as **coordination-controlled (CCS)**:

| Shared file | Touched by modules | Rule |
|---|---|---|
| `server/config/constants.py` | 01,03,04,05,06,07,08,10,12,13,14,16,20,23 | **Additive-only, single-owner-at-a-time.** Edit constants under a clear `# --- module N ---` block. Never rename/retype an existing constant another module reads without a $7 gate. **Owner:** 14 coordinates a batch-edit queue. |
| `server/domain/events.py` (`EventKind`) | 08,09,10,12,01 | **Append-only enum additions.** Do NOT delete/reorder existing `EventKind` values (TUI maps by name). New kinds appended with explicit comments. |
| `server/api/handlers.py` | 01,02,10 | **Interface owner:** 10. 01/02 may only change handler internals after `Interface-Locked`; coordinate the `execute`/`stream` signature. |
| `server/toolkit/tools/__init__.py` (registry) | 03,04,05,16,20,12 | Append-only registration entries; one line per tool; never reorder. |
| `server/toolkit/base.py` (`BaseTool`/`ToolResult`) | 03 + all tools | Owner **03**. Other modules may extend `ToolResult` fields only additively via review. |
| `server/storage/session_store.py`, `session_file.py` | 07,21,06,10 | Owner **21** for file format; **07** for Session lifecycle. Coordinate the JSONL record schema. |
| `server/domain/message.py`, `domain/domain.py` | 07,10,02 | Coordinate via 10 (transport) / 07 (session). |
| `server/providers/` interface | 13,06,08,09 | Owner **13**. 08/09 consume deltas; coordinate the streamed `Event` shape. |

**Hard concurrency rules:**
1. **One writer per shared file at a time.** Before editing any CCS file, claim it: add a `LOCK: <file> by <agent> (module N)` note in §8 and an `// @lock module-N` comment at the top of the file. Release when done.
2. **Additive over delete** for shared constants/events/enums. Delete/retype only with an explicit review gate (§7 item for the module that owns the semantic concept).
3. **Do not reformat / reorder** blocks you are not changing in a shared file (avoids noisy merge conflicts).
4. **Small, atomic diffs** on shared files. Split large edits into multiple small sequential edits on a shared file.

---

## 6. Parallel-write / collaboration protocol (no git)

**No build tools are run and no git operations are used.** All coordination happens
through the claim ledger (§8) and the shared-file lock rules (§5). Changes are made
in place on the working tree; do not commit, branch, push, stash, revert, or run any
git command.

1. **Claim before you edit.** Move the module to `In-Progress` in §8 and take any
   shared-file `LOCK:` (§5) before writing. One writer per module at a time.
2. Edit **only** the files owned by your module (§4) and/or add new files under your
   own module in `agent_engine_redesign/`.
3. **Small, atomic edits** per file. Do not reformat/reorder blocks you are not
   changing. This keeps diffs reviewable and avoids clobbering another agent's work.
4. Respect active locks: if §5/§8 shows `LOCK: <file> by <agent>`, do not edit that
   file until released. Edit a different file or wait.
5. Run only your module's validation gates (§7). Do not run any global build/publish/
   deployment or git commands.
6. When finished, set `Review`, fill the §9 report, and **release** all locks you hold.
7. If another agent needs a file you own, coordinate via §8 — hand it over explicitly,
   never let both edit at once.

**Dependency rule:** if your work depends on another module, don't copy their code.
Wait for the upstream module to reach `Interface-Locked` and code against the declared
interface (its feature doc), not against its internals.

---

## 7. Validation gates (definition of done — per module)

A module is `Done` only when **all** of these pass. Gate = PASS/FAIL recorded in §8.

- [ ] **G1 Unit/behaviour:** module's feature-doc acceptance behaviours implemented; new tests added in `server/tests/test_<module>.py`.
- [ ] **G2 Suite:** `python -m pytest server/tests/ -q` still passes (no regressions, no shared-file conflicts introduced).
- [ ] **G3 Lint:** `ruff check server/ && ruff format --check server/` clean (or repo's configured lint).
- [ ] **G4 Interface:** any public signatures/EventKind additions are declared in the module feature doc and the `Transport Contract` is honored.
- [ ] **G5 TUI compat:** no TUI-breaking change; if `domain/events.py` or `api/websocket.py` changed, TUI `tui/src/types/scenario.ts` mapping still holds (or adapter added).
- [ ] **G6 Scope:** no out-of-scope new features; no new advanced modules; no unrelated file changes.
- [ ] **G7 Shared-file:** no stale `LOCK:` on files you own; all your CCS edits are additive where required.
- [ ] **G8 Clean working tree:** your edits are self-contained (no leftover locks, no half-finished files); the modules you touched run correctly.

**Dependency gate for dependents:** a downstream module may begin coding against an
upstream only after that upstream is `Interface-Locked` (contracts stable), and may
finish only after upstream is `Done`.

---

## 8. Claim & coordination ledger

> This is where live coordination state lives. Update it whenever you claim/release
> a module, lock a shared file, or change a status. Keep it accurate — it is the
> single source of truth for "who is doing what right now."

| Module | Owner (agent) | Status | LOCK (files held) | G1–G8 gate results | Notes |
|---|---|---|---|---|---|
| 01 turn/loop | Jupiter | **Interface-Locked** | — | G1 PASS (3 new tests); G3 clean; G2 PASS (full suite green except pre-existing heavy-isolation failure) | P0 XL; Lane A; consumer of 02/03. LOCKED interface = `SimpleLoop.process_prompt(prompt, session_id, history, mode, skills_section, plan_context, model_override) -> AsyncIterator[Event]` (mirrors AgentLoop; emergent stop / tool-then-stop / DOOM_LOOP guard; reuses context/stream/exec/compaction). Phase A removed repo-map plumbing from the active PromptPath/SimpleLoop path. AgentLoop retains an inert `repo_map` compatibility argument until its Phase B retirement. Salvage, manifest, and write-replay cleanup remain Phase 3 in the legacy loop. |
| 02 prompt_sending | Jupiter | **Done** | — | G1 PASS (6 new tests); G3 clean; J1 wiring PASS (25 tests in test_prompt_overrides.py incl. new TestLoopWiring); J1 regression fix PASS (test_token_usage_occupancy + test_event_bus_wiring green); J2 focused pass (37 prompt-path/executor/delegation tests); J3 combined regression PASS (95 touched prompt/config/todo/event/storage tests); J4 focused prompt batch PASS after direct PromptPath attachment resolution; J5 PASS (delegation fork removed, 37 prompt-path/executor tests green, Ruff clean); latest combined review batch PASS (62 tests) | P0 M; needs 15 (done) + 01 (locked). LOCKED interface = `server/agents/prompt_path.py` (`PromptPath.send(content, session_id, history, mode, skills_section, plan_context, model_override, repo_map, attachments) -> AsyncIterator[Event]`) + `resolve_user_parts` (resolves text/file/folder/inline/agent/MCP parts at prompt time) + `build_clean_system_context` (module-15 tagged surface). Single path, no delegation branching. `PromptExecutor._execute` now always routes the turn through `PromptPath`, so the remaining executor surface is the normal prompt path plus the existing plan-ready persistence and SimpleLoop seam. **J2/J5:** direct `PromptPath` attachment resolution is live; the legacy captain/crewmate fork is removed; focused prompt batch and Ruff are green. **J1-regression fixes:** two tests that relied on `prompt_executor.RecoverableAgentLoop` (which J1 removed from that module) updated to patch the new `prompt_executor.SimpleLoop` — `test_token_usage_occupancy.py` (token-recording path) + `test_event_bus_wiring.py` (C-F02 summarized-before-terminal ordering) both green |
| 03 tool_service | Mars | Interface-Locked | — (LOCK on server/toolkit/base.py released) | G1 focused editor diagnostics PASS; G3 focused editor diagnostics PASS; G4/G5/G6/G7/G8 PASS; G2 executable pytest PASS (venv: test_tool_service.py, 25 passed) | P0 L; Lane B; **LOCKED Phase 2 interface:** `ToolRegistry.get_definition(name) -> ToolDef | None`; `execute_tool` now uses ToolDef lookup -> `decode_parameters` -> legacy registry mode/MCP permission and hook gates -> execute -> one `truncate_output`, returning event-compatible `ToolResult`. Consumers 01/02 already use `execute_tool` without migration; 04/05/16/20 may retain BaseTool registration. Resolver/taxonomy/middleware removal remains Phase 3. **Ledger update for Jupiter 12 and downstream tool owners:** stable adapter is live; do not bypass `execute_tool` for model-triggered execution. |
| 04 file_operations | Mars | Interface-Locked | — | G1/G2 PASS (venv: Phase A tool/context/config/workspace/prompt/API suite, 168 passed); G3 focused diagnostics PASS; G4/G5/G6/G7/G8 PASS | P0 M; Module 16 consumer migration complete: glob/grep now use RipgrepBackend when available, with a direct-venv Python fallback that preserves ZenithIgnoreMatcher filtering for `.zenithignore` compatibility. Phase A completed the `multi_edit` removal: implementation, registration, parameter normalization, mutation tracking, and obsolete success scenarios are gone. File mutation contract remains exact-match `file_edit`; replay-block cleanup remains Phase B. |
| 05 command_runner | Mars | Interface-Locked | — | G1 focused editor diagnostics PASS; G3 focused editor diagnostics PASS; G4/G5/G6/G7/G8 PASS; G2 executable pytest PASS (venv: test_shell_streamed.py + TestBashTool/TestBackgroundJobs slice, 10 passed) | P0 L; **LOCKED Phase 2 interface:** foreground `BashTool.execute` streams to completion via `run_shell_command_streamed`; explicit `run_in_background` remains the only background path. `run_shell_command_streamed` remains the additive live-output primitive with dedicated shell-stream tests. **Handoff to Jupiter 01/10:** consume and forward those chunks through the event adapter to enable TUI live output; Module 05 cannot edit that transport path. Background/job_output tools remain Phase 3; the false-success heuristic and auto-background fallback were removed. |
| 06 context | Mars | Interface-Locked | — | G1/G2 PASS (venv: test_context + test_context_fragment, 30 passed); G3/G4/G5/G6/G7/G8 PASS | P1 L; **LOCKED Phase 2 contract:** Module 15 supplies ordered composed system sections to the live SimpleLoop; ContextManager preserves current build-message and compaction behavior. ContextFragment provides the tagged-slot representation without changing the WebSocket/TUI boundary. Tier/scoring/running-summary removals remain Phase 3. **Handoff to 08/09/02:** preserve ContextManager message shape until coordinated fixed-slot replacement. |
| 07 session_state | Mars | Interface-Locked | — | G1:G3:G4:G5:G6:G7:G8 PASS; G2 PASS (Phase A session/prompt/persistence/API slice, 61 passed) | P1 M; Phase A completed `SessionState` removal. Sessions persist only `run_status` (`busy`/`idle`) and `is_active`; service, import/export, API resume, simulated WebSocket paths, and storage summaries use the status-only contract. `session_workspace` removal remains Phase B. |
| 08 thinking_reasoning | Mars | Interface-Locked | — | G1/G2 PASS (venv: test_reasoning_stream + test_parts_render + test_event_adapter, 29 passed); G3/G4/G5/G6/G7/G8 PASS | P1 S; locked delta-merged ReasoningPart contract remains live. The legacy partial-thinking chunking path has been removed from stream_completion; final THINKING events still exist until the module-09/10 part transport fully replaces them. Module 09/10 transport handoff stays unchanged because Module 10 owns the event adapter boundary. |
| 09 markdown_render | Mars | Interface-Locked | — | G1/G2 PASS (venv: test_reasoning_stream + test_parts_render + test_event_adapter, 29 passed); G3/G4/G5/G6/G7/G8 PASS | P1 M; additive ContentPart/PartKind + part factories + render_parts_text + parts_message (data.parts on MESSAGE kind, data.text fallback) in responder.py; tool output now uses the shared truncation service, and invented-kind removal is still deferred to Phase 3 (see report) |
| 10 transport_event_contract | Jupiter | **Done** | — | G1 PASS (13 tests in test_event_adapter.py); G3 PASS (focused Ruff clean); G5 PASS (additive, TUI kinds untouched); G6 PASS; **Phase-2 wiring PASS (J1 swap inner loop: 25 test_prompt_overrides + adapter tests green; ruff clean on prompt_executor + test)**; latest combined review batch PASS (62 tests); transport cleanup batch PASS (139 tests) | P0 M; review validation complete. Needs 01,09 (both Interface-Locked). Phase-1 additive DONE: `server/api/event_adapter.py` — `adapt_part`/`adapt_parts`/`iter_client_events` map module-09 `ContentPart` (text/reasoning/tool_call/tool_result/error) onto TUI `EventKind`s (message/thinking/tool_call/tool_result/error), full truncated tool output (no 5K preview). LOCKED interface = `iter_client_events(AsyncIterator[Event]) -> AsyncIterator[Event]`, accepting `data.parts` as either serialized part mappings or typed `ContentPart` instances and fanning them out in order. **Phase-2 DONE (Jupiter J1):** `iter_client_events` now consumed in `server/agents/prompt_executor.py` around the module-01 `SimpleLoop.process_prompt` stream (swap-inner-loop lane). Because SimpleLoop emits no `data.parts` yet, the adapter is a faithful pass-through today; it becomes the forward-compatible boundary for Phase-3 part re-expression. Invented-kind removal completed for the unused enum values; remaining TUI-consumed event kinds are retained. **Handoff Mars 08/09 → Jupiter 10:** emit a MESSAGE with `data.parts` containing serialized or typed module-09 `ContentPart`; adapter preserves TUI event names. |
| 12 todo | Jupiter | **Done** | — | G1 PASS (24 focused tests); G3 PASS (focused Ruff clean); G4 PASS (registered ToolDef write/list/remove); G6:G8 PASS; latest combined review batch PASS (62 tests) | Plain checklist tool (write/list/remove) with a session-scoped store; the registered Module 03 ToolDef adapter was validated end-to-end. No registry/base edits. **Handoff Jupiter 12 → Mars 03:** keep the existing `ToolRegistry.get_definition("todo")` adapter and `execute_tool` path; no integration action is required. |
| 13 provider_layer | Mars | Interface-Locked | — | G1/G2 PASS (venv: test_providers + test_sampling_kwargs, 28 passed); G3/G4/G5/G6/G7/G8 PASS | Lane C; **LOCKED Phase 2 interface:** `LLMProvider.capabilities` resolves `ModelCapabilities` from the catalog and configured `reasoning_effort` is forwarded in live completion kwargs. A temporary direct-venv `litellm` stub was used for the focused check because the real package is not installed in the workspace venv. Parser/sampling/validation removals remain Phase 3. **Handoff to 15/06/08:** consume provider capabilities and effort through this contract, not model-tier prompt injection. |
| 14 config_management | Jupiter | In-Progress (Blocked) | — | G1 PASS (14 focused tests); G3 PASS (focused Ruff clean); G4 PASS (typed defaults→storage→environment→caller precedence); G6:G8 PASS | `load_config()` is the verified live entry point for startup, handler reload, and WebSocket reload. It now preserves caller `workspace_root` and applies all declared typed scalar `ZENITH_*` overrides at call time, after storage and before caller overrides. `AGENT_MODES` now exposes only BUILD/PLAN/READ_ONLY; the crewmate-specific config entry and unused field were removed. **Handoff Jupiter 14 → all consumers:** use `load_config()` for live reload; do not rely on import-time `AppSettings` defaults for environment changes. Remaining constants redistribution still needs CCS + Mars resolver coordination. |
| 15 prompts | Mars | Interface-Locked | — | G1/G2 PASS (venv: test_prompts_template + test_prompt_overrides, 44 passed); G3/G4/G5/G6/G7/G8 PASS | P0 M; **LOCKED Phase 2 interface:** `SimpleLoop` constructs its live system prompt with `default_template_sections` + `compose_system_context`. Restored missing `server/prompts/templates/plan.md`, matching the legacy plan instruction body and keeping plan-mode templates editable. Legacy AgentLoop constants remain Phase 3. **Handoff to 06:** system prompt sections are a stable ordered list of strings. |
| 16 workspace_repo_map | Mars | Interface-Locked | — | G1/G2 PASS (venv: Phase A tool/context/config/workspace/prompt/API suite, 168 passed); G3/G4/G5/G6/G7/G8 PASS | P1 L; Phase A completed tree-sitter repo-map/code-graph removal: implementation files and dependencies are deleted; context injection, WebSocket method, configuration, and delegation graph enrichment are removed. Supported workspace discovery remains glob, grep, LSP, and native ignore matching. Legacy AgentLoop carries an inert argument until Phase B retirement. |
| 20 web_tools | Mars | Interface-Locked | — | G1/G2 PASS (venv: test_web_tools.py, 21 passed); G3/G4/G5/G6/G7/G8 PASS | P1 M; **LOCKED Phase 2 interface:** `WebfetchTool.execute` uses pure `fetch_page` -> `FetchResult` conversion and returns the existing TUI-compatible ToolResult shape. No extract/model pass exists in production. Websearch provider abstraction and MCP work are deferred as out of current scope. **Handoff to 03/01/02:** continue invoking webfetch through `execute_tool`; no transport migration required. |
| 21 storage | Jupiter | In-Progress (Blocked) | — | Re-evaluated: migration partially complete; append-only/atomic path unchanged; efficiency scaffolding trimmed (70 focused provider/storage tests, Ruff clean) | Modules 07/10/16/13/06 now expose stable interfaces. The invented search/workspace stores were removed from the runtime path and session search now scans the real session/message repositories directly. The catalog_compat compatibility path was collapsed into catalog_store and deleted. Keep session JSONL/session_file/atomic/profile/provider config/builtin seed unchanged. The safe slice completed here removes placeholder `waste_ratio`/`summarization_count` fields from `get_efficiency()` and deletes the dead search/workspace store modules. Remaining catalog rename / seed-merge cleanup still needs 13/06/10 coordination. |
| 23 toolkit_helpers | Jupiter | In-Progress (Blocked) | — | G1 PASS (39 focused catalog/helper tests); G3 clean; G2 PASS (no new failures — only pre-existing heavy-isolation + Mars's workspace_search failures); migration re-evaluated BLOCKED | Phase 1 additive DONE: `decode_params_with_schema` (param_normalizer.py, schema-based decode with normalize_file_params fallback); `is_destructive_write`/`is_destructive_delete` + Windows reserved/invalid-char checks in validate_path (path_validator.py); `evaluate_permission`/`PermissionDecision` allow/ask/deny model (command_safety.py); `CommandResult` consolidated result with truncation budget (command_result.py). Auto-lint's unsupported security-heuristic path has been removed, and the capability catalog has been removed in favor of direct registry grouping. **Removal blockers remain active:** `shell_runner.py` is owned by Mars Module 05 for any further command-runner fold. |

---

## 9. Reporting template (every module report must include)

Each agent's final report must answer, in this order:

```
Module: <N> <folder>
Status change: Pending → <state>
WHAT: <1-3 lines, what was implemented>
WHY: <how it matches opencode/codex behavior — cite the reference file>
FILES: <owned files changed>
OPEND/REMOVED: <what was strengthened or removed per feature doc>
EXPECTED BEHAVIOUR: <what the module now does, observable output>
OUTCOME / TEST EVIDENCE: <gate results G1-G8, pytest/ruff output>
SHARED-FILE IMPACT: <any CCS edits + locks taken/released>
DEPENDENCIES: <modules this unblocks; what it needs next>
```

---

## 10. Conflict resolution & escalation

1. **Two agents want the same Pending module:** first claimant wins (time-stamped ledger entry). The other picks a different module or coordinates with the owner.
2. **Two agents need the same shared file:** whoever needs it takes a `LOCK:`; the other waits or works on a different file. Never edit under a foreign lock.
3. **Edit conflict on a shared file:** the coordinator resolves it additively; no agent overwrites another's gate-passing, in-progress work.
4. **Blocked > 2 agent-cycles** on a dependency/decision → escalate to the human/coordinator with a clear "BLOCKED on <X> because <Y>".
5. **Behaviour disagreement with a feature doc:** do NOT improvise a divergent behaviour; flag it, update the feature doc (add a `Decision:` note), and continue only after agreement.
6. **Anything touching the TUI contract (transport/web socket/events):** mandatory coordination with module 10 owner before finishing (G5).

---

## 11. Execution phases (project-level)

| Phase | Scope | Gate to leave |
|---|---|---|
| 0 | Baseline: `python -m pytest server/tests/ -x -q` pass count recorded; TUI lint+test+build green | recorded baseline |
| 1 | Additive core alongside old code (no removal); interface-lock core modules | interfaces locked |
| 2 | Wire the API handler to the new loop (via event-adapter); TUI still works | end-to-end runtime OK |
| 3 | Remove old internals per feature-doc REMOVE lists | removed, no regressions |
| 4 | Rewrite tests for removed internals; full pipeline ruff→pytest→TUI lint→TUI test→TUI build→30s smoke | all green |

---

## 12. Baseline details (design targets per module)

See `agent_engine_redesign/<folder>/feature.md` for the full opencode/codex comparison,
issues, intended behavior, expected output, and outcome. The module inventory above is
the live status; the feature docs are the authoritative design.

### Verified design summaries (for quick reference)

- **01 turn/loop:** ~200-line loop `while pending: stream → process → continue if tool_calls else stop`. Remove guidance/salvage/LoopDetector/turn-manifest/recovery/validation/provider_adapters; remove `DEGENERATE_MESSAGE_PATTERN`.
- **02 prompt_sending:** resolve user parts (text/file/agent/MCP) at prompt time (opencode `resolveUserPart`); one clean `stream(request)` per turn.
- **03 tool_service:** `Tool.Def{id,description,params(jsonSchema),execute}` + registry + Truncate + Permission.ask; remove resolver/router/middleware-chain/capability-taxonomy.
- **04 file_operations:** serial mutation queue; exact-match edit; write with overwrite flag; read with truncation; no read-cache/replay-block.
- **05 command_runner:** PTY persistent-shell exec with live output; timeout; background only as explicit escape; remove poll `job_output` primary path.
- **06 context:** codex `ContextFragment` slots with markers; no scoring; single compaction achieving `tokens_saved>0`; remove tiers/`SESSION_STATE`/running-summary.
- **07 session_state:** append-only message store + snapshot; status busy/idle only; no state machine / session_workspace.
- **08 thinking_reasoning:** reasoning as a Part (start/delta/end, delta-merged); one type not a parallel event stream; remove `THINKING_PARTIAL_EMIT_CHARS`.
- **09 markdown_render:** clean Part content (text/reasoning/tool_call/tool_result); truncate before delivery via the shared truncation service.
- **10 transport_event_contract:** core kinds only (thinking/message/tool_call/tool_result/error); event-adapter maps Parts→existing EventKind; remove invented kinds.
- **12 todo:** plain checklist tool (opencode `todowrite`); remove todo state machine.
- **13 provider_layer:** unified provider consuming SDK deltas→Parts; capabilities from catalog; temperature+reasoning_effort; remove bespoke parser/sampling_kwargs/validation-taxonomy/api-validation/provier_adapters tier-injection.
- **14 config_management:** typed settings with precedence defaults→file→env→CLI; constants to owning modules; remove 4-mode toolscape.
- **15 prompts:** prompt bodies in template files; tagged composable sections; runtime tier-enhancement injection removed from the system prompt.
- **16 workspace_repo_map:** ripgrep-backed glob/grep + native ignore + on-demand LSP symbols; remove tree-sitter repo-map/code-graph.
- **20 web_tools:** webfetch pure fetch+convert (remove `extract` LLM pass); websearch provider abstraction.
- **21 storage:** keep real stores (session/profile/provider_config/builtin_seed/atomic/session_file); rename catalog; remove `search_store`/`workspace_store`/usage-efficiency placeholders/dual-catalog.
- **23 toolkit_helpers:** ripgrep for brace globs; param decode via schema; minimal path_validator; fold shell_runner into command_runner; remove auto_lint/catalog-capability.

---

## 13. Signoff checklist (per module, maintained during work)

- [ ] opencode/codex comparison documented (feature doc)
- [ ] zenith current logic documented (file/line)
- [ ] correct / wrong / over-engineered / missing listed
- [ ] intended behavior + expected output + outcome specified
- [ ] items to REMOVE listed
- [ ] regex audit (keep only if opencode/codex use it)
- [ ] static/simulation/dummy code flagged
- [ ] validation gates G1–G8 recorded in §8

**By proceeding to claim a module, each agent agrees to the rules in §3–§10.**

---

## 14. Reference map & read-first

- Feature docs: `agent_engine_redesign/<module>/feature.md`
- Design/matrix sign-off: `agent_engine_redesign/SIGNOFF.md`
- Zenith backend: `server/`
- TUI: `tui/`
- References: `ref_repo/opencode`, `ref_repo/codex` (ignore `zenith-py` inside codex)
- RCA of current bugs: `task.md`; UI sprint: `todo.md`; run: `run_step.md`
