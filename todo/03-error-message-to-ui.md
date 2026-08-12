# 03 — Error message → UI: raw blobs instead of clean, actionable errors

> Area: `server/providers/llm_provider.py` (message extraction), `server/providers/responder.py` (error events), `tui/src/components/Display/Scenario/ErrorBlock.tsx`
> Severity: **High** — every provider error currently reaches the user as raw, unparsed JSON (often `b'...'`-wrapped), with no guidance and no retry affordance.

---

## 1. Summary

The pipeline that turns a provider exception into what the user sees is broken at three layers: the backend fails to extract a clean message, the backend error event omits `provider`/`recoverable`-based UI decisions, and the frontend renders whatever raw text it gets without truncation or affordances. The result, as observed: a `[FAILED]` panel showing a multi-KB Google 429 JSON dump ending in `Execution halted`.

## 2. What is currently happening (evidence)

Frontend log (rendered `[FAILED]` panel):

```
[FAILED]
... | Error: Rate limited by provider 'google': litellm.RateLimitError: vertex_ai_betaException - b'{...
   "status": "RESOURCE_EXHAUSTED", "message": "429 Quota exceeded for metric
   generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 15...
   "retryDelay": "9.788501089s" ...
   Please retry in 9.788501089s...}'
Execution halted
```

The user cannot tell from this whether they're banned, throttled for 10 seconds, or need to buy credits.

### Backend evidence
- `_extract_clean_message` (`llm_provider.py:51`) tries `json.loads(exc.message)` — but the message is often `b'{...}'` (a bytes-wrapped string), so `json.loads` throws and it falls back to returning the raw message.
- `responder.error()` (`responder.py`) builds an event with `code` and `recoverable`, but **no `provider` field**, and the message is the raw exception text.
- `recoverable=False` → the frontend treats it as terminal ("Execution halted"), even when the cause is a *per-minute* quota that is retryable seconds later (misclassified — see `02-rate-limiting-quota-handling.md`).

### Frontend evidence
- `tui/src/components/Display/Scenario/ErrorBlock.tsx:10` declares `_MAX_MESSAGE_LENGTH = 200` — **declared but never used**, so messages are rendered in full (the raw JSON dump above).
- The badge logic (`recoverable ? '[ERROR]' : '[FAILED]'`) is fine, but the type's `provider` field is never set by the backend, so the "provider" line shows nothing (ErrorBlock reads `event.provider`).
- There is no Retry / Continue / Switch-model affordance in the error panel.

## 3. Root causes (code-level)

1. **`_extract_clean_message` can't parse `b'...'` JSON** — add a strip of the `b'...'` wrapper (and `\n` escapes) before `json.loads`, then pull `error.message` / `error.status`.
2. **`responder.error()` omits `provider`** — the `ErrorEvent` type on the frontend expects it; the backend simply doesn't fill it.
3. **ErrorBlock ignores its own truncation constant** — `_MAX_MESSAGE_LENGTH` unused; no expand/collapse.
4. **No mapping of `code` → friendly copy** — a `RATE_LIMIT` code with `recoverable=True` should render "Paused for rate limit — retrying" copy, not a raw dump.

## 4. Impact

- Users see byte-string JSON dumps and can't act on them.
- "Execution halted" is a dead end with no recovery path, even for transient causes.
- Diagnostic information that *would* help (provider, quota metric, retry delay, the *clean* server message) is buried inside the blob.

## 5. What the correct behaviour should be

### 5.1 Clean extraction on the backend
- Normalise: strip `b'`/`'` byte-string wrapper and un-escape before `json.loads`.
- Prefer the parsed `error.message`; fall back to the outermost exception line only.
- For rate-limit errors, enrich the message with the parsed retry delay: *"Google AI Studio rate limit: 15 req/min. Retrying in ~9.8s."*

### 5.2 Structured error events
- `responder.error()` should always include `provider` and a stable `code`.
- Add optional `action`/`hint` fields (e.g. `action: "retry"`, `hint: "Switch to a paid key or wait a minute"`) so the UI can render affordances without special-casing strings.

### 5.3 Frontend rendering
- **Truncate**: render up to `_MAX_MESSAGE_LENGTH` chars, then an expandable `… (show full details)` toggle (implement the already-declared constant!).
- Show `provider` when present.
- Map `code`/`action` to buttons: `Retry` (re-run the last turn), `Continue` (resume after quota pause), `Change model`.
- Show "Execution halted" only for `recoverable=False` and *billing/daily-quota* causes — never for transient 429s.

## 6. Happy flow (step by step)

1. Provider raises a 429 with `retryDelay: "9.7s"`.
2. Backend extracts the clean message + delay; `responder.error` emits `{type:"error", code:"RATE_LIMIT", recoverable:true, provider:"google", message:"Rate limited (15 req/min free tier). Retrying in ~10s…", action:"retry"}`.
3. The loop pauses and retries (see `02-…`); the UI shows a **warning/status** ("Paused — rate limit"), not a failure.
4. If it truly fails, the error panel shows a 200-char message with a "details" toggle, the provider line, and a `Retry` button.
5. For daily-quota exhaustion (`recoverable=False`), the panel says *"Daily free-tier quota reached. Switch model or try again tomorrow."* with a `Change model` button — no byte-string dumps.

## 7. Fix checklist

- [ ] Fix `_extract_clean_message` to handle `b'...'`-wrapped JSON and prefer `error.message`.
- [ ] Add `provider` (+ optional `action`/`hint`) to error events in `responder.py`.
- [ ] Wire the correct `recoverable` classification (see `02-…`) so transient 429s never reach `FAILED`.
- [ ] Use `_MAX_MESSAGE_LENGTH` with an expand/collapse toggle in `ErrorBlock.tsx`; remove the unused warning.
- [ ] Render `provider` line when present.
- [ ] Add `Retry` / `Continue` / `Change model` affordances driven by `action`/`code`.
- [ ] Regression test: inject a 429 with a `b'{...}'` body → assert the emitted event has a clean message and `recoverable=true`.
