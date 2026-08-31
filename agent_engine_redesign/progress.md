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
| 01 | turn/loop | `turn/` | Pending | P0 | XL | 02,03 | — (first consumer) |
| 02 | prompt_sending | `prompt_sending/` | Pending | P0 | M | 15 | 01 |
| 03 | tool_service | `tool_service/` | Pending | P0 | L | — | — |
| 04 | file_operations | `file_operations/` | Pending | P0 | M | — | 03 |
| 05 | command_runner | `command_runner/` | Pending | P0 | L | — | 03 |
| 06 | context | `context/` | Pending | P1 | L | 13,15 | 02 |
| 07 | session_state | `session_state/` | Pending | P1 | M | — | 01 |
| 08 | thinking_reasoning | `thinking_reasoning/` | Pending | P1 | S | 13 | 01 |
| 09 | markdown_render | `markdown_render/` | Pending | P1 | M | — | 08 |
| 10 | transport_event_contract | `transport_event_contract/` | Pending | P0 | M | — | 01,09 |
| 11 | subagents_orchestrator | `subagents_orchestrator/` | **OUT OF SCOPE** | — | — | — | — |
| 12 | todo | `todo/` | Pending | P2 | S | — | 03 |
| 13 | provider_layer | `provider_layer/` | Pending | P0 | L | — | — |
| 14 | config_management | `config_management/` | Pending | P1 | M | — | — |
| 15 | prompts | `prompts/` | Pending | P0 | M | 13 | — |
| 16 | workspace_repo_map | `workspace_repo_map/` | Pending | P1 | L | — | 03 |
| 17 | skills | `skills/` | **OUT OF SCOPE** | — | — | — | — |
| 18 | mcp | `mcp/` | **OUT OF SCOPE** | — | — | — | — |
| 19 | lsp | `lsp/` | **OUT OF SCOPE** | — | — | — | — |
| 20 | web_tools | `web_tools/` | Pending | P1 | M | — | 03 |
| 21 | storage | `storage/` | Pending | P2 | M | — | 07 |
| 22 | permissions | `permissions/` | **OUT OF SCOPE** | — | — | — | — |
| 23 | toolkit_helpers | `toolkit_helpers/` | Pending | P1 | M | — | 03 |

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
| 23 toolkit_helpers | `server/toolkit/auto_lint.py`, `brace_expand.py`, `catalog.py`, `command_result.py`, `command_safety.py`, `digest.py`, `param_normalizer.py`, `path_validator.py` |

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
| 01 turn/loop | Jupiter | **Interface-Locked** | — | G1 PASS (3 new tests); G3 clean; G2 PASS (full suite green except pre-existing heavy-isolation failure) | P0 XL; Lane A; consumer of 02/03. LOCKED interface = `SimpleLoop.process_prompt(prompt, session_id, history, mode, skills_section, plan_context, model_override, repo_map) -> AsyncIterator[Event]` (mirrors AgentLoop; emergent stop / tool-then-stop / DOOM_LOOP guard; reuses context/stream/exec/compaction). New `server/agents/simple_loop.py` + module-01 constants block (additive-only). 02/10/14 may code against it. Old AgentLoop + removals (guidance/salvage/loop-detect/manifest/validation/provider_adapters) deferred to Phase 3. Pre-existing heavy-isolation test failure tracked (module-01 owned, old AgentLoop) |
| 02 prompt_sending | Jupiter | **Interface-Locked** | — | G1 PASS (6 new tests); G3 clean; J1 wiring PASS (25 tests in test_prompt_overrides.py incl. new TestLoopWiring); J1 regression fix PASS (test_token_usage_occupancy + test_event_bus_wiring green) | P0 M; needs 15 (done) + 01 (locked). LOCKED interface = `server/agents/prompt_path.py` (`PromptPath.send(content, session_id, history, mode, skills_section, plan_context, model_override, repo_map, attachments) -> AsyncIterator[Event]`) + `resolve_user_parts` (resolves text/file/folder/inline/agent/MCP parts at prompt time) + `build_clean_system_context` (module-15 tagged surface). Single path, no delegation branching. Legacy PromptExecutor + 3-way delegation branch removal deferred to Phase 3. **J1 (Phase-2, swap inner loop only):** PromptExecutor._execute now builds module-01 `SimpleLoop` and wraps its stream in module-10 `iter_client_events`; persistence/delegation/terminal-sequencing preserved; TUI unaffected (verified by TestLoopWiring). Full `PromptPath.send` entry-point swap deferred. **J1-regression fixes:** two tests that relied on `prompt_executor.RecoverableAgentLoop` (which J1 removed from that module) updated to patch the new `prompt_executor.SimpleLoop` — `test_token_usage_occupancy.py` (token-recording path) + `test_event_bus_wiring.py` (C-F02 summarized-before-terminal ordering) both green |
| 03 tool_service | Mars | Interface-Locked | — (LOCK on server/toolkit/base.py released) | G1:G3:G4:G5:G6:G7:G8 PASS; G2 targeted-PASS | P0 L; Lane B; foundational; additive ToolDef + InvalidToolArgumentsError + decode_parameters + truncate_output + ToolDefResult/run_tool_def (resolve helper) in base.py; REMOVE router/resolver/taxonomy/middleware in Phase 3 (see report + feature Decision note) |
| 04 file_operations | Mars | Interface-Locked | — | G1:G3:G4:G5:G6:G7:G8 PASS; G2 targeted-PASS | P0 M; additive FileMutationQueue (per-workspace serial) in tools/file_mutation_queue.py; fuzzy/read-cache/replay-block/heavy-output/multi_edit removals + queue wiring deferred to Phase 3/2 (see report) |
| 05 command_runner | Mars | Interface-Locked | — | G1:G3:G4:G5:G6:G7:G8 PASS; G2 targeted-PASS | P0 L; additive ShellStreamEvent + run_shell_command_streamed (live chunk streaming + wait-for-completion) in shell_runner.py; buffered _execute_sync/background/job_output/BASH_FALSE_SUCCESS_PATTERNS removal deferred to Phase 2/3 (see report) |
| 06 context | Mars | Interface-Locked | — | G1:G3:G4:G5:G6:G7:G8 PASS; G2 targeted-PASS | P1 L; additive ContextFragment/RenderedFragment/ContentKind/tagged_fragment in context.py (codex slots); 5-tier scoring/MODE_BUDGET_PROFILES/SESSION_STATE/running-summary removals deferred to Phase 3 (see report) |
| 07 session_state | Mars | Interface-Locked | — | G1:G3:G4:G5:G6:G7:G8 PASS; G2 targeted-PASS | P1 M; additive RunStatus (busy/idle) + Session.run_status/mark_busy/mark_idle/status in session.py; state-machine + session_workspace removal deferred to Phase 3; unblocks 21 storage (see report) |
| 08 thinking_reasoning | Mars | Interface-Locked | — | G1:G3:G4:G5:G6:G7:G8 PASS; G2 targeted-PASS | P1 S; quick win; additive ReasoningPart (delta-merged) + ReasoningEffort + accumulate_reasoning_parts in llm_stream.py; THINKING-event removal deferred to Phase 3 (see report + feature Decision note) |
| 09 markdown_render | Mars | Interface-Locked | — | G1:G3:G4:G5:G6:G7:G8 PASS; G2 targeted-PASS | P1 M; additive ContentPart/PartKind + part factories + render_parts_text + parts_message (data.parts on MESSAGE kind, data.text fallback) in responder.py; MAX_EVENT_OUTPUT preview + invented-kind removal deferred to Phase 3 (see report) |
| 10 transport_event_contract | Jupiter | Review | — | G1 PASS (12 new tests in test_event_adapter.py); G3 clean; G5 PASS (additive, TUI kinds untouched); G6 PASS; **Phase-2 wiring PASS (J1 swap inner loop: 25 test_prompt_overrides + adapter tests green; ruff clean on prompt_executor + test)** | P0 M; needs 01,09 (both Interface-Locked). Phase-1 additive DONE: `server/api/event_adapter.py` — `adapt_part`/`adapt_parts`/`iter_client_events` map module-09 `ContentPart` (text/reasoning/tool_call/tool_result/error) onto TUI `EventKind`s (message/thinking/tool_call/tool_result/error), full truncated tool output (no 5K preview). LOCKED interface = `iter_client_events(AsyncIterator[Event]) -> AsyncIterator[Event]` (fan-out of `data.parts`). **Phase-2 DONE (Jupiter J1):** `iter_client_events` now consumed in `server/agents/prompt_executor.py` around the module-01 `SimpleLoop.process_prompt` stream (swap-inner-loop lane). Because SimpleLoop emits no `data.parts` yet, the adapter is a faithful pass-through today; it becomes the forward-compatible boundary for Phase-3 part re-expression. Invented-kind removal deferred to Phase 3 (see feature doc REMOVE note) |
| 12 todo | Jupiter | Review | — | G1:G6:G8 PASS | Lane D; plain checklist tool (write/list/remove); simplified store; tests updated |
| 13 provider_layer | **Mars** | Interface-Locked | — | G1:G3:G4:G5:G6:G7 PASS; G2 targeted-PASS (full suite slow) | Lane C; P0; additive: ModelCapabilities + model_capabilities_from_catalog + reasoning_effort knob + provider.capabilities; REMOVES deferred to Phase 3 (see feature Decision note + report) |
| 14 config_management | Jupiter | **Interface-Locked** | — | G1 PASS (13 tests); G3 clean | Lane D; Phase 1 additive: layered precedence defaults→file→env→CLI documented in settings.py/loader.py + 5 precedence tests in test_config.py. **Removals (constants redistribution + 4-mode toolscape + CREWMATE mode) deferred to Phase 3** per §11 protocol — requires coordinated batch-edit of CCS file constants.py and changes to resolver.py (03), handlers.py (10), loop.py (01), prompt_executor.py (02) with all consumers locked. |
| 15 prompts | Mars | Interface-Locked | — | G1:G3:G4:G5:G6:G7:G8 PASS; G2 targeted-PASS | P0 M; additive editable templates (build.md/plan.md) + load_prompt_template + PromptSection/compose_system_context/default_template_sections in prompts.py; hardcoded constants + tier-injection removal deferred to Phase 3 (see report) |
| 16 workspace_repo_map | Mars | Interface-Locked | — | G1:G3:G4:G5:G6:G7:G8 PASS; G2 targeted-PASS | P1 L; additive RipgrepBackend / SearchMatch / grep / glob in workspace/search.py (ripgrep-backed glob/grep + native ignore; tree-sitter repo-map/code-graph removal deferred to Phase 3/2 (see report)) |
| 20 web_tools | Mars | Interface-Locked | — | G1:G3:G4:G5:G6:G7:G8 PASS; G2 targeted-PASS | P1 M; additive FetchResult + fetch_page (pure fetch+convert) in webfetch.py + constants dedup (DEFAULT_WEBSEARCH_MAX_RESULTS single source); websearch provider abstraction + MCP-fronted search deferred to Phase 2/3; legacy extract kept (see report) |
| 21 storage | Jupiter | In-Progress (Blocked) | — | — | BLOCKED on module 07/10/16 interface-lock: remove search_store/workspace_store breaks handlers.py (10) + FileWorkspaceRepository (07/16); dual catalog path needs 06/13. Keep append-only JSONL + atomic |
| 23 toolkit_helpers | Jupiter | In-Progress (Blocked) | — | G1 PASS (19 new tests in test_toolkit_helpers.py); G3 clean; G2 PASS (no new failures — only pre-existing heavy-isolation + Mars's workspace_search failures) | BLOCKED on module 03/04/05 interface-lock for REMOVALS (brace_expand → glob.py/grep.py(04); catalog → registry_validation(03); shell_runner owned by 05). Phase 1 additive DONE: `decode_params_with_schema` (param_normalizer.py, schema-based decode with normalize_file_params fallback); `is_destructive_write`/`is_destructive_delete` + Windows reserved/invalid-char checks in validate_path (path_validator.py); `evaluate_permission`/`PermissionDecision` allow/ask/deny model (command_safety.py); `CommandResult` consolidated result with truncation budget + false-success detection (command_result.py). Removals (brace_expand/auto_lint/catalog-capability/shell_runner fold) deferred to Phase 3. |

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
- **09 markdown_render:** clean Part content (text/reasoning/tool_call/tool_result); truncate before delivery; remove `MAX_EVENT_OUTPUT` preview hack.
- **10 transport_event_contract:** core kinds only (thinking/message/tool_call/tool_result/error); event-adapter maps Parts→existing EventKind; remove invented kinds.
- **12 todo:** plain checklist tool (opencode `todowrite`); remove todo state machine.
- **13 provider_layer:** unified provider consuming SDK deltas→Parts; capabilities from catalog; temperature+reasoning_effort; remove bespoke parser/sampling_kwargs/validation-taxonomy/api-validation/provier_adapters tier-injection.
- **14 config_management:** typed settings with precedence defaults→file→env→CLI; constants to owning modules; remove 4-mode toolscape.
- **15 prompts:** prompt bodies in template files; tagged composable sections; remove runtime tier-enhancement injection.
- **16 workspace_repo_map:** ripgrep-backed glob/grep + native ignore + on-demand LSP symbols; remove tree-sitter repo-map/code-graph.
- **20 web_tools:** webfetch pure fetch+convert (remove `extract` LLM pass); websearch provider abstraction.
- **21 storage:** keep real stores (session/profile/provider_config/builtin_seed/atomic/session_file); rename catalog; remove `search_store`/`workspace_store`/usage-efficiency placeholders/dual-catalog.
- **23 toolkit_helpers:** ripgrep for brace globs; param decode via schema; minimal path_validator; fold shell_runner into command_runner; remove brace_expand/auto_lint/catalog-capability.

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
