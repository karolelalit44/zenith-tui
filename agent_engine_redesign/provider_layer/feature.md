# Provider Layer

## Overview

The provider layer is how zenith talks to LLM vendors: model resolution, API key/auth, streaming response parsing, token counting, retries/validation, and the provider-agnostic adapter surface.

### How opencode does it

- **Provider** is a thin per-vendor SDK wrapper: `createOpenAIProvider`, `createAnthropicProvider`, etc., each exposing a unified `streamModel`/`streamText` + `AbortController`. Model catalog comes from `models.dev` via a `provider.ts:catalog: Record<ProviderV2.ID, Info>`.
- **Model info** (context window, max output, tokenizers) is looked up from the catalog by provider+model id.
- Streaming: `processor.ts` consumes `provider.result.stream()` (an async generator) defensively; the SDK itself delivers token deltas; opencode maps them to `text-delta`/`reasoning-delta` Parts.
- No bespoke parser: the SDK returns typed chunks. Tool call parsing is done by the SDK/provider response, surfaced as parts.
- Auth: keys from config/`auth.json`, env, or credential helpers; no custom auth state machine.
- No per-provider retry/validation taxonomies beyond normal SDK error propagation.

### How codex does it

- `ModelProvider` trait (in `model-provider` crate): a unified interface over OpenAI/Anthropic/etc., streaming via `ModelTurnStream`. Capabilities via `ModelInfo`/`ModelCapabilities` (supports thinking, vision, reasoning_summary, etc.).
- Model catalog bundled JSON (`model_catalog_json`) + `ModelsResponse` for the API layer.
- Config-centric: `config/model.rs` carries `model_provider`, `model`, `temperature`, `reasoning_effort`, `context_window`, `max_output_tokens`, etc.
- Streaming events explicitly typed (`responses_retry.rs`, `ResponsesRetry` for retry-once logic).
- Effort/thinking passed through as model params, not harness-parsed.

### What zenith has today

**Files:**
- `server/providers/base.py` â€” abstract `BaseProvider`, `stream_completion`, `count_tokens`, abort.
- `server/providers/llm_provider.py` (901 lines) â€” the main OpenAI-compatible client: request building, streaming loop, tool-call assembly, thinking/reasoning extraction, `sampling_kwargs` tuning, error mapping.
- `server/providers/registry.py` â€” `ProviderRegistry.from_config` builds `LLMProvider`s from `ProviderConfig`, resolving model defaults (max_tokens, temperature) and thinking support from the catalog.
- `server/providers/parser.py` (384) â€” a bespoke streaming response parser: extracts `content`, `tool_calls`, `reasoning`, finishing_reason, including `sampling_kwargs` fields.
- `server/providers/token_counter.py` â€” `TokenCounter` using tiktoken with cl100k_base fallback + char-heuristic (`CHARS_PER_TOKEN`).
- `server/providers/validation.py` (489) â€” response validation/retry logic.
- `server/providers/responder.py` â€” event factories (already covered in markdown_render/transport).
- `server/agents/provider_adapters.py` (69) â€” `detect_model_tier`, `get_tier_prompt_enhancements`, `is_gemini_3_plus` tier enhancement branching.
- `server/api/provider_validation.py` (280) â€” a REST layer validating provider configs at the API boundary.
- `server/api/validation_state.py` â€” validation state machine.

**Constants (config/constants.py, provider domain):**
- `DEFAULT_CONTEXT_WINDOW`, `DEFAULT_LLM_TEMPERATURE`, `default_max_tokens_for_context`, `CHARS_PER_TOKEN`, `SUMMARY_FRAMING_TOKENS`, `MIN_OUTPUT_RESERVE_TOKENS`, `HARD_STOP_USAGE_RATIO`, `MAX_TOOL_OUTPUT_TIERS`, `MAX_TOOL_OUTPUT_BASELINE`, `SAMPLING_*` kwargs knobs, `STREAM_CONNECT_TIMEOUT_*`, `STREAM_READ_TIMEOUT_*`, provider-specific finishing-reason / error-code maps.

### What is correct

- tiktoken-based counting with heuristic fallback is reasonable (matches real tokenizers).
- Model capability resolution (thinking support) from the catalog is sound.
- Provider-agnostic `BaseProvider` interface is the right shape.

### What is wrong / over-engineered / incorrect / missing

**Over-engineered / incorrect:**
- A **bespoke streaming parser** (`parser.py`) reinventing what the SDK/provider already types. opencode/codex consume SDK chunks and map to Parts; they do not hand-parse tool-call/reasoning from raw text with regex/manual extraction.
- `sampling_kwargs` tuning (extra sampling parameters beyond temperature/max_tokens) â€” opencode/codex pass temperature/effort and stop; they do not expose a family of sampling knobs for the harness to tune.
- `providers/validation.py` (489 lines) retry/validation taxonomy â€” over-engineered vs opencode/codex (minimal retry; codex has a simple `ResponsesRetry`).
- `api/provider_validation.py` / `validation_state.py` â€” a separate REST validation layer + state machine not in the reference; validation is typically a config-load concern, not a per-endpoint stateful subsystem.
- `provider_adapters.py` model-tier enhancement branching (`detect_model_tier` -> `get_tier_prompt_enhancements`) â€” injects model-specific prose into the prompt at runtime; opencode achieves model-specific behavior via provider templates/params, not ad-hoc prompt injections. Over-engineered.

**Missing:**
- A real `ModelCapabilities` set (vision, reasoning_summary, thinking) exposed uniformly (codex `ModelInfo`); zenith only resolves "thinking" bool.
- `reasoning_effort` as a proper config knob (zenith has `reasoning_budget` scattered; not unified).

### Static/simulation code to remove
- Any hardcoded finishing-reason / error-code maps used to simulate success.
- `HARD_STOP_USAGE_RATIO`-driven synthetic stop behavior if it fakes provider signals.

## What we will do

- Keep a unified `BaseProvider`/`LLMProvider` but slim it: consume SDK/provider-streamed deltas and map them to Parts (text/reasoning/tool_call) â€” drop the bespoke `parser.py` hand-parse.
- Pass `temperature` + `reasoning_effort` as model params; remove `sampling_kwargs` knob-family tuning.
- Resolve model capabilities from the catalog (context window, max output, thinking, vision).
- Keep tiktoken counting + heuristic fallback.
- Move provider validation into config-load time; remove the separate API validation layer/state machine.
- Remove `provider_adapters.py` tier-prompt injection.

### Decision (2026-08-31) — phased execution & cross-module coordination

Per `progress.md` §11, this project runs additively in **Phase 1 (interface-lock,
no removal)**; the REMOVE list below is executed in **Phase 3**, coordinated so
consumers migrate first. Mars (owner of module 13) has therefore:

- **ADDED (Phase 1, interface-lock):**
  - `ModelCapabilities` (pydantic model) + `model_capabilities_from_catalog()` in
    `server/providers/base.py` — a unified capability set (thinking, vision,
    functions, reasoning_summary, supports_temperature) mirroring codex
    `ModelInfo`/opencode catalog. Downstream modules (06 context, 08
    thinking_reasoning, 09 markdown_render) may code against this contract.
  - `reasoning_effort` as a first-class, optional param on `LLMProvider` and
    threaded into `_build_completion_kwargs` (defaults `None` → zero behaviour
    change; `drop_params` protects providers that ignore it). `ProviderRegistry
    .from_config` passes it through defensively (`getattr`).
  - `LLMProvider.capabilities` exposes the resolved `ModelCapabilities`.
- **NOT removed yet (Phase 3):** `parser.py`, `sampling_kwargs` family,
  `validation.py` taxonomy, `api/provider_validation.py`, `api/validation_state.py`,
  `provider_adapters.py` tier-injection. These are live-imported today (loop.py,
  prompts.py, api/server.py) and must be removed only after their consumers are
  migrated — do NOT delete during Phase 1.
- **Coordination note (module 14 config_management):** unifying `reasoning_effort`
  as a typed setting belongs on `ProviderConfig` (config/providers.py), which is
  owned by Jupiter/module 14. `from_config` already reads it via `getattr`, so once
  module 14 adds the field it is picked up with no further module-13 change.


## What we will REMOVE
- `providers/parser.py` bespoke parsing (replaced by Part mapping)
- `sampling_kwargs` tuning family
- 489-line `providers/validation.py` taxonomy (fold minimal retry)
- `api/provider_validation.py`, `api/validation_state.py` (fold into config validation)
- `provider_adapters.py` (`detect_model_tier`/`get_tier_prompt_enhancements`/`is_gemini_3_plus`)
- Excess `SAMPLING_*`, `STREAM_*_TIMEOUT_*`, provider `HARD_STOP_USAGE_RATIO` constants

## Regex audit
| Regex | opencode/codex uses it? | Action |
|---|---|---|
| provider_adapters `is_gemini_3_plus` checks | No (model-specific meta via config/templates) | Remove |
| error-code / finishing-reason string maps | No | Remove |

## Verification / signoff
- [x] Unified provider interface contract documented & interface-locked (ModelCapabilities, reasoning_effort, model_capabilities_from_catalog)
- [x] Model capabilities resolved from catalog (additive; `LLMProvider.capabilities`, `model_capabilities_from_catalog`)
- [x] temperature + reasoning_effort as params; sampling_kwargs removal deferred to Phase 3 (decision note)
- [x] tiktoken + heuristic counting kept (unchanged)
- [ ] Validation folded into config load; API validation layer/state machine removed (Phase 3)
- [ ] provider_adapters tier-injection removed (Phase 3)
- [x] ruff + pytest (module tests) pass for additive Phase-1 changes

## Status: Interface-Locked (Phase 1 additive); removal pending Phase 3

---

## Module report (§9 template)

```
Module: 13 provider_layer
Status change: Pending → Interface-Locked (Phase 1 additive)
WHAT: Added a unified ModelCapabilities contract + model_capabilities_from_catalog()
      resolver in providers/base.py; added reasoning_effort as an optional, defensive
      config knob on LLMProvider (threaded into _build_completion_kwargs) and
      ProviderRegistry.from_config; exposed LLMProvider.capabilities.
WHY: Matches codex ModelInfo / opencode provider catalog capabilities (thinking, vision,
      functions, reasoning_summary) and passes temperature + reasoning_effort as plain
      model params — see ref_repo/opencode packages/opencode/src/tool and codex
      config/model.rs intent. Additive only, per progress.md §11 Phase 1 (no removal).
FILES: server/providers/base.py, server/providers/registry.py,
      server/providers/llm_provider.py, server/tests/test_providers.py,
      agent_engine_redesign/provider_layer/feature.md
KEPT/REMOVED: strengthened capability resolution + reasoning_effort; NO removals yet —
      parser.py / sampling_kwargs / validation.py / api/provider_validation.py /
      validation_state.py / provider_adapters.py tier-injection are deferred to Phase 3
      (they are live-imported by loop.py, prompts.py, api/server.py today).
EXPECTED BEHAVIOUR: model capabilities now resolvable uniformly per model; reasoning_effort
      pass-through is a no-op unless configured (defaults None); no runtime change when unset.
OUTCOME / TEST EVIDENCE: G1 PASS (ModelCapabilities/from_catalog/reasoning_effort tests added);
      G2 targeted-PASS (141 provider+loop tests + 103 companion + test_providers 21 all green;
      full `python -m pytest server/tests/` not run to completion — very slow/possibly
      network-bound); G3 ruff clean; G5 no transport/event change (TUI unaffected).
SHARED-FILE IMPACT: none — no CCS edits, no constants.py change, no locks taken; all edits
      within module-13 owned files except appending to an existing test file.
DEPENDENCIES: interface-locks 06 context / 08 thinking_reasoning / 09 markdown_render /
      15 prompts (may code against ModelCapabilities). config-level reasoning_effort
      unification coordinated with module 14 (Jupiter) via getattr passthrough.
```

Next: Phase 2 wires the new interface into consumers; Phase 3 performs the REMOVE list
above under coordination. Needs module 01/02/07 interface-lock eventually for full Done.
