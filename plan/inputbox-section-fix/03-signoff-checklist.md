# Signoff Checklist — Input Composer Redesign

**Plan**: `inputbox-section-fix`
**Branch**: `fix/ser-tu-communication-n-separations`
**Date**: 2026-08-02

> Each phase is signed off only when **all** its criteria pass. Checkmarks are filled during implementation; a phase is not considered done until its row in `02-todo-list.md` and all criteria here are green.

---

## Phase 1 — Backend (server/)

- [x] `prompt.send` accepts and validates `model` (str), `temperature` (float 0..2), `max_tokens` (int ≥1), `attachments` (≤25, non-empty paths, deduped). Invalid values → JSON-RPC error, not a crash.
- [x] Per-prompt `model` is persisted on the user message metadata and applied to the session row (`session.model`, `metadata["last_model"]`).
- [x] Provider mutation (model/temperature/max_tokens) is applied in a try/finally and always restored — confirmed by test (fake provider records observed values; post-run values equal originals).
- [x] Both the standard loop and the sub-agent path respect the overrides.
- [x] `prompt.cancel` is wired in dispatch, is idempotent, and cancels an in-flight executor (tested).
- [x] Attachments are path-traversal-guarded (`../outside` rejected), size-capped (512 KB/file, 2 MB total), binary files skipped with a warning, and injected as `<attachment>` blocks into the user message.
- [x] `python -m pytest server/tests` is green (including `test_prompt_overrides.py`).

## Phase 2 — TUI transport

- [x] `sendPrompt` forwards `model/temperature/max_tokens/attachments` verbatim to `prompt.send`.
- [x] `cancelPrompt(sessionId)` sends `prompt.cancel` and resolves `{cancelled}` without throwing when no executor exists.

## Phase 3 — Command registry + palette

- [x] `/` autocomplete and the `ctrl+p` palette render from the SAME registry (single source of truth).
- [x] All pre-existing commands still work through the registry adapter (`/help /settings /context /usage /provider /models /clear /compact /clear-tools /build /plan`).
- [x] `/model` opens the model picker.
- [x] The autocomplete filter no longer freezes: typing `/comp` narrows to `/compact`.
- [x] Palette rows show their keybinding in the gutter and fuzzy-filter.
- [x] `tui/tests/commandService.test.ts` still passes (`/help /provider /models /clear /compact /clear-tools` through the adapter).

## Phase 4 — Composer UI

- [x] Multi-line editing + auto-resize (1 → min(15, rows/3)); large paste handled without corruption.
- [x] Distinct border/glyph states for focused, idle, disabled ("Waiting for approval…"), and running.
- [x] Input is EDITABLE while a run is in progress (no `disabled={isRunning}`).
- [x] Placeholders cycle; `↵ send` hint appears only when input non-empty & idle; spinner + `Esc cancel` shown while running.
- [x] Model chip shows `modelStore.current` and reflects changes without re-rendering the whole composer.
- [x] `@` produces a real attachment chip (name/size) and removes the `@` from the input; chips removable.
- [x] Idle `ctrl+c` clears the input; the cleared draft is recoverable (draft restore).

## Phase 5 — Keybindings

- [x] `keybind.ts` is the single declarative map; `matchKeypress` is pure and unit-consistent with Ink `Key`.
- [x] Dead `ctrl+m` branch removed; `shift+m`(empty input) opens mode and does NOT type an `M`; `?`(empty input) opens help and does NOT type a `?`.
- [x] `ctrl+p` opens the palette (help moved to `?`/`/help`); `ctrl+e` opens the model picker; `ctrl+n`/`ctrl+shift+n` cycle recent models.
- [x] HelpModal renders the keybind table — UI and behavior can no longer drift.

## Phase 6 — Model picker + per-prompt model

- [x] `ctrl+e` opens the two-stage picker (Provider → Model); esc backs from stage 2, closes from stage 1.
- [x] Stage 2 shows Favorites → Recent → provider models; `★` favorite toggle works.
- [x] Selecting a model persists via `ModelStore` (`~/.zenith/model.json`) AND updates provider config (`providerRepository.setModel`) — survives restart.
- [x] Submitting a prompt sends `provider` + `model` explicitly; backend log shows the resolved model; session/message metadata reflect it.
- [x] When `modelStore.current` is invalid/unconfigured, submission falls back to the active provider without error.

## Phase 7 — Cancel + streaming

- [x] Esc during a run sends `prompt.cancel`; the executor cancels; UI returns to idle quickly; the next prompt works.
- [x] No partial-message tail after cancel (events after abort are dropped). Abort plumbing is **already implemented** (`BackendScenarioProvider.abortFlag`); guard with `tui/tests/backendScenarioProvider.test.ts`.
- [x] Confirmation flow: pending tool permission disables the composer ("Waiting for approval…"); y/n works.

## Phase 8 — History (stretch)

- [ ] History up/down only at cursor edges; consecutive duplicates removed; max 50 preserved across restart.
- [ ] (If shipped) `/stash` / `/stash list` / `/stash pop` work and persist.

## Phase 9 — Quality

- [x] `npm run typecheck && npm run lint && npm run test` pass.
- [x] `python -m pytest server/tests` pass.
- [ ] Manual verification matrix (section 9 of `01-detailed-design.md`) fully passes against a live server.
- [x] No regressions in existing slash commands, session/history persistence, or confirmation flow.

---

## Final Signoff

| Reviewer | Phase | Date | Decision (Pass / Revise) | Notes |
|----------|-------|------|--------------------------|-------|
| | 1 Backend | | | |
| | 2 Transport | | | |
| | 3 Registry/Palette | | | |
| | 4 Composer UI | | | |
| | 5 Keybindings | | | |
| | 6 Model picker | | | |
| | 7 Cancel/Streaming | | | |
| | 8 History | | | |
| | 9 Quality | | | |
