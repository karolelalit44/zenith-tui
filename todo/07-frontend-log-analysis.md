# 07 — Remaining frontend rendering mistakes (from the observed transcript)

> Area: `tui/src/components/Display/Scenario/*` (`MessageBlock.tsx`, `ScenarioRenderer.tsx`, `WarningBlock.tsx`, `ErrorBlock.tsx`, `ThinkingBlock.tsx`), `tui/src/hooks/useScenario.ts`, `tui/src/screens/Composer/*`
> Severity: **Medium** — several small, independent rendering defects that together made the failed run look broken, and would clutter even successful runs.

---

## 1. Summary

Beyond the big items (`06-tool-execution-display.md`, `03-error-message-to-ui.md`, `05-integrity-and-ux.md`), a detailed pass over the frontend log turned up a batch of smaller issues: giant raw tool-schema JSON rendered as a "tool result", inconsistent icon/verb conventions, a 20-event history cap that hides context mid-run, an ever-present "Working…" spinner, dead/ignored fields, and a stale error panel with no actions. Each is cheap to fix and improves the transcript a lot.

## 2. Findings (with evidence from the log)

### 2.1 Raw tool-definition JSON dumped into the transcript
```
✓ [GET_TOOL_DEFINITION] Completed
{ "tool": { "name": "file_write", "description": "…", "parameters": { "$schema": "…", "properties": { "path": {…}, "content": {…} }, … } } }
```
The `GET_TOOL_DEFINITION` tool result (a full JSON schema, multi-KB) is rendered verbatim via the default result renderer. A tool-schema fetch is **internal plumbing**; it should render as one compact line (`Loaded tool definition file_write`) or be filtered out entirely.

### 2.2 Inconsistent iconography and verbing per event type
Observed: `└ RUN`, `● Create(…)`, `✓ [GET_TOOL_DEFINITION] Completed`, `✓ / ✗ [RUN …]`, `▲ [WARNING]`, `✗ [FAILED]`, `›` (thinking). The same *kind* of event (a tool step) is `└ RUN` at call time and `● Create` at result time. Icons and verbs should come from one small set (see `06-…` §4).

### 2.3 The 20-event history cap hides the beginning of the task
```
… 43 earlier events hidden … (dynamicLimit = 20, ScenarioRenderer.tsx:90)
```
Mid-build, everything before the last 20 events is collapsed to a "… N earlier events hidden" line. For a long build the user loses sight of the *original request* and early decisions. Recommendation: keep the cap for *tool internals* but always pin the first user message + the first assistant message, and make "show N earlier" a one-key expand.

### 2.4 The assistant greeting/plumbing is replayed as content
The transcript replays `Hello! How can I help you today?` (an old turn's assistant message) followed by `• Thought for 500ms` and `* Processing your request in build mode…`. The greeting is stale history; the "Processing your request…" bullet is status text rendered as if it were a message. History replay should filter assistant greetings / status bullets, or the greeting should not be persisted as a content message.

### 2.5 Thinking blocks: noisy and collapsed-but-verbose
```
Thinking › Thought for 500ms (ctrl+o to collapse)
```
Every iteration adds a `Thought for Nms` header, and the block content is collapsed by default yet the header still takes a line each time — ~18 lines of pure "thought for Xms" in this run. Suggest: show only when there is actual reasoning text; otherwise one thin indicator or nothing; and don't log a distinct block per stalled iteration.

### 2.6 The "Working · Xs · esc to interrupt" banner is always visible
`LiveSpinner`/status bar shows `Working · 42s · esc to interrupt` for the whole turn including during the long post-failure stall. For non-interruptible states (rate-limit cooldown, finalization) the "esc to interrupt" hint is wrong, and during multi-minute turns it's constant noise. Scope it: show only when an interrupt is actually possible and meaningful.

### 2.7 Dead/ignored fields and properties
- `ErrorBlock.tsx:10` declares `_MAX_MESSAGE_LENGTH = 200` and never uses it (see `03-…`).
- `ToolCallCard` ignores the backend `text` field (`Executing …`).
- Error events never carry `provider`, so `event.provider` renders nothing.
- `WarningBlock` renders the full warning string with no length cap or collapse, which is why 13 identical multi-line skip warnings each took ~6 lines.

### 2.8 No affordances on the error panel
The final `[FAILED] … Execution halted` panel has no actions. In the failure case specifically the user is told nothing about what to do next (retry, continue, change model, view logs). See `03-…` §5.3 and `05-…` §5.3.

### 2.9 Fragile index-based event patching in `useScenario`
Partial/message events use an `index` field for in-place replacement. Over the 63-event replay + live event stream this is a weak contract (ordering corruption risk if replay order changes). Prefer event ids / sequence numbers for patch targets.

## 3. Impact

- Every one of the above compounds: a failing run reads as raw JSON + warnings + stutter + a dead panel, and even a *successful* build is cluttered.
- The `GET_TOOL_DEFINITION` schema dump can leak internal API shape to users (minor info-hazard) and bloats saved transcripts.
- The always-on "Working" banner + thought timers add anxiety without information.

## 4. Recommended fixes (in priority order)

1. **Filter/compact internal events** — never render `GET_TOOL_DEFINITION` payloads verbatim; show `Loaded tool definition file_write` (or hide).
2. **Unify icon + verb set** for tool steps (see `06-…`); introduce a tiny `icons` map and a `verb(toolName)` helper used everywhere.
3. **Pin-first-message in replay** — keep the user request visible despite `dynamicLimit`; make "N earlier events" a one-key expand.
4. **Clean history replay** — drop assistant greetings/status bullets from replay; don't persist them as content.
5. **Tame thinking blocks** — show a block only when there is reasoning text; otherwise nothing (or a single thin line).
6. **Scope the Working banner** — show `esc to interrupt` only when interrupt is possible; consider hiding after N minutes of stall.
7. **Use declared constants** — wire up `_MAX_MESSAGE_LENGTH` + expand/collapse in `ErrorBlock` and `WarningBlock`.
8. **Add error-panel actions** — Retry / Continue / Change model driven by `code`/`recoverable`/`action` (see `03-…`).
9. **Replace index-based patching** with id-based patching in `useScenario`.

## 5. Happy flow (step by step)

1. Task starts → the user request stays pinned; a compact thinking line shows actual reasoning only.
2. Each tool step renders as one clean card; `GET_TOOL_DEFINITION` is invisible plumbing.
3. Warnings appear only when actionable (and collapsed); the Working banner shows only during genuinely interruptible phases.
4. On failure, a clean panel with a message, provider, and Retry/Continue/Change-model actions.
5. The transcript stays readable top to bottom even for a 30-file build.

## 6. Verification checklist

- [ ] Grep transcript replay test: assert no raw `GET_TOOL_DEFINITION` JSON is rendered.
- [ ] Assert the first user message is always visible despite `dynamicLimit`.
- [ ] Assert exactly one icon/verb style per tool step after the `06-…` merge.
- [ ] Assert `_MAX_MESSAGE_LENGTH` is referenced (no unused constant) and warnings are capped/collapsible.
- [ ] Screenshot-compare a 10-file successful build before/after for transcript length.
