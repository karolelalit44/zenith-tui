# Detailed Design — Input Composer Redesign

**Plan**: `inputbox-section-fix`
**Branch**: `fix/ser-tu-communication-n-separations`
**Date**: 2026-08-03
**Version**: 1.1

---

## Table of Contents

1. [Research Summary](#1-research-summary)
2. [Current Implementation](#2-current-implementation-verified)
3. [Gap Analysis](#3-gap-analysis)
4. [Design Principles](#4-design-principles)
5. [Backend Contract](#5-backend-contract)
6. [Keyboard Map](#6-keyboard-map)
7. [Implementation Phases](#7-implementation-phases)
8. [File Structure](#8-file-structure)
9. [Verification](#9-verification)
10. [Follow-ups (Deferred)](#10-follow-ups-deferred)

---

## 1. Research Summary

### 1.1 Claude Code (public docs + observed behavior)

- Single bottom input line, **no button**; `>` prefix; **Enter submits**, Shift+Enter / Esc-to-edit for multi-line; the input auto-grows.
- Slash commands are the primary command surface (`/help`, `/model`, `/provider`, `/clear`, `/compact`, `/cost`, `/init`, `/login`, `/logout`, `/memory`, `/permissions`, `/status`, `/vim`…) with inline fuzzy suggestions while typing `/`.
- `@` inserts file/context references inline; references render as inline chips; the submitted plain text stays clean.
- **Up/Down** navigate history only when the cursor is at the buffer edge. **Esc** interrupts a running turn; **Ctrl+C** cancels.
- Streaming is inline; the input stays visible; a subtle `(chars / tokens)` context indicator sits below the thread.
- Keyboard-first, minimal chrome, focus always returns to the input.

### 1.2 OpenCode (local source — `ref_repo/opencode/packages/tui/src/`) — patterns to adopt

- **Full editor, not a text field**: `component/prompt/index.tsx` uses a real `<textarea>` with `minHeight=1` / `maxHeight = max(6, termHeight/3)` auto-resize and a **virtual-text "extmark"** system rendering file/agent/paste references inline as styled `parts` — plain text stays clean.
- **Declarative, mode-stacked keybindings**: `config/keybind.ts` (name → key spec + `CommandMap`) + `keymap.tsx` (mode stack; a "managed textarea layer" makes `return` submit / `shift+return` newline / `ctrl+c` clear-input *only while the textarea is focused*). Same physical keys, different meaning by focus.
- **One command registry for both `/` and the palette**: palette-namespace commands declare `slashName` (+ aliases) and are collected dynamically (`useCommandSlashes()`); `autocomplete.tsx` and `command-palette.tsx` (ctrl+p) render from it, each decorated with its keybinding.
- **Model picker = generic list dialog** (`dialog-model.tsx` on `dialog-select.tsx`): Favorites → Recent → all providers' models, fuzzysort filter, ctrl+f favorite toggle. State in `context/local.tsx`: per-agent current + recent(10) + favorites persisted to `model.json`, plus `cycle_recent` (F2) / `cycle_favorite` keybindings.
- **History context-sensitive + stash**: `prompt/history.tsx` (JSONL, max50, dedupe) navigated by Up/Down only at buffer edges; a **stash** parks a draft.
- **Input stays live during streaming** — not disabled while running; you can type/queue the next prompt; only disabled during permission/question prompts. Status bar: animated spinner + `esc interrupt`, retry countdown, token usage `tokens (pct%) · $cost`.
- **Placeholders cycle** (`Ask anything… "<example>"`).

### 1.3 What we deliberately do NOT copy

- Solid.js / `@opentui` framework and the extmark engine wholesale — Zenith is Ink + React; we replicate the *behavior* (clean text + inline chips) with Ink primitives.
- OpenCode's hard-abort-on-2-escapes — Zenith already has a confirmation flow and Ctrl+C; keep Esc-as-interrupt with a distinct cancel RPC.
- Stash / workspace / `/move` machinery — out of scope for this pass (stash is an optional stretch).

---

## 2. Current Implementation (verified)

- **Composer** `tui/src/components/Input/CommandInput.tsx`: `❯` glyph + `MultiLineTextInput`, `─` divider, footer (mode label, `◇ model · provider`, short dir, `(branch)`, `tokens/max`, context gauge, `(Σ total)`, `N req`, Running/Idle). Rendered from `App.tsx:360-376` only when `!showAutocomplete && !showFilePicker && !isOverlayOpen`; currently `disabled={isRunning}` (input frozen while streaming — to change). When `disabled`, the composer swaps the editor for `◌` + "Processing... (Esc to cancel)".
- **Input core** `tui/src/components/Input/MultiLineTextInput.tsx`: hand-rolled buffer/cursor, `MIN_LINES=1` / `MAX_LINES=15`, Enter submits / Shift+Enter newline, Up/Down line-nav + history at edges, paste sanitation, inverse-char cursor.
- **State hooks** in `App.tsx`: `useAutocomplete` (input, history `~/.zenith/history.json` max50, `attachments[]` display-only — `addAttachment` is exported but **unused** today; `/`→autocomplete, `@`→file-picker whose select runs `insertFilePath`, which strips the `@` and inserts a raw path string, **not** an attachment), `useOverlayManager` (`OverlayType`: mode/help/settings/context/provider/models/usage, stacked), `useConversation`, `useScenario` (`startScenario(prompt, mode, provider)` → `wsClient.sendPrompt(prompt, mode, sessionId, provider)`), `useProvider`, `useTerminalKeyboard`.
- **Global keys** (`useTerminalKeyboard.ts:93-222`): confirmation y/n/esc (`:97-107`); `esc` closes overlay or aborts (`:109-120`); `ctrl+c` abort; `ctrl+l` clear; `ctrl+s` save plan; `ctrl+p` → help (`:148-151`); `ctrl+e` → models (`:153-156`); `ctrl+m` → mode (`:158-161`, dead in Ink — Ctrl+M arrives as `\r`); `ctrl+t`/`shift+t` → thinking. HelpModal documents "Shift+M Switch Mode" (mismatch).
- **Slash commands**: `services/api/options.json` + `CommandService.dispatchCommand` (exact slash match; actions overlay/clear/compact/clear_tools/mode). `AutocompleteDropdown` renders from `options.json` and **replaces** the composer (frozen filter — can't type more while open; no `onChange` wired back into the input). `options.json` already includes `/models`.
- **Model infra (reuse)**: `services/providers/ModelStore.ts` (`current`/`recent` max10/`favorite`, `set`, `cycle(reverse)`, `cycleFavorite`, `toggleFavorite`, `getFirstValidModel`, `isModelInProviders`); `ProviderRepository.getProviderInfoList()`; `ProviderService`. `screens/Provider/ModelPicker.tsx` (SearchList) **already wired** via `OverlayRouter.tsx:68-81` (`models` overlay) → `providerRepository.setModel` + `modelStore.set` + `providerService.notifyChange()`. UI kit: `SearchList`, `RoundedBox`, `PromptInput`, `ModalFooter`, `textBuffer.fuzzyScore`.
- **Backend `prompt.send`** (`server/api/handlers.py:317-378`): params `content|prompt, provider, mode, session_id`; resolves provider from `registry`; creates user `Message`; `executor.run(session_id, content, mode, handlers, manager)` (fire-and-forget); implicit cancel = next `prompt.send` calls `executor.cancel_active()` (`_session_executors`). Dispatch map `handlers.py:66-99` has **no** `prompt.cancel`; enum `JsonRpcMethod.PROMPT_CANCEL` exists in `protocol.py:25` (unused). `PromptExecutor.run/._execute` signatures currently `(session_id, content, mode, handlers, manager)`.
- **Backend seams**: `server/agents/context.py` `ContextManager.build_messages` (repo map, memory, AGENTS.md) is the natural attachment-injection point. `server/agents/loop.py:155-167` already swaps `provider.model` in try/finally for `model_override`. `LLMProvider.complete_typed` (`llm_provider.py:648-736`) already applies per-call `temperature`/`max_tokens` with a finally-restore; the streaming path used by the agent loop (`server/agents/llm_stream.py:71` → `_stream_impl` → `_build_completion_kwargs`) reads `self.max_tokens`/`self.temperature` at call time (`llm_provider.py:377-378`) — so mutating `provider.model`/`.temperature`/`.max_tokens` in a try/finally at the executor level is the correct seam for per-prompt overrides. `Message.metadata` persists via `metadata_json` (`repositories.py:280-292`); `Session` already has `model` + `metadata` fields (`session.py:31,40`).
- **Environment constraint**: Ink `Key` type has **no f1–f12 / alt** fields (verified against `node_modules/ink/build/hooks/use-input.d.ts` — only arrows, pageUp/Down, home/end, return, escape, ctrl, shift, tab, backspace, delete, meta, super/hyper) → model cycling uses `ctrl+n` / `ctrl+shift+n`, not F2.
- **Tests (keep green)**: `tui/tests/commandService.test.ts` drives `dispatchCommand('/help'|'/provider'|'/models'|'/clear'|'/compact'|'/clear-tools')` — the Phase 3 registry adapter must keep this passing (or be updated in the same phase). `tui/tests/backendScenarioProvider.test.ts` already exercises abort/no-partial-tail behavior.

---

## 3. Gap Analysis

| Capability | Today | Target |
|---|---|---|
| Multi-line + auto-resize | ✅ 15-line cap | ✅ keep; cap = min(15, rows/3) |
| Enter submit / Shift+Enter newline | ✅ | ✅ + `alt+enter`, `ctrl+j` |
| Declarative keybinding map | ❌ scattered `useInput` | ✅ central `keybind.ts` + `matchKeypress` |
| Inline `/` suggestions that keep filtering | ⚠ dropdown replaces composer | ✅ local filter buffer; registry-driven |
| Command palette (ctrl+p) | ❌ (ctrl+p = help today) | ✅ unified registry; help → `?`(empty)/`/help` |
| Two-stage provider→model selector | ⚠ overlay-only (`/models`) | ✅ `ModelPickerFlow` + footer chip + per-prompt model |
| Model cycle (recent/favorite) | ❌ (ModelStore.cycle unused) | ✅ `ctrl+n`/`ctrl+shift+n` |
| Per-prompt model/temperature/max_tokens | ❌ | ✅ `prompt.send` + WS client + submit path |
| Real file attachments (content → backend) | ❌ display-only chips, static list | ✅ `@` picker → real listing → chips → `prompt.send` |
| Explicit cancel RPC | ❌ | ✅ `prompt.cancel` + Esc wiring |
| Input live during streaming | ❌ `disabled={isRunning}` | ✅ editable; queue next prompt; Esc→cancel |
| History context-sensitive up/down | ⚠ works at edges | ✅ formalize + draft restore |
| Placeholder cycling | ❌ static | ✅ rotating examples |
| `↵ send` hint | ❌ | ✅ footer hint |
| Disabled/error/streaming states | ⚠ minimal | ✅ explicit + retry countdown + cancel affordance |

---

## 4. Design Principles

1. **Keyboard-first, minimal chrome** — the input is always focused; every action reachable from the keyboard; no mouse.
2. **One command registry** drives `/` autocomplete, the palette, and help — a single source of truth (OpenCode pattern).
3. **Clean text + inline chips** — attachments/paths render as styled chips without polluting the submitted plain text (extmark-inspired, Ink-native).
4. **Mode-aware keys** — the same `up/down/return/esc/tab` mean different things by focus (textarea vs suggestion list vs picker).
5. **Stay responsive while streaming** — input stays editable; running state is conveyed in the footer/status, not by freezing the composer.
6. **Reuse before build** — ModelStore, SearchList, RoundedBox, CommandService, WebSocketClient, `useProvider`, theme tokens; extend, don't duplicate.

---

## 5. Backend Contract

### 5.1 `prompt.send` wire shape (TUI → server)

```
content: string
provider?: string
mode?: 'build' | 'plan'
session_id?: string
model?: string                 // per-prompt override, e.g. "qwen3-coder-30b"
temperature?: number           // 0..2
max_tokens?: number            // >=1
attachments?: { path: string; name?: string; content?: string }[]
```

- TUI sends `{path, name}` (path-reference, no inline content) → small WS frames, IO on the server.
- Backend resolves paths against `config.workspace_root`, **path-traversal-guarded** (`is_relative_to`), **size-capped** (512 KB/file, 2 MB total), **binary** (null bytes in first 8 KB) skipped with a warning.
- `content` is an escape hatch for pasted file text (not used by the normal `@` flow).

### 5.2 `prompt.cancel`

```
{ session_id?: string } → { cancelled: boolean }
```

Wired into the dispatch map; idempotent (no-op if no active executor for the session).

### 5.3 Attachment injection point

Before `agent.process_prompt`, each attachment is read and prepended to `content` as:

```
<attachment path="…">…</attachment>
```

Injection into the user message lets it participate in normal context truncation and persists in `Message.content`. Unreadable/binary/oversized → `r.warning("Skipped attachment …")` and continue. A dedicated `build_messages` exempt block is a documented follow-up.

---

## 6. Keyboard Map

Declarative `keybind.ts`: `KeybindId` union + `KEYBINDINGS: Record<KeybindId, {keys, description}>` + pure `matchKeypress(_input, key, bindings)` + `formatKeyBind`.

| KeybindId | Keys | Action |
|---|---|---|
| submit | `enter` | Send message |
| newline | `shift+return`, `ctrl+return`, `ctrl+j` | Insert newline |
| history_up / history_down | `up` / `down` | Prev/next prompt (cursor at edge) |
| help | `?` | Help (empty input) |
| mode | `shift+m` | Switch mode (empty input) |
| palette | `ctrl+p` | Command palette |
| thinking | `ctrl+t`, `shift+t` | Toggle thinking |
| save_plan | `ctrl+s` | Save plan to file |
| clear_turns | `ctrl+l` | Clear conversation |
| clear_input | `ctrl+c` | Clear input / cancel run |
| interrupt | `escape` | Cancel running / close |
| model_picker | `ctrl+e` | Switch provider/model |
| model_cycle / model_cycle_reverse | `ctrl+n` / `ctrl+shift+n` | Cycle recent model |

**Conflict resolutions**
- `ctrl+p` (help today) → **command palette**; help → `?` (empty input) + `/help`.
- `ctrl+m` (mode, dead in Ink) → **removed**; mode → `shift+m` on empty input, handled in the composer's `onSpecial` (swallows the char, so it doesn't type an `M`).
- `ctrl+e` stays → models overlay (now renders the new two-stage `ModelPickerFlow`).

---

## 7. Implementation Phases

### Phase 1 — Backend: `prompt.send` extensions + `prompt.cancel`
**Files**: `server/api/handlers.py`, `server/agents/prompt_executor.py`, new `server/tests/test_prompt_overrides.py`.

- `_prompt` (handlers.py ~317): parse/validate `model` (strip), `temperature` (float 0..2), `max_tokens` (int ≥1), `attachments` (list of dicts with non-empty `path`; dedupe by path; cap 25). Set `user_msg.metadata["model"]` and `["attachment_paths"]` before persist (metadata persisted via `metadata_json`). If `model` set, update `session.model` + `session.metadata["last_model"]` (`session_repo.update`). Thread `model_override/temperature/max_tokens/attachments` into `executor.run(...)`.
- Add `"prompt.cancel": lambda: self._cancel_prompt(ws, rid, session_id)` to the dispatch map; `_cancel_prompt` calls `self._session_executors.get(session_id)?.cancel_active()`, replies `{"cancelled": bool}`.
- `PromptExecutor`: extend `run`/`_execute` with the 4 new args. In `_execute`, resolve `effective_model = model_override or plan_model_override` (per-prompt wins), apply `model/temperature/max_tokens` to `self._provider` in a **try/finally restoring originals** — covers both the standard loop and the sub-agent path. Provider pre-set → pass `model_override=None` to `agent.process_prompt`; no `loop.py` change needed. (Seam confirmed: `_build_completion_kwargs` reads `self.max_tokens`/`self.temperature` per call at `llm_provider.py:377-378`; the `complete_typed` finally-restore at `llm_provider.py:648-736` is the in-repo precedent. `Message.metadata` persists via `metadata_json` at `repositories.py:280-292`; `Session.model`/`.metadata` exist at `session.py:31,40`.)
- Attachment injection util (async read, traversal guard, size cap, binary skip) + prepend `<attachment>` blocks to `content`.
- Tests: fake provider records observed model/temp/max_tokens; assert mutation+restore, message metadata, session row, `prompt.cancel` cancels an in-flight task, traversal guard + size cap.

### Phase 2 — TUI transport
**File**: `tui/src/services/transport/WebSocketClient.ts`.
- `sendPrompt(content, mode='build', sessionId?, provider?, opts?: {model?, temperature?, max_tokens?, attachments?})`.
- Add `cancelPrompt(sessionId): Promise<{cancelled: boolean}>` → `prompt.cancel`.

### Phase 3 — Command registry + command palette
**Files**: new `tui/src/services/api/CommandRegistry.ts`, modify `CommandService.ts`, `AutocompleteDropdown.tsx`, new `CommandPalette.tsx`, modify `App.tsx`.
- `CommandRegistry`: module-level `CommandDef[]` — `{id, slash, title, description, category: 'Session'|'View'|'Mode'|'Model'|'Tools', keybind?, keywords?, hidden?, run(ctx)}`. Entries: existing `/help /settings /context /usage /provider /models /clear /compact /clear-tools /build /plan` + new `/model` (opens picker) + non-slash palette items ("Toggle thinking", "Switch mode", "Open model picker", "Save plan to file", "Clear conversation", "Command palette"). `CommandRunContext` gains `openModelPicker`, `openPalette`, `toggleThinking`.
- `CommandService.dispatchCommand` becomes a thin adapter over the registry (keeps exact-slash match, returns boolean). `options.json` stays as reference only. Keep `tui/tests/commandService.test.ts` passing — it drives `/help /provider /models /clear /compact /clear-tools` through `dispatchCommand` with the existing `CommandHandlers` shape, so the adapter must preserve the `dispatchCommand(raw, handlers)` contract (update the test in this phase only if the contract intentionally changes).
- `CommandPalette.tsx` = `SearchList` over `!hidden` commands with `gutter: formatKeyBind(keybind)`; select runs the command then closes.
- `AutocompleteDropdown`: build list from registry; add a local filter buffer (mirrors to a new `onQueryChange` prop) so `/filt…` keeps filtering (fixes the frozen-filter bug). Keep arrows/enter/esc/tab.

### Phase 4 — Composer UI redesign
**Files**: modify `CommandInput.tsx`, `MultiLineTextInput.tsx`, `hooks/useAutocomplete.ts`, `App.tsx`; new `components/Input/AttachmentChips.tsx`, `ComposerFooter.tsx`, `ComposerGauge.tsx`.

- Layout (one rounded card, Ink inline styles): `AttachmentChips` (when attachments) above; input row `❯ + MultiLineTextInput v2`; divider; footer: `[BUILD]/[PLAN] ◇ modelShort·provider` (left) · `dir·(branch) | tokens/max · gauge · ↵ send` (right).
- **Focus states**: `border.active` when focused & enabled; `border.muted` when disabled (confirmation pending → dim "Waiting for approval…"). Glyph `❯` emerald+bold when focused, dim otherwise.
- **Running state**: input stays editable; footer right shows `ASCII_SPINNER_FRAMES[tick]` (isolated in a `RunningSpinner` so idle frames don't tick) + `Esc cancel` (warning) instead of the send hint.
- **Placeholders cycle** every ~4s: `Ask anything…` / `Describe the change…` / `@ file · / cmd · ? help`; hidden when value non-empty.
- **Send hint**: `↵ send` (dim) when input non-empty & idle; `↵` only otherwise.
- **Model chip**: shows `modelStore.current` (`providerID/modelID`) when valid, else active-provider model; `▾`; subscribe to `modelStore` (force update) in a memoized child so the composer doesn't re-render on model changes.
- **`MultiLineTextInput v2`**: add `onSpecial?(char, key, value) => boolean` called first in `handleInput` (return `true` swallows the key) — used for empty-input `?` help, `shift+m` mode, idle `ctrl+c` clear-input (single handler, no double-fire races). Newline on `shift/ctrl/meta/return` + `\x0a`; plain return submits. Keep line-edge history, home/end, paste sanitation. Height `min(15, floor(rows/3))`.
- **`useAutocomplete`**: `@` opens picker; on select `addAttachment({path, name, mimeType, size})` (fs.stat + extension) and strip `@` from input. Add a `draftRef`: save pre-clear text on submit; `clearInput` restores the draft when called by `ctrl+c` idle.
- **`App.tsx`**: composer visible when `!showFilePicker && !isOverlayOpen && !showPalette`. Replace `disabled={isRunning}` with `running={isRunning}` and `disabled={!!(activeConfirmation && !activeConfirmation.answered)}`. Wire `onOpenModelPicker`, `onCancel`, `onOpenHelp`, `onOpenMode`.

### Phase 5 — Declarative keybinding map + key wiring
**Files**: new `tui/src/config/keybind.ts`; modify `useTerminalKeyboard.ts`, `MultiLineTextInput.tsx`, `screens/Help/HelpModal.tsx`.
- `keybind.ts` per section 6 (ids, key specs, `matchKeypress`, `formatKeyBind`).
- `useTerminalKeyboard` rewrite: keep confirmation y/n/esc; wire palette (ctrl+p), thinking, save_plan, clear_turns, model_picker (ctrl+e → `openOverlay('models')`), model_cycle (ctrl+n / ctrl+shift+n → `modelStore.cycle()`/`cycle(true)` then `set`), interrupt (esc: overlay/palette open → close; running → `prompt.cancel` + local abort). **Remove dead `ctrl+m` branch**; `?`/`shift+m` handled in the composer's `onSpecial`. New props from `App.tsx`: `showPalette/setShowPalette`, `openModelPicker`, `cycleModel`, `composerRunning`.
- `HelpModal`: render the `KEYBINDINGS` table; update to "Ctrl+P → Command palette", "? (empty input) → Help", "Shift+M (empty input) → Switch mode".

### Phase 6 — Two-stage Provider → Model picker
**Files**: new `components/Model/ProviderSelect.tsx`, `ModelSelect.tsx`, `ModelPickerFlow.tsx`; modify `routes/OverlayRouter.tsx` (`models` overlay → `ModelPickerFlow`), `hooks/useScenario.ts`, `hooks/useConversation.ts`, `App.tsx`, `CommandInput.tsx`.
- `ModelPickerFlow`: two-stage state machine (`provider` → `model`), `RoundedBox` container, esc backs/closes, enter selects/advances.
  - **Stage1 `ProviderSelect`** (SearchList): providers from `getProviderInfoList()` that are configured/connected AND have ≥1 model; `current` marker for `modelStore.current?.providerID`; `gutter '✓'` when configured; category Popular/Providers.
  - **Stage2 `ModelSelect`** (SearchList): reuse `ModelPicker.tsx` options logic (Favorites → Recent → provider models, dedupe, `current` markers) filtered to the chosen provider; `★ Favorite` action (Tab).
- On final select: `modelStore.set(sel)` **and** `providerRepository.setModel(sel.providerID, sel.modelID)` + `providerService.notifyChange()` (mirrors today's `OverlayRouter` behavior, preserves global provider-config persistence). Close overlay.
- **Submit path** (`App.tsx handleSubmit`): resolve `sel = modelStore.current` if valid in providers else null; `providerId = sel?.providerID ?? activeProvider.id`; `modelId = sel?.modelID`; `startScenario(prompt, mode, providerId, modelId, attachments)`. `useScenario.startScenario` → `wsClient.sendPrompt(prompt, mode, sessionId, provider, {model, attachments})`. `useConversation.addTurn(prompt, mode, model?)` stores model on the turn for the header; `handleRetry` passes it back.

### Phase 7 — Cancel/interrupt + streaming UX
**Files**: `hooks/useScenario.ts`, `services/transport/BackendScenarioProvider.ts`, `App.tsx`; backend done in Phase 1.
- `useScenario.abort()`: `runnerRef.current?.abort()` + `setIsRunning(false)`/`setActiveConfirmation(null)` **already exist** (`useScenario.ts:182-186`); the only new work is `wsClient.cancelPrompt(sessionIdRef.current)` (if set).
- `BackendScenarioProvider.execute`: the `aborted` flag **already exists** — `abortFlag` (`BackendScenarioProvider.ts:13`) is checked at the top of the event handler (`:147`) and set by `abort()` (`:304-307`), so events after abort are already dropped (no partial-message tail). No code change; keep `tui/tests/backendScenarioProvider.test.ts` green as the guard.
- Composer stays interactive while running; Enter during a run issues a new `prompt.send` and the backend's existing `executor.cancel_active()` on re-send stops the previous turn (coarse "queue next prompt"). A true task queue is a documented follow-up.

### Phase 8 — History + draft (stretch)
**Files**: `hooks/useAutocomplete.ts`, new `services/history/promptHistory.ts`; optional `/stash` (JSONL `~/.zenith/stash.jsonl`, max10).
- Minimum: draft-restore (Phase 4) + keep `history.json` max50 with consecutive-dedupe.
- Stretch: `/stash`, `/stash list`, `/stash pop` if time permits.

### Phase 9 — Polish, performance, verification
- Memoize new children (`ComposerFooter`, `ComposerGauge`, `AttachmentChips`); `commandRegistry` is a module-level const; spinner isolated in `RunningSpinner`; turn list already `<Static>`. Height capped (`min(15, rows/3)`); paste path O(n)/keypress.
- Run the verification matrix (section 9).

---

## 8. File Structure

### New TUI files
```
tui/src/
├── config/
│   └── keybind.ts                  # KeybindId, KEYBINDINGS, matchKeypress, formatKeyBind
├── components/
│   ├── Input/
│   │   ├── AttachmentChips.tsx      # attachment chip row
│   │   ├── ComposerFooter.tsx       # footer row (mode·model | dir·tokens·gauge·send hint)
│   │   ├── ComposerGauge.tsx        # 10-block context gauge
│   │   ├── RunningSpinner.tsx       # isolated spinner (idle frames don't tick)
│   │   └── CommandPalette.tsx       # SearchList wrapper over the registry
│   └── Model/
│       ├── ProviderSelect.tsx       # stage 1: provider list
│       ├── ModelSelect.tsx          # stage 2: model list (Favorites/Recent/All)
│       └── ModelPickerFlow.tsx      # two-stage state machine
└── services/
    ├── api/
    │   └── CommandRegistry.ts       # single command source of truth
    └── history/
        └── promptHistory.ts         # history helpers (extracted from useAutocomplete)
```

### New backend file
```
server/tests/test_prompt_overrides.py
```

### Modified files (representative)
- `server/api/handlers.py`, `server/agents/prompt_executor.py`
- `tui/src/services/transport/WebSocketClient.ts`
- `tui/src/services/api/CommandService.ts`, `tui/src/components/Input/AutocompleteDropdown/AutocompleteDropdown.tsx`
- `tui/src/components/Input/CommandInput.tsx`, `tui/src/components/Input/MultiLineTextInput.tsx`
- `tui/src/hooks/useAutocomplete.ts`, `tui/src/hooks/useTerminalKeyboard.ts`, `tui/src/hooks/useScenario.ts`, `tui/src/hooks/useConversation.ts`
- `tui/src/App.tsx`, `tui/src/routes/OverlayRouter.tsx`, `tui/src/screens/Help/HelpModal.tsx`
- Tests: `tui/tests/commandService.test.ts` (Phase 3), `tui/tests/backendScenarioProvider.test.ts` (Phase 7 guard — no change expected)

---

## 9. Verification

1. Backend: `cd server && python -m server.main serve` (binds `ws://localhost:8765/ws`); `python -m server.main db init` if needed.
2. TUI: `cd tui && npm run dev` (`ZENITH_BACKEND_URL` or default).
3. Checks: `npm run typecheck && npm run lint && npm run test` (TUI); `python -m pytest server/tests` (backend).
4. Manual matrix:
   - Multi-line (shift/ctrl+enter), large paste, auto-resize cap, `↵ send` hint show/hide.
   - `/` autocomplete filters and runs; `/model` opens picker; `?`(empty) opens help; `shift+m`(empty) opens mode; both type normally when input non-empty.
   - `ctrl+p` palette (commands + keybinding gutters, fuzzy filter).
   - `ctrl+e` two-stage picker; `ctrl+n`/`ctrl+shift+n` cycle recent models, footer chip updates, selection persists across restart (`~/.zenith/model.json`).
   - Submit with a chosen model → backend log `PROMPT.RESOLVED provider=… model=…`; session row + message metadata updated.
   - `@` attaches a real file → chip → submit → backend logs the `<attachment>` block; traversal guard rejects `../outside`; binary file skipped with a warning.
   - Esc during a run → `prompt.cancel`, executor cancelled, UI idle quickly, next prompt works. Input editable while running; Enter queues next prompt.
   - Confirmation flow: tool permission → composer disabled ("Waiting for approval…"), y/n works.
   - ctrl+c idle clears input; draft restored.

---

## 10. Follow-ups (Deferred)

- True prompt task queue (queue vs replace on Enter-during-run).
- Dedicated `build_messages` exempt block for attachments (currently injected into the user message).
- Stash (`/stash`, `/stash list`, `/stash pop`) if not shipped in Phase 8.
- Inline autocomplete popover *above* the composer (vs. replacing it) — Phase 3 keeps replace-behavior but fixes the frozen filter.
- Session turn-history API for up-arrow-through-assistant-turns (currently only `session.resume`/`session.sync`).
