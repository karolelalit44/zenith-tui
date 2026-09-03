# Prompts / System Prompt Assembly

## Overview

How the system prompt / base instructions are authored, selected, and combined into the model's system context.

### How opencode does it

- System prompt assembled in `session/prompt.ts` (~line 1255): concatenates **skills list**, **environment**, **instructions (AGENTS.md)**, **MCP notes**, plus **model messages**.
- Provider-specific system **text templates** selected at runtime via `session/system.ts` from `./prompt/*.txt` (anthropic, default, gpt, gemini, codex, etc.).
- Prompt bodies live in **editable `.txt` template files**, not code â€” data, not source. Model/agent-specific phrasing branches at the `system.ts` layer.
- User content assembled from resolved parts (text/file/agent/MCP) by `prompt.ts`.

### How codex does it

- No single `SYSTEM_PROMPT` constant. System context is assembled from many small **world-state sections** (`context/world_state/mod.rs`): a typed `WorldStateSection` trait with stable IDs and snapshots; each section (environment, permissions, tools, personality, multi_agent, context_window_guidance, ...) renders only its **diff vs the prior state** (`render_diff`, RFC 7386 patch), minimizing injected tokens.
- Base/developer instructions come from `agents_md.rs`, `exec_env`, and per-section fragments.

### What zenith has today

- `server/agents/prompts.py` (332): build/plan mode instruction blocks as Python string constants (e.g. `BUILD_MODE_INSTRUCTIONS`), importing mode/tier enhancements from `provider_adapters` (`detect_model_tier`, `get_tier_prompt_enhancements`) and `is_gemini_3_plus`.
- System context built by `context.py` tiers (already covered in `context/feature.md`).

### What is correct

- Mode/tier branching to tailor instructions per model (conceptually aligns with opencode's provider templates and codex per-model instructions).
- Concise, opinionated instruction style.

### What is wrong / over-engineered / incorrect / missing

**Over-engineered / incorrect:**
- Prompt bodies are **hardcoded Python string constants** (`prompts.py`). opencode keeps them as `.txt` template files; codex as data-view sections. Embedded strings are not independently editable/versionable by the user.
- Mode/tier **enhancement injection** (`provider_adapters.get_tier_prompt_enhancements`) mutates the prompt at runtime by model tier â€” a bespoke mechanism, separate from a clean section model.
- Conflates a lot of policy/instruction into one dense blob rather than composing independent, tagged sections.
- No diff/patch mechanism: re-injects full instruction blocks every turn (wasteful) â€” codex only emits changed sections.

**Missing:**
- Editable prompt template files.
- Tagged, composable, independently-versionable sections.

## What we will do

- Move prompt bodies out of Python into **template files** (opencode `.txt` style) selected at runtime by provider/model.
- Compose the system context from independent, tagged sections (aligns with codex world_state + the ContextFragment model from `context/feature.md`).
- Emit only changed/new sections where token economy matters (coarse version of codex's render_diff).
- Remove the `provider_adapters` runtime tier-enhancement injection.

## What we will REMOVE
- Hardcoded instruction blob in `prompts.py` (move to templates)
- `provider_adapters.get_tier_prompt_enhancements` / `detect_model_tier` prompt mutation
- `is_gemini_3_plus` conditional injections

## Regex audit
| Regex | opencode/codex uses it? | Action |
|---|---|---|
| `is_gemini_3_plus` / model-name string detection in prompt assembly | No (provider templates) | Remove |
| (none other specific) | â€” | â€” |

## Verification / signoff
- [x] Prompt bodies in template files (additive: `server/prompts/templates/build.md`, `plan.md`)
- [x] Tagged composable prompt sections (additive `PromptSection` + `compose_system_context`)
- [~] Provider/model-specific template selection — interface-locked stub; per-provider branch is Phase 2
- [~] No runtime tier-enhancement injection — Phase 3 (kept today; consumers must adopt first)
- [~] No grammar/diff emission — diff/render_diff is Phase 2 (token economy)
- [x] ruff + pytest pass (additive change)

## Status: Interface-Locked (Phase 1 additive); hardcoded-constant & tier-injection removal pending Phase 3

### Decision (2026-09-01) - Phase 2 validation (Mars)

`SimpleLoop` already uses `default_template_sections()` and `compose_system_context()` for
the live system prompt. The referenced `plan.md` template was missing from the workspace;
it is now restored with the existing `PLAN_MODE_INSTRUCTIONS` content. Docker validation of
template and prompt-loop wiring passes: 44 tests.

### Decision (2026-08-31) — phased execution (Mars, module 15 owner)

Per `progress.md` §11, Phase 1 is **additive interface-lock only; no removal yet**. Today
`build_system_prompt` still uses the hardcoded `BUILD_MODE_INSTRUCTIONS`/`PLAN_MODE_INSTRUCTIONS`
constants and `provider_adapters.get_tier_prompt_enhancements`/`is_gemini_3_plus` injection,
all still live-imported/consumed. So module 15 has:
- **ADDED (interface-lock) in `server/agents/prompts.py`:**
  - Editable template files `server/prompts/templates/build.md` + `plan.md` (opencode `.txt` style)
    with `load_prompt_template(mode)` reading them by mode at runtime.
  - `PromptSection` (tagged, composable; lazy callable content; `is_empty`) + `compose_system_context()`
    composing independent tagged sections (aligns codex world-state / ContextFragment).
  - `default_template_sections()` — the "clean" tagged composition (instructions/env/tool_reference/skills)
    that Phase 3 adopts once constants + tier injection are removed.
- **NOT removed yet (Phase 3, coordinated):** hardcoded instruction constants, the
  `provider_adapters.get_tier_prompt_enhancements`/`detect_model_tier` prompt mutation, and
  `is_gemini_3_plus` conditional injections. These are removed only after 01/02 prompt_sending
  and context consumers switch to the tagged/template surface. Do NOT delete during Phase 1.

### Step-2 adoption (Jupiter, module 01) — 2026-08-31

The new `SimpleLoop` (`server/agents/simple_loop.py`, module 01) no longer calls the legacy
`build_system_prompt`; it composes the runtime system prompt directly from the module-15
additive surface `default_template_sections(...)` + `compose_system_context(...)`, joined into a
single system string for `ContextManager.build_messages`. This removes the loop's dependency on
`BUILD_MODE_INSTRUCTIONS`/`PLAN_MODE_INSTRUCTIONS`, `provider_adapters.get_tier_prompt_enhancements`,
`detect_model_tier`, and `is_gemini_3_plus` tier-injection — the module 15/13 hardcoded-constant and
tier-injection removal path (Mars, Phase 3) is now unblocked for the 01-loop consumer. The legacy
`build_system_prompt` remains for `AgentLoop` (module 04, Mars removal target) and prompt_path.md.
Verified: ruff clean, no circular import, 45 loop/executor/prompt tests green.

---

## Module report (§9 template)

```
Module: 15 prompts
Status change: Pending → Interface-Locked (Phase 1 additive)
WHAT: Added editable mode templates (server/prompts/templates/build.md, plan.md) + load_prompt_template,
      PromptSection (tagged/composable/lazy), compose_system_context, default_template_sections in
      server/agents/prompts.py.
WHY: opencode keeps prompt bodies in editable .txt templates (session/system.ts + ./prompt/*.txt);
      codex renders per-section world-state; zenith's hardcoded constants + tier injection are not
      editable/independently versionable.
FILES: server/agents/prompts.py, server/prompts/templates/build.md (NEW), plan.md (NEW),
      server/tests/test_prompts_template.py (NEW), agent_engine_redesign/prompts/feature.md
KEPT/REMOVED: additive template+section surface added; hardcoded constants + get_tier_prompt_enhancements
      + is_gemini_3_plus kept for Phase 3 (consumers 01/02 + context must adopt tagged surface first).
EXPECTED BEHAVIOUR: prompt bodies now also available as editable template files + composable tagged
      sections; legacy build_system_prompt path unchanged (verified len 5154 smoke).
OUTCOME / TEST EVIDENCE: G1 PASS (9 new tests); G2 targeted-PASS (prompts tests green; runtime smoke
      of build_system_prompt + default_template_sections OK); G3 ruff clean; G4 interface declared in
      feature doc; G5 no transport/event change; G6 additive only; G7 no CCS file touched (prompts.py is
      module-15 owned; provider_adapters.py is module-13 owned and left untouched); G8 self-contained.
SHARED-FILE IMPACT: none (provider_adapters.py / constants.py untouched).
DEPENDENCIES: provides tagged-template contract to 01/02 prompt_sending and 06 context; Phase 2 adds
      provider/model template selection + render_diff; Phase 3 removes constants + tier injection.
```

Next: Phase 2 wires providers/context onto template sections; Phase 3 removes hardcoded constants +
tier-enhancement injection under coordination with 01/02/06.
