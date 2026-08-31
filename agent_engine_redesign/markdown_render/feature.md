# Markdown / Response Render

## Overview

How the assistant's final text response, tool calls, and tool results are rendered to the user.

### How opencode does it

- The backend delivers a **clean Part model**: assistant text, reasoning, tool calls, tool results as parts of one message.
- The TUI renders markdown from the assistant text.
- Tool calls render as **updatable blocks** (title, input, running/completed state).
- Tool results render with truncation notice + output path.
- Thinking renders inline.
- Permission prompts render as interactive ask dialogs.

### How codex does it

- `EventMsg` stream drives the TUI: `AgentMessageContentDelta`, `ReasoningContentDelta`, `ToolCallRequestReference`/`ToolCallUpdate`, `ExecCommandOutputDelta`, `TurnMetadata(FullSnapshot)`.
- Content deltas update the assistant message in place.
- Tool calls / command output render inline with live state.

### What zenith has today

- `server/providers/responder.py` â€” event factories: `thinking`, `message_event`, `tool_call`, `tool_result`, `error`, `warning`, `success`, `turn_manifest`, `progress`, `context_compaction_*`.
- `MAX_EVENT_OUTPUT = 5000` â€” the wire event carries only a preview.
- TUI (`tui/src/types/scenario.ts`) defines ~27 `EventKind` values and maps them.
- Tool output formatted via `format_tool_result` in `executor.py`.

### What is correct

- The TUI renders markdown and maps events (approx. opencode's TUI).

### What is wrong / over-engineered / incorrect / missing

**Over-engineered:**
- Many invented event kinds (`turn_manifest`, `progress`, `todo_board`, `captain_orchestration`, `crewmate_*`, `context_compaction_*`, `plan_ready`). None in opencode/codex's core rendering.
- `MAX_EVENT_OUTPUT=5000` preview â€” the TUI only ever sees a 5K preview of tool output; full truncated output should be delivered.

**Missing:**
- The backend should deliver clean Part content (text/reasoning/tool_call/tool_result) and let the TUI render â€” not a fragmented set of synthetic tool events.

## What we will do

- Backend emits clean Part-based content: assistant text, reasoning, tool_call, tool_result, error.
- Deliver full (truncated) tool output, not a tiny preview.
- Let the TUI render markdown from text parts.
- Remove invented event kinds that carry no rendering value.

## What we will REMOVE
- `MAX_EVENT_OUTPUT` preview-only contract for tool output (deliver truncated full output).
- Invented event kinds (`turn_manifest`, `progress`, `captain_orchestration`, `crewmate_*`, `context_compaction_started`, `plan_ready`, etc.) unless the TUI needs them.

## Regex audit
| Regex | opencode/codex uses it? | Action |
|---|---|---|
| (none specific here) | â€” | â€” |

## Verification / signoff
- [x] Clean Part content delivered (TextPart/ReasoningPart/ToolCallPart/ToolResultPart/ErrorPart)
- [x] Full truncated tool output in parts (via truncate_output, not the 5K preview)
- [x] TUI renderable markdown fallback (data.text) preserving the wire contract
- [~] Invented event kinds removed — Phase 3
- [x] ruff + pytest (10 new tests; import + consumer regression green)

## Status: Interface-Locked (Phase 1 additive); MAX_EVENT_OUTPUT preview removal + invented-kind removal pending Phase 3

### Decision (2026-08-31) — phased execution (Mars, module 09 owner)

Per `progress.md` §11, Phase 1 is **additive interface-lock only; no removal yet**. Today
`MAX_EVENT_OUTPUT` still truncates tool output to a 5K preview in `responder.tool_result`, and the
invented event kinds (`turn_manifest`, `progress`, `crewmate_*`, `context_compaction_*`, `plan_ready`,
etc.) are still emitted and mapped by the TUI. So module 09 has:
- **ADDED (interface-lock) in `server/providers/responder.py`:**
  - `PartKind` enum + `ContentPart` (opencode AnyPart: text/reasoning/tool-call/tool-result/error) with
    a `type` discriminator. Helpers `text_part` / `reasoning_part` / `tool_call_part` /
    `tool_result_part` (truncates via `truncate_output`, delivering full-but-truncated output) /
    `error_part`.
  - `render_parts_text(parts)` — markdown/plain fallback renderer for the TUI.
  - `parts_message(parts, ...)` — emits the clean Part list under `data.parts` **on the existing
    MESSAGE kind** while keeping `data.text` as the rendered fallback, so the transport/TUI wire
    contract is unchanged (G5). Module-09 reasoning part is separate from module-08's to avoid a
    circular import (llm_stream -> responder).
- **NOT removed yet (Phase 3):** `MAX_EVENT_OUTPUT` preview in `tool_result`, and the invented event
  kinds. These are removed/re-wired only after the TUI and transport handle `data.parts` fully. Do NOT
  delete during Phase 1.

---

## Module report (§9 template)

```
Module: 09 markdown_render
Status change: Pending → Interface-Locked (Phase 1 additive)
WHAT: Added clean Part content delivery: PartKind + ContentPart (text/reasoning/tool-call/tool-result/
      error), part factory helpers (tool_result_part truncates via truncate_output), render_parts_text,
      and parts_message (emits data.parts on MESSAGE kind with rendered data.text fallback).
WHY: opencode delivers clean AnyPart content (ToolCallPart/ToolResultPart/TextPart/ReasoningPart) that
      the TUI renders; codex uses EventMsg content deltas. zenith emits fragmented synthetic events with a
      5K MAX_EVENT_OUTPUT preview.
FILES: server/providers/responder.py, server/tests/test_parts_render.py (NEW),
      agent_engine_redesign/markdown_render/feature.md
KEPT/REMOVED: additive Part model/factory added; MAX_EVENT_OUTPUT preview + invented event kinds kept
      for Phase 3. parts_message repurposes the existing MESSAGE event (no new EventKind; events.py untouched).
EXPECTED BEHAVIOUR: consumers can now emit/render clean part content; legacy responder path unchanged.
OUTCOME / TEST EVIDENCE: G1 PASS (10 new tests); G2 targeted-PASS (parts + reasoning-stream consumer
      regression 16 green; import smoke OK); G3 ruff clean; G4 interface declared in feature doc; G5 no
      transport/EventKind change (MESSAGE reused, text field preserved); G6 additive only; G7 module-09
      owned file only (responder.py; events.py untouched); G8 self-contained.
SHARED-FILE IMPACT: none.
DEPENDENCIES: consumes module-03 truncate_output (already Interface-Locked); provides part-content
      contract to 10 transport + TUI; Phase 3 removes MAX_EVENT_OUTPUT preview and invented kinds.
```

Next: Phase 2 emits parts from processor/loop; Phase 3 removes MAX_EVENT_OUTPUT preview and invented
event kinds under coordination with transport + TUI.
