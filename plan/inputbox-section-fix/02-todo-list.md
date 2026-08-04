# Todo List — Input Composer Redesign

**Plan**: `inputbox-section-fix`
**Branch**: `fix/ser-tu-communication-n-separations`
**Date**: 2026-08-03

> Sequencing: Phase 1 must land before Phase 2/6 (wire shape). `prompt.cancel` (Phase 1) must land before Phase 7 (Esc wiring). The `keybind.ts` map (Phase 5) should land before Phase 3 palette gutters / Phase 4 composer keys to avoid churn. Phases 3–6 are otherwise parallelizable.
>
> Review notes (2026-08-03): Phase 7's abort plumbing is **already implemented** — `BackendScenarioProvider.abortFlag` (`BackendScenarioProvider.ts:13,147,304`) and `useScenario.abort()`'s `runnerRef.abort()` + local resets (`useScenario.ts:182-186`) exist; only `wsClient.cancelPrompt` wiring is new. `tui/tests/commandService.test.ts` and `tui/tests/backendScenarioProvider.test.ts` must stay green through Phases 3/7.

---

## Phase 1 — Backend: `prompt.send` extensions + `prompt.cancel` (server/) ✅ done 2026-08-03

- [x] `server/api/handlers.py` — `_prompt`: parse/validate optional `model` (strip), `temperature` (float 0..2), `max_tokens` (int ≥1), `attachments` (list of dicts, non-empty `path`, dedupe by path, cap 25).
- [x] `_prompt`: persist `model` + `attachment_paths` on `user_msg.metadata` before `message_repo.create`.
- [x] `_prompt`: when `model` set, update `session.model` + `session.metadata["last_model"]` via `session_repo.update`.
- [x] `_prompt`: thread `model_override / temperature / max_tokens / attachments` into `executor.run(...)`; extend `PROMPT.RECEIVED` log.
- [x] Dispatch map: add `"prompt.cancel"` → `_cancel_prompt`.
- [x] `_cancel_prompt`: look up `_session_executors.get(session_id)`, call `cancel_active()`, reply `{"cancelled": bool}` (idempotent).
- [x] `server/agents/prompt_executor.py` — extend `run`/`_execute` signatures with the 4 new args.
- [x] `_execute`: resolve `effective_model = model_override or plan_model_override`; apply model/temperature/max_tokens to `self._provider` in try/finally that restores originals (covers standard + sub-agent paths). Seam confirmed: `_build_completion_kwargs` reads `self.max_tokens`/`self.temperature` per call (`llm_provider.py:377-378`); `complete_typed` (`llm_provider.py:648-736`) is the in-repo finally-restore precedent.
- [x] `_execute`: pass `model_override=None` to `agent.process_prompt` (provider pre-set; fold plan override into `effective_model`).
- [x] Attachment reader util: async read, `is_relative_to` traversal guard, 512 KB/file + 2 MB total caps, binary (null bytes in first 8 KB) skip.
- [x] Inject `<attachment path="…">…</attachment>` blocks into `content` before `process_prompt`; emit `r.warning` for skipped files.
- [x] `server/tests/test_prompt_overrides.py` — fake provider records observed model/temp/max_tokens; assert mutation+restore; message metadata; session row; `prompt.cancel` cancels in-flight task; traversal guard + size cap.
- [x] Backend green: `python -m pytest server/tests` (438 passed) + `ruff check server/` clean.

---

## Phase 2 — TUI transport ✅ done 2026-08-03

- [x] `WebSocketClient.sendPrompt(content, mode, sessionId?, provider?, opts?)` — opts: `model?`, `temperature?`, `max_tokens?`, `attachments?` (`PromptOptions`/`PromptAttachment` interfaces).
- [x] `WebSocketClient.cancelPrompt(sessionId)` → `prompt.cancel`, returns `{cancelled}`.
- [x] TUI green after Phase 2: `npm run typecheck`, `npm run lint`, `npm run test` (79 passed). Also fixed two pre-existing lint issues (`ProviderRepository.ts:60` `isNaN` → `Number.isNaN`; biome formatting in `UserMessageBlock.tsx`).

---

## Phase 3 — Command registry + command palette (TUI) ✅ done 2026-08-03

- [x] New `CommandRegistry.ts`: `CommandDef` type + `CommandRunContext` (`openModelPicker`, `openPalette`, `toggleThinking`, `savePlan`) + module-level `commandRegistry` (12 slash commands incl. new `/model` + 6 palette-only items with keybinds, `getCommandSlashes` helper).
- [x] `CommandService.dispatchCommand` → thin adapter over the registry (exact-slash match, returns boolean, preserves `CommandHandlers` contract). `tui/tests/commandService.test.ts` stays green. `options.json` kept as reference only.
- [x] New `CommandPalette.tsx` = `SearchList` over `!hidden` commands with `gutter: formatKeyBind(keybind)`; select runs then closes.
- [x] `AutocompleteDropdown.tsx`: builds list from registry; local `useTextBuffer` filter (initialized from `input`, mirrors via `onQueryChange`) fixes the frozen filter.
- [x] `App.tsx`: `showPalette` state + `handleSetShowPalette` (closes autocomplete/file picker when opening); `commandCtx` useMemo (incl. `handleSavePlan`, `openModelPicker` fallback `openOverlay('models')`); render palette; composer visibility excludes `showPalette`; `showPalette`/`setShowPalette` wired into `useTerminalKeyboard`.
- [x] TUI green after Phase 3: `npm run typecheck`, `npm run lint`, `npm run test` (79 passed).

---

## Phase 4 — Composer UI redesign (TUI) ✅ done 2026-08-03

- [x] `MultiLineTextInput v2`: `onSpecial?(char, key, value) => boolean` called first in `handleInput` (return `true` swallows); newline on shift/ctrl/meta/return + `\x0a`; home/end; height `min(15, floor(rows/3))` via `computeMaxLines`.
- [x] New `AttachmentChips.tsx` (chip row `@name · size`, round border, per-chip `×` remove via `onRemove`).
- [x] New `ComposerGauge.tsx` (10-block `█`/`░` gauge, warning color >80 %, memoized).
- [x] New `ComposerFooter.tsx` (mode chip `[PLAN]/[BUILD]`, `ModelChip` subscribing to `modelStore.current` + `▾`, provider name hidden <65 cols, dir hidden <100 cols, `(branch)`, tokens/max, gauge, `↵ send`/`↵`, spinner + `Esc cancel` when running, "Waiting for approval…" when disabled; memoized).
- [x] New `RunningSpinner.tsx` (isolated 150 ms tick over `ASCII_SPINNER_FRAMES`, memoized).
- [x] `CommandInput.tsx`: focus/disabled/running states — `disabled` (confirmation pending) → dim border + `◌` + "Waiting for approval…"; `running` → input stays editable, footer spinner + `Esc cancel`; cycling placeholders (~4s); `onSpecial` handles empty-input `?` help, `shift+m` mode, idle `ctrl+c` clear-input, running `esc` cancel; send hint via footer.
- [x] `useAutocomplete.ts`: `@` picker select → real `FileAttachment` (`fs.statSync` size + extension→mime map) + strips `@` from input (chip only, plain text stays clean); `draftRef` saves pre-clear text in `addHistory` (submit path), `clearInput` restores it when input is empty (ctrl+c idle). `clearInput` used by submit/slash still clears without restore.
- [x] `App.tsx`: composer visible when `!showFilePicker && !isOverlayOpen && !showPalette`; `running={isRunning}` + `disabled={!!(activeConfirmation && !activeConfirmation.answered)}` (was `disabled={isRunning}`); wired `onCancel={abort}`, `onOpenHelp={() => openOverlay('help')}`, `onOpenMode` (toggles build/plan), `onClearInput={clearInput}`. Removed `isRunning`/`tokenUsageStats` composer props (Σ total / N req now shown only in `SessionStatusBar`; plan footer omits them).
- [x] TUI green after Phase 4: `npm run typecheck`, `npm run lint`, `npm run test` (79 passed), `npm run build`.
- NOTE (deviation): `onOpenModelPicker` is NOT passed into `CommandInput` — no keyboard key in the composer legitimately opens the picker without double-firing with the global handler (Ink delivers keypresses to every active `useInput`, so the composer can't "swallow" for the global). Model picker stays reachable via `ctrl+e` (global), `/model`, and the palette. The `ModelChip ▾` in the footer is a visual affordance only.
- NOTE: `tokenUsageStats`/`isRunning` props dropped from `CommandInput` (were only used by the old footer state line, now in `ComposerFooter`/`SessionStatusBar`).

---

## Phase 5 — Declarative keybinding map + key wiring (TUI) ✅ done 2026-08-03

- [x] New `config/keybind.ts`: `KeybindId`, `KEYBINDINGS` (section 6 table), pure `matchKeypress` (Ink-Key-consistent, modifier-sensitive named keys, ctrl+letter control chars), `formatKeyBind`/`formatKeySpec`.
- [x] `useTerminalKeyboard` rewrite using `matchKeypress`: confirmation y/n/esc kept; `ctrl+p` palette (optional `showPalette`/`setShowPalette` props); `ctrl+e` model picker (optional `openModelPicker`, falls back to `openOverlay('models')`); `ctrl+n`/`ctrl+shift+n` model cycle (optional `cycleModel`); thinking/save_plan/clear_turns kept; esc closes palette/overlay then cancels running; removed dead `ctrl+m`; removed shift/ctrl+return scroll-to-top/bottom (conflicts with `newline` bindings). New props optional so `App.tsx` wires them in later phases.
- [x] `MultiLineTextInput` uses `matchKeypress` for submit/newline/history_up/history_down, preserving plain-enter-submit / shift/ctrl+enter-newline semantics.
- [x] `HelpModal` renders the `KEYBINDINGS` table (14 entries, two-column), updated to Ctrl+P palette / ? help / Shift+M mode; added `/model` row.
- [x] TUI green after Phase 5: `npm run typecheck`, `npm run lint`, `npm run test` (79 passed).

---

## Phase 6 — Two-stage Provider → Model picker (TUI) ✅ done 2026-08-03

- [x] New `ProviderSelect.tsx` (stage 1): `getProviderInfoList()` filtered to configured/connected (`has_api_key`/`validated`/`is_active`) with ≥1 model; `✓` gutter when configured; `●` title marker for `modelStore.current?.providerID`; Popular/Providers categories (`POPULAR` list like `ProviderPicker`).
- [x] New `ModelSelect.tsx` (stage 2): Favorites → Recent → provider models (dedupe), `current` markers, `★ Favorite` action (Tab); `onBack` on esc; title shows provider name.
- [x] New `ModelPickerFlow.tsx`: two-stage state machine (`providerID: string | null`), `RoundedBox` "MODEL PICKER" container; stage 1 esc closes, stage 2 esc backs.
- [x] `OverlayRouter.tsx`: `models` overlay → `ModelPickerFlow` (was legacy `ModelPicker`; `ModelPicker.tsx` kept — `providerScreens.test.tsx` still renders it directly).
- [x] `useTerminalKeyboard.ts`: `models` overlay exempt from global esc close-all so the flow owns esc (back/close).
- [x] Final select: `providerRepository.setModel(...)` → `modelStore.set(sel)` + `providerService.notifyChange()` + close (same as prior OverlayRouter behavior).
- [x] `useScenario.startScenario(prompt, mode, provider?, model?, attachments?)` → `sendPrompt(..., {model, attachments: [{path, name}]})`.
- [x] `useConversation.addTurn(prompt, mode, model?)` stores model on the turn; `handleRetry` passes `activeTurn.model` back.
- [x] `App.tsx` submit path: resolve `sel = modelStore.current` (validated against provider catalog), `providerId = sel?.providerID ?? activeProvider.id`, `modelId = sel?.modelID`; passes both + `attachments`.
- [x] `CommandInput` model chip reads `modelStore.current` (done in Phase 4 via `ComposerFooter.ModelChip`).
- [x] TUI green after Phase 6: `npm run typecheck`, `npm run lint`, `npm run test` (79 passed), `npm run build`.

---

## Phase 7 — Cancel/interrupt + streaming UX (TUI) ✅ done 2026-08-03

- [x] `useScenario.abort()`: added `wsClient.cancelPrompt(sessionIdRef.current)` (if set) to the existing `abort()` (`runnerRef.abort()` + `setIsRunning(false)`/`setActiveConfirmation(null)` were already present).
- [x] `BackendScenarioProvider.execute`: verified — `abortFlag` (`:13`) checked at the top of the event handler (`:147`), set by `abort()` (`:304-307`); no partial-message tail. `tui/tests/backendScenarioProvider.test.ts` stays green (79 total passed).
- [x] `App.tsx`: composer stays mounted while running (Phase 4); Enter-during-run sends a new `prompt.send` (backend `executor.cancel_active()` on re-send stops the previous turn).

---

## Phase 8 — History + draft (stretch)

- [ ] Extract `services/history/promptHistory.ts` from `useAutocomplete` (keep `~/.zenith/history.json` max50 + consecutive dedupe).
- [ ] Draft restore (from Phase 4) verified.
- [ ] (Optional) `/stash`, `/stash list`, `/stash pop` (JSONL `~/.zenith/stash.jsonl`, max10).

---

## Phase 9 — Polish, performance, verification

- [x] Memoize `ComposerFooter`, `ComposerGauge`, `AttachmentChips`; `commandRegistry` module-level; `RunningSpinner` isolated.
- [x] `npm run typecheck && npm run lint && npm run test` (TUI) — final: typecheck clean, lint clean (121 files), `npm run test` 79 passed (two consecutive full-suite runs), `npm run build` green.
- [x] `python -m pytest server/tests` (backend) — 438 passed + `ruff check server/` clean.
- [ ] Manual verification matrix (section 9 of `01-detailed-design.md`) passes end-to-end.
- NOTE (final verification): the timing-sensitive `App.test.tsx > Escape during scenario stops execution` flaked intermittently under full-suite parallel load (passes alone; ~2/3 after Phase 4). Stabilized by `useCallback`-ing `handleOpenHelp`/`handleToggleMode` in `App.tsx` (restores `React.memo` on `CommandInput`, trims render cost). Two consecutive full-suite green runs after the fix.
