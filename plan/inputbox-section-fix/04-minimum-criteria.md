# Minimum Criteria — Input Composer Redesign

**Plan**: `inputbox-section-fix`
**Branch**: `fix/ser-tu-communication-n-separations`
**Date**: 2026-08-03

> This document defines what **must** be present for the work to be considered complete and releasable, and what is **optional** (can be deferred without blocking signoff). Sections marked **MUST** are non-negotiable for `03-signoff-checklist.md` to pass.

---

## 1. MUST — Backend contract

- [x] Spec: `prompt.send` accepts per-prompt `model`, `temperature`, `max_tokens`, and `attachments` (path-reference; `content` escape hatch).
- [x] Spec: `prompt.cancel` RPC wired into the JSON-RPC dispatch (idempotent).
- [x] Spec: attachments path-traversal-guarded, size-capped (512 KB/file, 2 MB total), binary-skipped, injected into the user message.
- [x] Spec: per-prompt model persisted on message metadata + session row.
- [x] Spec: provider override mutation restored in a finally (standard + sub-agent paths).

## 2. MUST — TUI behavior

- [x] Spec: input stays **editable while a run is in progress** (no `disabled={isRunning}`).
- [x] Spec: Esc during a run sends `prompt.cancel` (explicit cancel, not just implicit re-send).
- [x] Spec: multi-line editing with auto-resize (1 → min(15, rows/3)); Enter submits; Shift/Ctrl+Enter newline.
- [x] Spec: context-sensitive history (Up/Down only at cursor edges); draft restore on idle `ctrl+c`.
- [x] Spec: `ctrl+p` command palette and `/` autocomplete share one command registry; autocomplete filter keeps working while typing.
- [x] Spec: two-stage Provider → Model picker via `ctrl+e`; selection persists via `ModelStore`.
- [x] Spec: per-prompt model from the picker is actually sent on submit and takes effect server-side.
- [x] Spec: `@` attaches a real file whose content reaches the backend.
- [x] Spec: declarative `keybind.ts` map; HelpModal renders it; `ctrl+m` dead branch removed; `shift+m`/`?` on empty input handled via `onSpecial`.

## 3. MUST — Quality gates

- [x] Spec: `npm run typecheck && npm run lint && npm run test` pass (TUI) — includes keeping `tui/tests/commandService.test.ts` (registry adapter) and `tui/tests/backendScenarioProvider.test.ts` (abort flag) green.
- [x] Spec: `python -m pytest server/tests` pass (backend), including new override/cancel/attachment tests.
- [x] Spec: manual verification matrix (section 9 of `01-detailed-design.md`) passes end-to-end.
- [x] Spec: no regression in existing slash commands, session/history persistence, or confirmation flow.

---

## 4. Optional (defer without blocking signoff)

| Feature | Deferrable because | Suggested follow-up |
|---|---|---|
| True prompt task queue (queue vs replace on Enter-during-run) | Existing cancel-on-resend already stops the previous turn | New RPC + queue in `MethodHandlers` |
| Dedicated `build_messages` exempt block for attachments | Injection into the user message already reaches the model + persists | `server/agents/context.py` |
| `/stash`, `/stash list`, `/stash pop` | Draft restore covers the main accidental-clear case | `services/history/promptHistory.ts` |
| Inline autocomplete popover *above* the composer | Replace-behavior kept; only the frozen filter is fixed this pass | New popover component + positioning |
| Session turn-history API for up-arrow-through-assistant-turns | Only `session.resume`/`session.sync` exist today | New `session.turns` RPC + TUI navigation |
| Model `cycleFavorite` keybinding | `ctrl+n` cycling covers recent models | Add `ctrl+shift+f` or palette entry |
| `alt+enter` / `ctrl+j` newline alternatives | Shift/Ctrl+Enter already covers it | Documented in keybind map |
| Mouse support / clickable send button | Explicitly out of scope (user decision) | Requires Ink mouse layer |

---

## 5. Minimum release definition (all MUST true)

1. Backend overrides + cancel are implemented and tested (`server/tests` green).
2. Composer UI redesign is in place with editable-while-running behavior.
3. Command palette + unified registry work; autocomplete filter fixed.
4. Two-stage model picker works and the chosen model is applied per-prompt.
5. `@` attachments reach the backend.
6. Declarative keybindings drive the UI; HelpModal is accurate.
7. TUI typecheck/lint/tests green; manual matrix passes.
8. No regression in existing functionality.

When 1–8 hold, the phase-9 rows in `03-signoff-checklist.md` can be signed off and the branch is releasable.
