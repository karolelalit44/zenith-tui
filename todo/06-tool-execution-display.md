# 06 — Tool execution display: merge "RUN" + "Create" into one professional card

> Area: `tui/src/components/Display/Scenario/ToolCallCard.tsx`, `ToolResultCard.tsx`, `componentRegistry.tsx`, `useScenario.ts`
> Severity: **High (UX)** — every tool execution is rendered twice with different verbs/icons, and skipped-call warnings spam the transcript.

---

## 1. Summary

A single `file_write` renders as **two separate cards**: a `ToolCallCard` (`└ RUN file_write …`) and then a `ToolResultCard` (`● Create(...) …`). They duplicate the same information (the command, then a near-identical tool name + params), with inconsistent icons and verbing, plus 13+ identical `▲ [WARNING] Skipped calls …` blocks in the transcript. What should be one tight "tool step" line is a wall of noise.

## 2. What is currently happening (evidence)

From the frontend log, one write produced:

```
└ RUN file_write
   path: "library-mgmnt-sys/requirements.txt", overwrite: true, content: "..."
● Create(path="library-mgmnt-sys/requirements.txt", ...)
   Status: Success (233 B) · 331ms
```

And per stalled iteration (×13+):

```
▲ [WARNING] Skipped calls already completed with identical params this turn:
   file_write(path=library-mgmnt-sys/requirements.txt), file_write(...), file_write(...)
▲ [WARNING] [System] No new tool was executed this iteration; every call you emitted was already attempted earlier…
```

### Structural causes
- `componentRegistry.tsx` registers **two separate event types** — `tool_call` → `ToolCallCard`, `tool_result` → `ToolResultCard` — so a tool step is two cards by construction.
- `useScenario.ts` processes the two events independently; nothing pairs a `tool_call` with its `tool_result` (the backend does provide a shared tool-call id, but the UI doesn't join on it).
- The "RUN" card shows raw params (`path`, `overwrite`, full `content`); the result card re-derives a "verb" (`Create`) from the tool name and re-shows the path. Verbing/inlining logic is duplicated in both cards.
- `ToolCallCard` ignores the `text` field the backend sends (`"Executing …"`), rendering its own header instead.
- Skipped-call warnings are emitted as full `[WARNING]` blocks, one per iteration, with the full call list, and rendered verbatim.

## 3. Impact

- Every tool step takes 2 cards + 2 different icon styles → a 10-file build becomes 40+ visual units.
- Duplicated params (especially `content`) blow up the transcript and make errors hard to scan.
- Warning spam buries real results and makes the agent look broken (it was part of the observed "model is looping" signal, but the UI amplified it ~13×).
- A user skimming the transcript can't tell "what actually got created" from "what was attempted".

## 4. What the correct behaviour should be

### 4.1 One card per tool step (pair tool_call + tool_result)
Render a single card like Claude Code / Aider's minimal style:

```
● file_write   path: library-mgmnt-sys/requirements.txt
   ✓ Created library-mgmnt-sys/requirements.txt (233 B) · 331ms
```

- **While running**: a spinner + `● file_write …` (collapsible params).
- **After done**: static icon + status line; params collapsed under `▶ details`.
- Icon follows a single small set (e.g. `●` for tool steps, `✓`/`✗` for outcome), never a verb (`RUN`, `Create`).

### 4.2 Param hygiene
- Show `path`/the primary key, and the diff-relevant params; **hide** `overwrite` defaults and full `content` behind `▶ details`.
- Derive the display verb once, in one shared helper, keyed off the tool name (`file_write` → not "Create").
- Fix `ToolCallCard` to use the backend's `text` field (or drop the field) — don't render a second header.

### 4.3 Silence skip noise
- Skipped duplicates should be **silently collapsed** in the UI. At most one compact line per turn: `3 duplicate tool call(s) skipped silently (file_write → requirements.txt)`, and only if the user expands it.
- The `[System] No new tool was executed…` message should never be shown verbatim as a warning block; it's internal guidance (see `01-…` §5.2) and belongs in the loop, not the transcript.

### 4.4 Implementation notes
- Preferred: merge at the **source** — backend already pairs calls via a tool-call id; emit a single `tool_step` event (or have the TUI join `tool_call`+`tool_result` on that id and render one card). Recommend `componentRegistry` keep a single `tool_step` component.
- Keep history replay compatible (63-event replay path) when adding the pairing.

## 5. Happy flow (step by step)

1. Model calls `file_write(path=…, content=…)`.
2. UI shows `● file_write  path: …` with a spinner.
3. Result arrives → the card resolves to `✓ Created … (233 B) · 331ms`; params collapse.
4. A duplicate is skipped → nothing visible (silently deduped), or one collapsed line if the user expands the turn's "N skipped" marker.
5. The transcript for a 10-file build reads as 10 clean tool-step lines + the final summary.

## 6. Fix checklist

- [ ] Pair `tool_call` ↔ `tool_result` by tool-call id in `useScenario.ts` (or adopt a unified `tool_step` event on the backend).
- [ ] Create one merged card component; deregister the separate `ToolCallCard`/`ToolResultCard` for `tool_call`/`tool_result`.
- [ ] Share a single display-verb/params helper; hide `overwrite` + full `content` behind `▶ details`; use the `text` field.
- [ ] Collapse skipped-call warnings to a single, expandable marker per turn; suppress the `[System] …` guidance text from the transcript.
- [ ] Regression check: replay a saved transcript (63-event replay) and assert each tool step is exactly one card.
