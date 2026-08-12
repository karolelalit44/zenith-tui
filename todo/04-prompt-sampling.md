# 04 — Prompt & sampling settings: anti-loop instructions and Gemini 3+ sampling

> Area: `server/agents/prompts.py`, `server/providers/llm_provider.py` (kwargs/temperature), `server/agents/context.py`
> Severity: **Medium-High** — contributes directly to the observed repeat-call loop and produces deprecation warnings on Gemini 3+.

---

## 1. Summary

Two distinct problems. **(1)** The system prompt gives compact models no explicit rules against repeating tool calls, so a compact/cheap model (e.g. `gemini-3.5-flash-lite`) is free to re-emit `file_write` endlessly. **(2)** The completion kwargs always send `temperature: 0.7` (plus `top_p`/`top_k`) — Gemini 3+ models **deprecate** these sampling params and log a warning on every call, which polluted the log with hundreds of lines and may change model behaviour.

## 2. What is currently happening (evidence)

```
2026-08-09 11:41:37,343 [WARNING] ... litellm: Received 'temperature=0.7'. This is a deprecated field for gemini-3.5-flash-lite. ...
   (repeated ~3-5 times per stream start)
2026-08-09 11:41:37,343 [WARNING] ... Received 'top_p=0.9'. This is a deprecated field ...
2026-08-09 11:41:37,343 [WARNING] ... Received 'top_k=40'. This is a deprecated field ...
```

The prompt side (`prompts.py`, `compact_model_rules`) already includes rules like *"NEVER output chat preambles…"* but **contains no rule about not repeating tool calls or not rewriting the same file**. Meanwhile the loop observed the model re-emitting the exact same `file_write` 22–23 times per turn, with zero pushback from the system prompt.

## 3. Root causes (code-level)

### 3.1 Sampling params for Gemini 3+
`llm_provider.py:380-383`:

```python
if temperature is not None:
    kwargs["temperature"] = temperature   # default 0.7 (llm_provider.py:22)
    kwargs["top_p"] = 0.9
    kwargs["top_k"] = 40
```

The runtime catalog is SQL-backed (`catalog_models` table, seeded by migrations 004/006; `server/config/provider_catalog.json` was removed). Model sampling capabilities are declared per model in `model_capabilities_json`. The code always injects `temperature/top_p/top_k`, and models that deprecate them (e.g. Gemini 3+) reject/ignore them with a per-call deprecation warning. This is also wasted log bandwidth and can change sampled behaviour if the provider silently clamps values.

### 3.2 No anti-repetition / anti-clobber instructions
`prompts.py` `compact_model_rules` (`NEVER output chat preambles…`, `NEVER include tool invocation content in text…`) are all about *output formatting*. Nothing tells the model:
- do not call a tool twice with identical params in one turn;
- do not write the same path twice; use `file_edit` after `file_read` instead;
- if the task is done, write the final summary and emit no tool calls.

`tool_choice="auto"` (`llm_provider.py:384`) is fine, but combined with no constraints it leaves compact models free to loop (Gemini Flash-style models are known to re-emit tool calls under pressure).

### 3.3 Context/token guidance
`context.py` (`_adaptive_reserve`) already reserves budget, but nothing in the prompt tells the model to conserve tokens or that repeating work is penalized. The stall messages that *do* attempt this are too verbose and arrive too late (see `01-agent-loop-root-cause.md` §3.5).

## 4. Impact

- Log spam: hundreds of deprecation warnings per turn.
- Potential behaviour drift: sampling params may be silently dropped or clamped by Gemini 3+.
- The model loops because it was never told not to → wasted tokens + rate-limit death (the whole `01-`/`02-` cascade).

## 5. What the correct behaviour should be

### 5.1 Sampling
- Sampling params are driven by the **model's own catalog capabilities**, never by hardcoded model names/versions in code.
- A model whose `model_capabilities_json` declares `"supports_temperature": false` receives **no** `temperature` param; the provider then uses its defaults (no deprecation warnings).
- Otherwise send `temperature` (resolved from `default_temperature` or the request override) and only `top_p`/`top_k` when a catalog field sets them.
- Build the kwargs through a small generic helper (`_build_completion_kwargs`) with unit tests, instead of a single hardcoded block.

### 5.2 Anti-loop prompt rules (compact + full models)
Add to `compact_model_rules` (and a corresponding short rule for larger models):

```
- Never call a tool twice with identical parameters in one turn. If you must retry, change the parameters or explain why.
- Never write the same file path twice in one turn. To modify a file, call file_read first, then file_edit.
- When the task is complete, output ONLY your final summary text and stop — do not emit tool calls.
- A tool call that already succeeded this turn will be skipped. Treat skips as feedback to stop repeating.
```

These rules are cheap and directly address the observed loop. Keep them short so they don't bloat the context.

### 5.3 Consistent enforcement
- The prompt rules must match the *runtime* enforcement from `01-…` §5.1 (one-write-per-path guard). Prompt + enforcement together are what actually stops compact models.
- Keep stall guidance minimal: *"No new work happened. If the task is complete, write your final summary now and stop."* — never a wall of "tools still NOT used".

## 6. Happy flow (step by step)

1. Turn starts; kwargs are built with **no** sampling params for Gemini 3+ → zero deprecation warnings in the log.
2. The model is told up front: don't repeat calls, don't rewrite paths, end with a summary.
3. The model writes each file once, in order, then emits a final summary with no tool calls.
4. If it still drifts, the runtime guard (see `01-…`) finalizes gracefully within one extra iteration.

## 7. Fix checklist

- [ ] Build sampling kwargs from the model's declared capabilities (omit `temperature` when `supports_temperature: false`; send it otherwise).
- [ ] Add the 4 anti-loop rules to `compact_model_rules` (and a short variant for large models).
- [ ] Verify with a scripted run that no `deprecated field` warnings appear for `gemini-3.5-flash-lite`.
- [ ] Add a prompt unit test asserting the anti-repeat rules exist for both rule sets.
