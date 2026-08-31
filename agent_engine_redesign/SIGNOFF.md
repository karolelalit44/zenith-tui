# Agent Engine Redesign — Folder Sign-off / Validation

**Date:** 2026-08-31
**Status:** VALIDATED — no folder skipped, all comparisons recorded.

This document is the official sign-off for the `agent_engine_redesign/` folder. It
proves that every current zenith backend module has been audited against the
reference engines (opencode, codex) and that the differences, issues, intended
behavior, expected output, and outcome are recorded in the correct feature doc.

---

## 1. Validation method

1. Enumerated all 122 zenith source files under `server/` (excluding tests and
   `__init__.py`/`__main__.py`).
2. Mapped every file to exactly one feature folder in `agent_engine_redesign/`.
3. Verified each `feature.md` contains the full standard comparison template.
4. Verified `progress.md` references every feature folder (and vice versa).

---

## 2. Module → feature-doc coverage matrix

Every zenith module maps to one feature doc. **No folder skipped, no module unrecorded.**

| Feature folder | zenith modules covered |
|---|---|
| `turn/` | `agents/loop.py`, `agents/recovery.py`, `agents/validation.py`, `agents/loop_detection.py` |
| `prompt_sending/` | `agents/prompt_executor.py` |
| `prompts/` | `agents/prompts.py` |
| `tool_service/` | `toolkit/base.py`, `registry.py`, `executor.py`, `resolver.py`, `router.py`, `discovery.py`, `schema_metrics.py`, `registry_validation.py`, `middleware/hooks.py`, `logging.py`, `plan_write.py` |
| `file_operations/` | `toolkit/tools/file_read.py`, `file_write.py`, `file_edit.py`, `file_delete.py`, `multi_edit.py`, `glob.py`, `grep.py`, `list_dir.py` |
| `command_runner/` | `toolkit/tools/bash.py`, `background.py`, `job_output.py`, `job_kill.py`, `shell_runner.py` |
| `command_runner/command_output_response/` | command output capture/truncate/present (companion) |
| `context/` | `agents/context.py`, `compaction.py`, `compaction_service.py`, `running_summary.py`, `summarizer.py` |
| `session_state/` | `domain/session.py`, `domain/domain.py`, `agents/run_state.py`, `agents/session_state.py`, `agents/session_workspace.py`, `sessions/service.py` |
| `thinking_reasoning/` | `agents/llm_stream.py` |
| `markdown_render/` | `providers/responder.py` |
| `transport_event_contract/` | `api/server.py`, `websocket.py`, `handlers.py`, `protocol.py`, `schemas.py`, `middleware.py`, `startup.py`, `shutdown.py`, `domain/events.py`, `domain/message.py`, `domain/errors.py`, `domain/hooks.py` |
| `todo/` | `toolkit/tools/todo.py`, `agents/todo_state.py` |
| `provider_layer/` | `providers/base.py`, `llm_provider.py`, `registry.py`, `parser.py`, `token_counter.py`, `validation.py`, `agents/provider_adapters.py`, `api/provider_validation.py`, `api/validation_state.py` |
| `config_management/` | `config/constants.py`, `settings.py`, `env.py`, `loader.py`, `providers.py` |
| `workspace_repo_map/` | `workspace/repo_map.py`, `graph_queries.py`, `index.py`, `git.py`, `ignore.py`, `toolkit/tools/code_graph_tools.py` |
| `web_tools/` | `toolkit/tools/webfetch.py`, `websearch.py`, `_html_text.py` |
| `storage/` | `storage/*.py` (all 13), `sessions/export.py`, `sessions/import_service.py` |
| `toolkit_helpers/` | `toolkit/auto_lint.py`, `brace_expand.py`, `catalog.py`, `command_result.py`, `command_safety.py`, `digest.py`, `param_normalizer.py`, `path_validator.py` |
| `skills/` | `skills/loader.py` — **OUT OF SCOPE for now** (new feature, not an existing critical module) |
| `mcp/` | `mcp/client.py`, `mcp/manager.py`, `toolkit/tools/mcp_tool.py` — **OUT OF SCOPE for now** |
| `lsp/` | `lsp/client.py`, `lsp/manager.py`, `lsp_definition.py`, `lsp_diagnostics.py`, `lsp_rename.py` — **OUT OF SCOPE for now** |
| `permissions/` | `toolkit/middleware/safety.py` — **OUT OF SCOPE for now** |
| `subagents_orchestrator/` | `agents/delegation/*`, `agents/crewmate_loop.py`, `toolkit/tools/explore_tool.py` — **OUT OF SCOPE for now** (keep only current explore tool) |

> **Non-feature files (not modules):** `server/main.py` is the CLI/bootstrap
> entry point; `server/api/test_websocket.py` is a test file. Neither is a
> feature characteristic.

---

## 3. Template-completeness check (all feature.md)

Every `feature.md` was checked for these required sections — **all present**:
- How opencode does it
- How codex does it
- What zenith has today (+ file paths / constants)
- What is correct
- What is wrong / over-engineered / incorrect / missing
- What we will do
- What we will REMOVE
- Regex audit (keep only if opencode/codex use it)
- Verification / signoff checklist
- Status: Pending

24 `feature.md` files (23 folders + nested `command_output_response`) all pass.

---

## 4. Scope note (per user directive)

For now we fix ONLY zenith's **existing** modules to be workable and to replicate
codex/opencode behavior. NEW/advanced features — skills, mcp, lsp, permissions,
subagents — are **out of scope** (their design docs remain in the folder for
reference but are not part of the active fix plan).

---

## 5. Remaining discrepancies / TODO before implementation

No record gaps found. The only items to finalize are consolidation edits (not
missing coverage):
- `progress.md` execution phases should be re-read before kicking off
  implementation so the fix order matches the active-fix-focus list.

---

## Sign-off

- [x] Every zenith module mapped to a feature doc (no folder skipped)
- [x] Every feature doc has the full opencode/codex/zenith comparison
- [x] Differences, issues, intended behavior, expected output, outcome recorded
- [x] Regex audit present per doc
- [x] Static/simulation/dummy code flagged per doc
- [x] `progress.md` references all folders
- [x] Advanced features (skills/mcp/lsp/permissions/subagents) marked OUT OF SCOPE

**Validation result: PASS**
