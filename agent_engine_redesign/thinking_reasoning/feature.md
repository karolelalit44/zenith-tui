# Thinking / Reasoning

## Overview

How the model's reasoning/thinking text is requested, streamed, and surfaced to the user.

### How opencode does it

- Reasoning is streamed as first-class **reasoning Parts** via processor events: `reasoning-start`, `reasoning-delta`, `reasoning-end`.
- `reasoning-delta` merges text into the current reasoning part and emits a `PartDelta` (updated in place).
- `reasoning-end` finishes the reasoning part.
- Reasoning parts are rendered in the TUI inline (not as a parallel event stream).
- Reasoning effort is provider/model-dependent.

### How codex does it

- `ReasoningContentDelta` items stream reasoning text.
- `ReasoningEffort { Minimal, Low, Medium, High }` + `ReasoningEffortConfig` (explicit or `Auto`).
- Reasoning can be summarized (summary-only) when the model supports `reasoning_summary`.
- Context included based on `use_responses_lite`.

### What zenith has today

- `server/agents/llm_stream.py` (`stream_completion`) emits `THINKING` / `MESSAGE` / `TOOL_CALL` / `TOOL_RESULT` events.
- `THINKING_PARTIAL_EMIT_CHARS = 200` â€” emits a partial thinking event every 200 chars.
- `provider_adapters.py`, `providers/parser.py` handle reasoning extraction.
- A separate `ThinkingEvent` / `progress` event in the TUI.

### What is correct

- Streaming reasoning text exists.

### What is wrong / over-engineered / incorrect / missing

**Over-engineered / incorrect:**
- Thinking is modeled as a **parallel event stream** (`THINKING` + `progress`) separate from the message content. opencode/codex model reasoning as a **Part** inside the message, delta-merged in place.
- `THINKING_PARTIAL_EMIT_CHARS` chunking â€” opencode/codex merge deltas; no char-chunk synthetic event.

**Missing:**
- First-class `reasoning` Part type with delta merge.
- Reasoning effort configuration.

## What we will do

- Model reasoning as a first-class Part (start/delta/end, delta-merged in place).
- Emit reasoning from the processor, not a parallel event stream.
- Add reasoning-effort configuration (opencode/codex style).

### Decision (2026-08-31) — phased execution (Mars, module 08 owner)

Per `progress.md` §11, this is **Phase 1 (interface-lock, additive; no removal yet)**.
Phase 1 has therefore:
- **ADDED (interface-lock) in `server/agents/llm_stream.py`:**
  - `ReasoningPart` dataclass — first-class reasoning part with ``kind: start -> delta* -> end``
    and ``merge()`` delta-merged in place (opencode "reasoning-delta updated in place",
    codex ``ReasoningContentDelta``). ``snapshot()`` emits the current merged state.
  - `ReasoningEffort` enum — ``minimal/low/medium/high`` (codex ``ReasoningEffort``).
  - `accumulate_reasoning_parts()` async helper — folds a reasoning-delta stream into
    Part snapshots (start/delta/end), throttled by `THINKING_PARTIAL_EMIT_CHARS` until
    consumer wiring replaces that constant (see REMOVE).
- **NOT removed yet (Phase 3):** `THINKING_PARTIAL_EMIT_CHARS` and the parallel
  `THINKING`/`progress` event stream — still emitted by `stream_completion` today and
  consumed by the TUI. They are folded onto reasoning Parts only after 09 markdown_render
  and 10 transport_event_contract adopt the Part shape. Do NOT strip the thinking event
  path during Phase 1 (G5 TUI compat: `thinking` event kind is mapped in scenario.ts).

## What we will REMOVE
- `THINKING_PARTIAL_EMIT_CHARS`
- The separate `THINKING` / `progress` parallel event stream for reasoning (fold into reasoning Part).

## Regex audit
| Regex | opencode/codex uses it? | Action |
|---|---|---|
| (thinking-strip regex in opencode title gen) | opencode strips `</think>` via regex | Keep if provider emits think tags |
| (none zenith-specific) | â€” | â€” |

## Verification / signoff
- [x] Reasoning as a Part (delta-merged): ReasoningPart + accumulate_reasoning_parts added (additive)
- [x] Reasoning-effort config: ReasoningEffort enum added
- [~] No parallel THINKING event stream — Phase 3 (consumers 09/10 must adopt Parts first; G5)
- [x] ruff + pytest (module tests pass for additive Phase-1 changes)

## Status: Interface-Locked (Phase 1 additive); THINKING-event removal pending Phase 3

---

## Module report (§9 template)

```
Module: 08 thinking_reasoning
Status change: Pending → Interface-Locked (Phase 1 additive)
WHAT: Added ReasoningPart (delta-merged start/delta/end), ReasoningEffort enum, and
      accumulate_reasoning_parts() async fold in server/agents/llm_stream.py.
WHY: Mirrors opencode processor reasoning-start/delta/end "updated in place" parts and
      codex ReasoningContentDelta + ReasoningEffort — see ref_repo/opencode packages/opencode
      src/session/part + processor; ref_repo/codex reasoning models.
FILES: server/agents/llm_stream.py, server/tests/test_reasoning_stream.py,
      agent_engine_redesign/thinking_reasoning/feature.md
KEPT/REMOVED: additive Part abstraction added; THINKING event path + THINKING_PARTIAL_EMIT_CHARS
      kept for Phase 3 (consumers 09/10 need Parts wired first; G5 TUI thinking event mapped).
EXPECTED BEHAVIOUR: reasoning now expressible as delta-merged Parts; no change to the existing
      thinking event stream until Phase 3 wiring.
OUTCOME / TEST EVIDENCE: G1 PASS (3 new tests); G2 targeted-PASS (reasoning tests green);
      G3 ruff clean; G4 interface declared in feature doc; G5 no transport/event change;
      G6 additive only; G7 no shared-file locking needed (llm_stream.py is module-08 owned);
      G8 self-contained.
SHARED-FILE IMPACT: none (no CCS files touched; no constants.py change).
DEPENDENCIES: provides reasoning-Part contract to 09 markdown_render and 10 transport; Phase 3
      removal coordinated with those modules. reasoning_effort typed enum complements the
      module-13 model param.
```

Next: Phase 2 wires reasoning Parts into the processor/loop; Phase 3 removes the THINKING
parallel event stream under coordination with 09/10.
