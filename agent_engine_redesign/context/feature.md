# Context

## Overview

Context management: what is injected into the LLM request (system prompt, environment, repo map, skills, instructions, history, compaction summary) and how it is budgeted/optimized.

### How opencode does it

- System prompt assembled as: `env` + `instructions` + MCP notes + skills (`sys.environment` / `instruction.system` / `sys.mcp` / `sys.skills`).
- History via `MessageV2` (filter compacted messages).
- Completion check: last assistant finished & no tool calls.
- Compaction: thresholds `DEFAULT_BUFFER = 20000`, `DEFAULT_KEEP_TOKENS = 8000`, `TOOL_OUTPUT_MAX_CHARS = 2000`, `PRUNE_MINIMUM = 20000`, `PRUNE_PROTECT = 40000`. A single compaction service builds a summary using a fixed `SUMMARY_TEMPLATE`.

### How codex does it

- **ContextFragment** model (`context-fragments/src/fragment.rs`): `ContextualUserFragment { role, markers, body, content_kind }`.
- `render()` wraps body in open/end marker tags â†’ `RenderedFragment`.
- Every injected block is a tagged fragment: agents.md, base/developer instructions, environment, token budget, persistent/collaboration state, plugins, skills, etc.
- `world_state.rs` builds sections per step (ModelInstructions, agents.md, app tool policy, environment, token budget, etc.).
- **explicit, provenance-tagged, predictable slots** â€” the model and harness both know where each block came from.
- Compaction driven by `TokenBudgetConfig { max_tokens, compaction mode }` (Auto/Manual).

### What zenith has today

**Files:**
- `server/agents/context.py` â€” `ContextManager.build_messages` using 5 **tiers**:
  - T0: static system prompt + minimal tool schemas
  - T1: volatile blocks (repo map / plan)
  - T2: summary (running summary â‰¤ 1K)
  - T4: scored history (rolling window)
  - T5: user prompt verbatim
- Tier allocation via `MODE_BUDGET_PROFILES` with per-mode fractions (`tools_pct`, `history_pct`, `summary_pct`) per build/plan/read_only mode.
- `score_entry` scoring history entries; orphaned tool results dropped; stale reads penalized `STALE_TOKEN_MULTIPLIER = 2`.
- `SESSION_STATE` injection (list of files already written this session).
- `server/agents/running_summary.py` â€” background scheduler building summaries with a weak model.
- `server/agents/compaction_service.py` â€” CompactionService.

**Constants:**
- `TIER_T0/T1/T2/T4/T5`
- `MODE_BUDGET_PROFILES`
- `STALE_TOKEN_MULTIPLIER = 2`
- `SESSION_STATE_*` (MAX_TOKENS 400, MAX_FILES 50, marker/hash parsing)
- `SUMMARY_FRAMING_TOKENS`, `MIN_OUTPUT_RESERVE_TOKENS`, `HARD_STOP_USAGE_RATIO`
- `MAX_TOOL_OUTPUT_TIERS`, `MAX_TOOL_OUTPUT_BASELINE`

### What is correct

- The idea of a running summary + compaction on threshold.
- Token budgeting exists.

### What is wrong / over-engineered / incorrect / missing

**Over-engineered / incorrect:**
- **5-tier scored context** with `score_entry`, `STALE_TOKEN_MULTIPLIER`, orphan-dropping. This is bespoke and non-standard. opencode/codex use explicit fragment slots / simple policies, not scoring heuristics.
- `MODE_BUDGET_PROFILES` per-mode fraction tuning â€” not in the reference.
- `SESSION_STATE` injection with hash-based file tracking â€” not in opencode/codex (they just write files and let the model track its own session state via the summary).
- Overlapping systems: running_summary + summarizer + compaction_service + context tiers. Redundant.

**Missing:**
- A clean **ContextFragment** abstraction with provenance tags (codex's pattern).
- A single compaction trigger and a single summary template (codex `SUMMARY_TEMPLATE`).

### Static/simulation code to remove
- `_E2E_INSTRUMENT` / `_instrument()`.

## What we will do

- Adopt a ContextFragment abstraction: each injected block is a tagged fragment with an explicit role and markers.
- Fixed fragment slots: environment, system prompt, repo map, skills, instruction, compaction summary, history.
- Rolling-window history with a clear keep-token budget (no scoring heuristics).
- Single compaction service with a fixed summary template and clear thresholds.
- Remove the running-summary scheduler and the tier/scoring machinery.

## What we will REMOVE
- 5-tier scoring (`score_entry`, `STALE_TOKEN_MULTIPLIER`, orphan-dropping)
- `MODE_BUDGET_PROFILES` per-mode fractions
- `SESSION_STATE_*` injection
- `running_summary.py`, redundant `summarizer.py`
- `_E2E_INSTRUMENT` / `_instrument()`

## Regex audit
| Regex | opencode/codex uses it? | Action |
|---|---|---|
| `SESSION_STATE_HASH_PREFIX_LEN` / markers | No | Remove with SESSION_STATE |
| `*MARKER*` literal tags | codex uses marker tags | Adopt codex marker scheme |

## Verification / signoff
- [x] ContextFragment model with provenance markers (additive, codex style)
- [~] Fixed slots, no scoring heuristics — Phase 3 (5-tier scorer still live)
- [~] Single compaction service + fixed summary template — Phase 3 (see module note)
- [~] No running-summary scheduler, no SESSION_STATE — Phase 3
- [x] ruff + pytest pass (additive change)

## Status: Interface-Locked (Phase 1 additive); tier/scoring/SESSION_STATE/running-summary removals pending Phase 3

### Decision (2026-08-31) — phased execution (Mars, module 06 owner)

Per `progress.md` §11, Phase 1 is **additive interface-lock only; no removal yet**. Today the 5-tier
scored context (`TIER_T*`, `score_entry`, `STALE_TOKEN_MULTIPLIER`, orphan-dropping), `MODE_BUDGET_PROFILES`,
`SESSION_STATE_*` injection, and the running-summary/summarizer/compaction_service stack are all still
live and consumed by the loop/processor. So module 06 has:
- **ADDED (interface-lock) in `server/agents/context.py`:**
  - `ContentKind` enum (text/tool_output/summary/markdown/repo_map/system), `RenderedFragment` (body +
    content_kind), `ContextFragment` (codex `ContextualUserFragment { role, markers, body, content_kind }`
    with `render()` wrapping the body in its markers), and `tagged_fragment(role, body, kind)` producing the
    codex `<role>...</role>` marker scheme.
  - Complement to module-15 `PromptSection` (tagged prompt sections); ContextFragment is the codex-style
    provenance-tagged counterpart for all injected context slots (env/system_prompt/repo_map/skills/
    instructions/summary/history).
- **NOT removed yet (Phase 3, coordinated):** tier scoring, `MODE_BUDGET_PROFILES`,
  `SESSION_STATE_*` injection, `running_summary.py`/`summarizer.py`, `_E2E_INSTRUMENT`/`_instrument()`.
  `build_messages` is re-wired onto fixed fragment slots only once module 01 loop and compaction adopt
  the new shape. Do NOT delete during Phase 1.

---

## Module report (§9 template)

```
Module: 06 context
Status change: Pending → Interface-Locked (Phase 1 additive)
WHAT: Added ContextFragment (codex ContextualUserFragment) + RenderedFragment + ContentKind +
      tagged_fragment() in server/agents/context.py.
WHY: codex injects every block as an explicit, provenance-tagged fragment (context-fragments/src/fragment.rs);
      zenith's 5-tier scored context is bespoke/non-standard. Provides the tagged-slot contract build_messages
      will be re-wired onto in Phase 3.
FILES: server/agents/context.py, server/tests/test_context_fragment.py (NEW),
      agent_engine_redesign/context/feature.md
KEPT/REMOVED: additive ContextFragment added; 5-tier scoring, MODE_BUDGET_PROFILES, SESSION_STATE_*,
      running_summary/summarizer, _E2E_INSTRUMENT kept for Phase 3.
EXPECTED BEHAVIOUR: context blocks now expressible as explicit provenance-tagged fragments; existing
      scored build_messages path unchanged.
OUTCOME / TEST EVIDENCE: G1 PASS (6 new tests); G2 targeted-PASS (fragment tests + import smoke green);
      G3 ruff clean; G4 interface declared in feature doc; G5 no transport/event change; G6 additive only;
      G7 no CCS/shared file touched (context.py is module-06 owned); G8 self-contained.
SHARED-FILE IMPACT: none.
DEPENDENCIES: complements module-15 PromptSection; provides fragment-slot contract to 01 loop + 22 compaction;
      Phase 3 removes tier/scoring/SESSION_STATE/running-summary under coordination.
```

Next: Phase 2 wires build_messages onto fixed fragment slots; Phase 3 removes the tier/scoring machinery,
SESSION_STATE, and running-summary under coordination.
