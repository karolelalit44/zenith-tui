# Todo List — Input Composer Redesign

**Plan**: `inputbox-section-fix`
**Branch**: `fix/ser-tu-communication-n-separations`
**Date**: 2026-08-02

> Sequencing: Phase 1 must land before Phase 2/6 (wire shape). `prompt.cancel` (Phase 1) must land before Phase 7 (Esc wiring). The `keybind.ts` map (Phase 5) should land before Phase 3 palette gutters / Phase 4 composer keys to avoid churn. Phases 3–6 are otherwise parallelizable.

---

## Phase 1 — Backend: `prompt.send` extensions + `prompt.cancel` (server/)

- [ ] `server/api/handlers.py` — `_prompt`: parse/validate optional `model` (strip), `temperature` (float 0..2), `max_tokens` (int ≥1), `attachments` (list of dicts, non-empty `path`, dedupe by path, cap 25).
- [ ] `_prompt`: persist `model` + `attachment_paths` on `user_msg.metadata` before `message_repo.create`.
- [ ] `_prompt`: when `model` set, update `session.model` + `session.metadata["last_model"]` via `session_repo.update`.
- [ ] `_prompt`: thread `model_override / temperature / max_tokens / attachments` into `executor.run(...)`; extend `PROMPT.RECEIVED` log.
- [ ] Dispatch map: add `"prompt.cancel"` → `_cancel_prompt`.
- [ ] `_cancel_prompt`: look up `_session_executors.get(session_id)`, call `cancel_active()`, reply `{"cancelled": bool}` (idempotent).
- [ ] `server/agents/prompt_executor.py` — extend `run`/`_execute` signatures with the 4 new args.
- [ ] `_execute`: resolve `effective_model = model_override or plan_model_override`; apply model/temperature/max_tokens to `self._provider` in try/finally that restores originals (covers standard + sub-agent paths).
- [ ] `_execute`: pass `model_override=None` to `agent.process_prompt` (provider pre-set; fold plan override into `effective_model`).
- [ ] Attachment reader util: async read, `is_relative_to` traversal guard, 512 KB/file + 2 MB total caps, binary (null bytes in first 8 KB) skip.
- [ ] Inject `<attachment path="…">…</attachment>` blocks into `content` before `process_prompt`; emit `r.warning` for skipped files.
- [ ] `server/tests/test_prompt_overrides.py` — fake provider records observed model/temp/max_tokens; assert mutation+restore; message metadata; session row; `prompt.cancel` cancels in-flight task; traversal guard + size cap.
- [ ] Backend green: `python -m pytest server/tests`.

---

## Phase 2 — TUI transport

- [ ] `WebSocketClient.sendPrompt(content, mode, sessionId?, provider?, opts?)` — opts: `model?`, `temperature?`, `max_tokens?`, `attachments?`.
- [ ] `WebSocketClient.cancelPrompt(sessionId)` → `prompt.cancel`, returns `{cancelled}`.

---

## Phase 3 — Command registry + command palette (TUI)

- [ ] New `CommandRegistry.ts`: `CommandDef` type + `CommandRunContext` (add `openModelPicker`, `openPalette`, `toggleThinking`) + module-level `commandRegistry`.
- [ ] Registry entries: `/help /settings /context /usage /provider /models /clear /compact /clear-tools /build /plan` + new `/model` + palette-only items (Toggle thinking, Switch mode, Open model picker, Save plan to file, Clear conversation, Command palette) with keybindings.
- [ ] `CommandService.dispatchCommand` → thin adapter over the registry (exact-slash match, returns boolean).
- [ ] New `CommandPalette.tsx`: `SearchList` over `!hidden` commands, `gutter: formatKeyBind(keybind)`, select runs then closes.
- [ ] `AutocompleteDropdown.tsx`: build list from registry; local filter buffer + `onQueryChange` (fixes frozen filter).
- [ ] `App.tsx`: `showPalette` state; render palette; composer visibility excludes `showPalette`; ctrl+p toggle.

---

## Phase 4 — Composer UI redesign (TUI)

- [ ] `MultiLineTextInput v2`: `onSpecial?(char, key, value) => boolean` called first in `handleInput`; newline on shift/ctrl/meta/return + `\x0a`; home/end; height `min(15, floor(rows/3))`.
- [ ] New `AttachmentChips.tsx` (chip row, remove per-chip).
- [ ] New `ComposerGauge.tsx` (10-block context gauge, derived `effectiveMaxTokens`).
- [ ] New `ComposerFooter.tsx` (mode · model chip · dir · branch · tokens · gauge · `↵ send` / spinner+`Esc cancel`).
- [ ] New `RunningSpinner.tsx` (isolated tick so idle frames don't re-render).
- [ ] `CommandInput.tsx`: focus/disabled/running states; cycling placeholders (~4s); send hint; model chip reading `modelStore.current`.
- [ ] `useAutocomplete.ts`: real `@` attachments (fs.stat + mime), strip `@` from input on select; `draftRef` (save on submit, restore on idle `ctrl+c`).
- [ ] `App.tsx`: `running` vs `disabled` (confirmation only); wire `onOpenModelPicker`, `onCancel`, `onOpenHelp`, `onOpenMode`.

---

## Phase 5 — Declarative keybinding map + key wiring (TUI)

- [ ] New `config/keybind.ts`: `KeybindId`, `KEYBINDINGS` (section 6 table), `matchKeypress`, `formatKeyBind`.
- [ ] `useTerminalKeyboard` rewrite: confirmation y/n/esc kept; palette, thinking, save_plan, clear_turns, model_picker, model_cycle/reverse, interrupt; remove dead `ctrl+m`.
- [ ] `MultiLineTextInput` uses `matchKeypress` for its keys.
- [ ] `HelpModal` renders the `KEYBINDINGS` table (Ctrl+P palette, `?` help, Shift+M mode).

---

## Phase 6 — Two-stage Provider → Model picker (TUI)

- [ ] New `ProviderSelect.tsx` (stage 1; configured/connected providers with ≥1 model; `✓` gutter; Popular/Providers).
- [ ] New `ModelSelect.tsx` (stage 2; Favorites → Recent → provider models; `★ Favorite` action).
- [ ] New `ModelPickerFlow.tsx` (two-stage state machine; esc back/close; enter advance/select).
- [ ] `OverlayRouter.tsx`: `models` overlay → `ModelPickerFlow` (was legacy `ModelPicker`).
- [ ] Final select: `modelStore.set(sel)` + `providerRepository.setModel(...)` + `providerService.notifyChange()` + close.
- [ ] `useScenario.startScenario(prompt, mode, provider?, model?, attachments?)` → `sendPrompt(..., {model, attachments})`.
- [ ] `useConversation.addTurn(prompt, mode, model?)`; `handleRetry` passes stored model back.
- [ ] `App.tsx` submit path: resolve `sel = modelStore.current` (valid in providers) else active provider; send `providerId` + `modelId` + `attachments`.
- [ ] `CommandInput` model chip reflects `modelStore.current`.

---

## Phase 7 — Cancel/interrupt + streaming UX (TUI)

- [ ] `useScenario.abort()`: `runnerRef.abort()` + `wsClient.cancelPrompt(sessionId)` (if set) + local `setIsRunning(false)`/`setActiveConfirmation(null)`.
- [ ] `BackendScenarioProvider.execute`: `aborted` flag; drop events after abort.
- [ ] `App.tsx`: composer stays mounted while running; Enter-during-run sends new `prompt.send` (existing cancel-on-resend stops previous turn).

---

## Phase 8 — History + draft (stretch)

- [ ] Extract `services/history/promptHistory.ts` from `useAutocomplete` (keep `~/.zenith/history.json` max50 + consecutive dedupe).
- [ ] Draft restore (from Phase 4) verified.
- [ ] (Optional) `/stash`, `/stash list`, `/stash pop` (JSONL `~/.zenith/stash.jsonl`, max10).

---

## Phase 9 — Polish, performance, verification

- [ ] Memoize `ComposerFooter`, `ComposerGauge`, `AttachmentChips`; `commandRegistry` module-level; `RunningSpinner` isolated.
- [ ] `npm run typecheck && npm run lint && npm run test` (TUI).
- [ ] `python -m pytest server/tests` (backend).
- [ ] Manual verification matrix (section 9 of `01-detailed-design.md`) passes end-to-end.
