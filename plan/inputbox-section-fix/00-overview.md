# Input Composer Redesign — Overview

**Plan**: `inputbox-section-fix`
**Branch**: `fix/ser-tu-communication-n-separations`
**Date**: 2026-08-03
**Status**: Draft (reviewed against current `fix/ser-tu-communication-n-separations` code)
**Version**: 1.1

> **2026-08-03 review delta** (from `01-detailed-design.md` §2 + `02-todo-list.md`):
> - Line refs refreshed: composer render block is `App.tsx:360-376` (was `:316-332`); global-key handling is `useTerminalKeyboard.ts:93-222` (was `:77-164`).
> - Phase 7 is partly **already implemented**: `BackendScenarioProvider.abortFlag` exists (`BackendScenarioProvider.ts:13`, checked at `:147`, set by `abort()` at `:304-307`) and `useScenario.abort()` already calls `runnerRef.abort()` + local resets (`useScenario.ts:182-186`). Only the `wsClient.cancelPrompt(sessionId)` wiring is new.
> - Design seam confirmed: `Message.metadata` persists via `metadata_json` (`repositories.py:280-292`); `Session` already has `model` + `metadata` (`session.py:31,40`). `LLMProvider.complete_typed` already shows the temp/max_tokens finally-restore pattern (`llm_provider.py:648-736`); the streaming path reads `self.max_tokens`/`self.temperature` per call via `_build_completion_kwargs` (`llm_provider.py:377-378`), so executor-level attribute mutation in try/finally is the correct seam.
> - Test impact: keep `tui/tests/commandService.test.ts` (covers `/help /provider /models /clear /compact /clear-tools` through the future registry adapter) and `tui/tests/backendScenarioProvider.test.ts` (already covers abort / no-partial-tail) green.

---

## Executive Summary

Redesign Zenith's bottom input composer (`tui/src/components/Input/CommandInput.tsx`) from a bare single-card prompt box into a professional, keyboard-first command composer comparable to Claude Code / OpenCode / Codex CLI.

The scope is **full-stack**: backend (`prompt.send` per-prompt overrides + explicit `prompt.cancel`), TUI transport, a unified command registry + command palette, a two-stage Provider → Model picker with per-prompt model override, real file attachments, a declarative keybinding map, and polished idle / loading / disabled / streaming states — all while fitting Zenith's Ink-based TUI design language (8-theme token system, `RoundedBox`, `SearchList`, `ModelStore`).

The implementation is documented across four companion files in this folder (`01-detailed-design`, `02-todo-list`, `03-signoff-checklist`, `04-minimum-criteria`).

---

## Goals — What We Want to Achieve

1. **Keyboard-first command composer** — multi-line editing, auto-resize (min 1 / max min(15, rows/3)), declarative keybindings, cursor-aware history.
2. **One command registry** as the single source of truth for `/` autocomplete, the `ctrl+p` command palette, and the Help modal — every command carries its keybinding.
3. **Two-stage Provider → Model selector** — `ctrl+e` opens a provider list, then a model list (Favorites → Recent → All); selection persists via `ModelStore` (`~/.zenith/model.json`); quick model cycling with `ctrl+n` / `ctrl+shift+n`.
4. **Per-prompt model / temperature / max_tokens override** — `prompt.send` accepts them; the composer submits the currently selected model explicitly.
5. **Real file attachments** — `@` opens a real file picker; selected files become attachment chips; their contents reach the backend and are injected into the user message.
6. **Explicit cancel RPC** — `prompt.cancel` wired into the JSON-RPC dispatch; Esc during a run sends it (no more implicit cancel-by-resend only).
7. **Responsive streaming** — the input stays editable while the model is running; you can queue the next prompt; the footer shows a spinner + `Esc cancel`.
8. **Polished states** — distinct focus / disabled / running / error / empty states, cycling placeholders, a subtle `↵ send` hint, and a model chip in the footer.
9. **Reconcile keybinding drift** — Help text says `Shift+M` but code binds `Ctrl+M` (dead in Ink — Ctrl+M arrives as Enter); introduce one declarative map so UI and behavior can't drift again.
10. **Verifiable** — backend tests for overrides/cancel/attachments, TUI typecheck/lint/tests, and a manual verification matrix.

---

## Non-Goals

- **No encoder/decoder model split** — user decision: provider + model selector only (the codebase has no encoder/decoder concept today).
- **No mouse support** — terminal-first, keyboard-only; Enter submits (no clickable send button).
- **No prompt task queue** — Enter-during-run uses the existing cancel-on-resend behavior; a true queue is a deferred follow-up.
- **No stash / workspace / `/move` machinery** — the OpenCode stash and workspace features are explicitly out of scope (stash is an optional stretch).
- **No autocomplete popover above the composer** — the dropdown keeps its replace-the-composer behavior; this phase fixes the frozen-filter bug only.
- **No session turn-history API** — up-arrow-through-assistant-turns remains limited to `session.resume` / `session.sync`.

---

## Scope

| Layer | In scope | Primary files |
|---|---|---|
| Backend (`server/`) | `prompt.send` overrides (model/temperature/max_tokens/attachments), `prompt.cancel` RPC, attachment read/inject + tests | `server/api/handlers.py`, `server/agents/prompt_executor.py`, `server/tests/test_prompt_overrides.py` |
| TUI transport | `sendPrompt` opts + `cancelPrompt` | `tui/src/services/transport/WebSocketClient.ts` |
| TUI composer | redesigned card, footer, gauge, chips, states, `↵ send` hint, model chip | `CommandInput.tsx`, `MultiLineTextInput.tsx`, new `AttachmentChips/ComposerFooter/ComposerGauge` |
| TUI commands | `CommandRegistry` + `CommandPalette` + autocomplete filter fix | `CommandRegistry.ts` (new), `CommandService.ts`, `AutocompleteDropdown.tsx`, `CommandPalette.tsx` (new) |
| TUI model picker | two-stage `ModelPickerFlow`, model-cycle keys, per-prompt submit | `ModelPickerFlow.tsx` + `ProviderSelect/ModelSelect` (new), `OverlayRouter.tsx`, `useScenario.ts`, `useConversation.ts`, `App.tsx` |
| TUI keys | declarative `keybind.ts` + `useTerminalKeyboard` rewrite + HelpModal table | `keybind.ts` (new), `useTerminalKeyboard.ts`, `HelpModal.tsx` |
| History | draft restore + history dedupe (stash optional) | `useAutocomplete.ts`, `services/history/promptHistory.ts` (new) |

---

## Key Decisions (locked with the user)

1. **Model controls = two-stage Provider → Model selector** (Claude Code / OpenCode model). No encoder/decoder concept is introduced.
2. **Full-stack scope** — `server/` is in scope: extend `prompt.send` with per-prompt `model` / `temperature` / `max_tokens` / `attachments`, and add an explicit `prompt.cancel` RPC.
3. **Reuse `ModelStore` logic + SearchList pattern**; build a new two-stage `ModelPickerFlow` UI (the legacy `ModelPicker` becomes the second stage).
4. **Submit UX:** Enter submits; a subtle `↵ send` hint appears in the footer; **no mouse support**.
5. **`ctrl+p` becomes the command palette**; help moves to `?` (empty input) and `/help`.
6. **Mode toggle → `shift+m`** on empty input (via the composer's `onSpecial` hook); the dead `ctrl+m` branch is removed.
7. **Model cycling → `ctrl+n` / `ctrl+shift+n`** (Ink `Key` has no F1–F12 fields, so OpenCode's F2 is not portable).
8. **Input stays enabled while streaming**; `disabled` is reserved for pending confirmation prompts.

---

## Documents

| Document | Purpose |
|----------|---------|
| `01-detailed-design.md` | Full specification: research, current-state, gap analysis, architecture, backend contract, keyboard map, phases |
| `02-todo-list.md` | Implementation tasks and sequencing |
| `03-signoff-checklist.md` | Acceptance criteria for each phase |
| `04-minimum-criteria.md` | Minimum success requirements; must-have vs optional |

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Attachment path resolution when server cwd ≠ TUI cwd | Resolve paths against `config.workspace_root`; document that both processes run from the repo root |
| `modelStore.current` references an unconfigured provider | Picker lists configured providers only; backend already surfaces `Provider 'X' not available` as an error event |
| Ctrl+M collision with Enter in Ink | Dead `ctrl+m` branch removed; mode moved to `shift+m` on empty input |
| Scope creep | Follow-ups explicitly deferred (task queue, stash, inline popover, turn-history API) |
| Regression in existing submit/history behavior | Backend tests + TUI manual matrix; `options.json` commands kept functional through the registry adapter |

---

## Success Metrics

- All signoff criteria (`03`) and minimum criteria (`04`) satisfied.
- No regression in existing backend tests (`python -m pytest server/tests`).
- TUI passes `typecheck`, `lint`, and `npm test`.
- Manual verification matrix (section 9 of `01-detailed-design.md`) passes end-to-end against a live server.
