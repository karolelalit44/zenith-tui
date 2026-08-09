# 02 — Rate-limiting / quota handling: the blocker

> Area: `server/providers/llm_provider.py`, `server/agents/llm_stream.py`, `server/providers/retry.py`
> Severity: **Critical** — free-tier users (e.g. Google AI Studio, 15 req/min) currently get killed mid-task with `RATE_LIMIT` / "Execution halted".

---

## 1. Summary

The code does not read the provider's own retry guidance and does not pace its own API calls, so on rate-limited/free-tier providers it retries **too fast and too often**, exhausts the quota, and then dies with a raw 429 error and no path to resume. In the observed run, Google returned `"Please retry in 9.788501089s"` but the agent retried after **2 seconds**, got another 429, and after 2 attempts emitted `recoverable=False` → `[FAILED] ... Code: RATE_LIMIT` → `Execution halted`.

## 2. What is currently happening (evidence)

```
2026-08-09 11:48:50,508 [WARNING] server.agents.llm_stream: Stream retry 1 after rate limit (2.0s): Rate limited by provider 'google': ...
   (server said: Please retry in 9.788501089s)
2026-08-09 11:48:52,834 [INFO] server.agents.prompt_executor:  ERROR: message=Rate limited by provider 'google': litellm.RateLimitError: vertex_ai_betaException - b'{...Quota exceeded for metric:
   generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 15...}' code=RATE_LIMIT recoverable=False
```

The whole agent loop kept calling the API ~18 times in under 2 minutes against a **15 requests/minute** free-tier limit, guaranteeing the 429.

## 3. Root causes (code-level)

### 3.1 `_extract_retry_after` only reads the HTTP header — Google puts the value in the JSON body
`llm_provider.py:78-91`:

```python
def _extract_retry_after(exc):
    resp = getattr(exc, "response", None)
    headers = getattr(resp, "headers", None)
    ra = headers.get("retry-after")      # ← only header
    ...
```

Google's error body contains `"details": [{ "@type": "...RetryInfo", "retryDelay": "9.7s" }]` — never parsed. So `retry_after` stays `None`, and `llm_stream.py:93` falls back to `min(2**attempt, 10)` = **2 s**, ignoring the server's "9 s" instruction. Retrying at 2 s while the server says 9 s guarantees another 429.

### 3.2 Quota exhaustion is misclassified as a transient 429
`llm_provider.py:98-108`:

```python
is_quota_exhausted = any(q in msg for q in (
    "free-models-per-day", "insufficient_quota", "credit_balance",
    "payment_required", "quota_exceeded",      # underscore, never appears
    "add 10 credits",
))
```

The real message is `"Quota exceeded for metric: .../generate_content_free_tier_requests"` (a **space**, not an underscore) with `"status": "RESOURCE_EXHAUSTED"`. None of the keywords match, so the error is treated as transient (`recoverable=True`) and retried — wrongly.

### 3.3 The 2-retry budget resets every iteration (no global guard)
`llm_stream.py:89-103`:

```python
except RateLimitError as e:
    if time.monotonic() >= deadline or not e.recoverable or attempt >= 2:
        yield r.error(str(e), ..., recoverable=False)
        return
```

- `attempt` is local to one `stream_with_retries` call.
- `loop.py` calls `stream_with_retries` **once per iteration**, so each iteration gets a fresh `attempt=1,2` budget.
- There is no session/turn-level circuit breaker and **no client-side throttle** — nothing stops the loop from issuing ~18 API calls against a 15/min quota.

### 3.4 Additional retry layers are inconsistent
- `llm_provider._build_completion_kwargs` passes `"num_retries": 1` to litellm (`llm_provider.py:382`).
- `complete()` wraps calls in `retry_with_backoff` (`llm_provider.py:410`, `retry.py`) which *does* respect `retry_after` — but only for non-streaming completion; the streaming path in `stream_with_retries` does not.
- `RETRY_TIMEOUT = 60.0` (`llm_stream.py:15`) bounds a single stream, not the whole turn.

### 3.5 Raw error blobs reach the user
Because `_extract_clean_message` fails on the `b'...'`-wrapped JSON (see `03-error-message-to-ui.md`), the full 429 JSON (with quota metrics, links, retry info) is dumped into the UI as the error text, and `recoverable=False` prints "Execution halted".

## 4. Impact

- Mid-task hard failure on the most common provider setup (free tier).
- ~18 wasted API calls that all 429 → quota burns *faster* because we hammer.
- Confusing, hostile error UX (giant JSON, no guidance, no resume).
- On shared/trial keys, the user can get temporarily banned for bursty retrying.

## 5. What the correct behaviour should be

### 5.1 Read the provider's retry delay
- Parse `retryDelay` from the error JSON body (`RetryInfo.retryDelay`, formats `"9.7s"`/`"9.788501089s"`), fall back to the `retry-after` header, then to exponential backoff.
- In `stream_with_retries`, wait **max(server_delay, 0) capped by remaining deadline** and use a minimum delay of a few seconds for 429s.

### 5.2 Classify quota correctly
- Add `"quota exceeded"`, `"quota_exceeded"`, `"free_tier_requests"`, `"RESOURCE_EXHAUSTED"`, `"generate_content_free_tier"`, `"rate_limit"` + `"quota"` to `is_quota_exhausted`.
- For per-minute quota (retryable soon) keep `recoverable=True` but enforce a **server-advised cooldown**; for daily/billing quotas (`free-models-per-day`, `insufficient_quota`, `payment_required`) mark `recoverable=False` with a clear message.

### 5.3 Add a client-side throttle (the real fix)
- Add a per-provider **minimum interval between stream starts** (from the catalog or env, e.g. `ZENITH_MIN_REQUEST_INTERVAL`). Google free tier = 15/min ⇒ ~4 s spacing (+ jitter). Enforce it in the loop so the turn physically cannot exceed the quota.
- Add a **turn-level circuit breaker**: after N consecutive provider errors in one turn (e.g. 3), pause with a user-facing message *"Rate limited — waiting 30s and continuing"* (emit a `thinking`/`warning` event) instead of failing.

### 5.4 Friendly, actionable errors
- When the turn finally cannot proceed, emit a clean message like:
  *"Rate limit reached (Google AI Studio free tier: 15 requests/min). Waiting ~9s and retrying…"* or, if exhausted, *"Free-tier daily quota reached for gemini-3.5-flash-lite. Switch model/provider or try again later."*
- Keep `recoverable=True` for per-minute limits and add a **Continue** affordance in the UI (see `05-integrity-and-ux.md`).

## 6. Happy flow (step by step)

1. Model asks for stream #12 of a long turn on free tier.
2. Google returns `429` with `"retryDelay": "7.2s"`.
3. `_extract_retry_after` (fixed) parses `7.2s` from the body.
4. `stream_with_retries` yields `thinking: "Rate limited — retrying in 8s…"` and sleeps ~8 s.
5. The throttle in the loop also spaces the next iteration so no more than ~14 requests land in the current minute.
6. The retry succeeds; the turn continues; the task completes.
7. If the quota is truly exhausted (daily), the turn ends with a **clean, recoverable** message and the UI offers "Continue later" instead of "Execution halted".

## 7. Fix checklist

- [ ] Parse `retryDelay` from the error JSON body in `_extract_retry_after` (handle `b'...'` prefix, `"Xs"` and bare-seconds formats).
- [ ] Expand `is_quota_exhausted` keywords (`quota exceeded`, `free_tier_requests`, `RESOURCE_EXHAUSTED`, `generate_content_free_tier`).
- [ ] Use `max(retry_after, min_delay)` in `stream_with_retries` for 429s; keep retry count but bound total wait by `RETRY_TIMEOUT`.
- [ ] Add per-provider minimum request interval + jitter enforced in `loop.py` (`ZENITH_MIN_REQUEST_INTERVAL` / catalog `rate_limit` field).
- [ ] Add a turn-level provider-error circuit breaker with a user-visible pause + resume.
- [ ] Surface clean, actionable rate-limit messages (see also `03-error-message-to-ui.md`).
- [ ] Regression tests: mocked provider returning 429 with `retryDelay` (body) → assert wait ≈ server value; 429 with `free_tier_requests` → assert correct `recoverable` and no hammering.
