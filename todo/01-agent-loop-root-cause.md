# 01 — Agent Loop: the root cause of wasted tokens and failed tasks

> Area: `server/agents/loop.py` (+ `server/agents/loop_detection.py`, `server/agents/prompts.py`)
> Severity: **Critical** — this is what turned a simple "build a FastAPI app" request into a 93k-token burn with a failed, half-written project.

---

## 1. Summary

When the model re-emits the same tool call (or the same batch of tool calls) over and over, the agent does **not** stop fast enough. It keeps spending a full LLM round-trip per iteration, each round-trip re-sending a growing context, until either the token budget is exhausted or the provider rate-limits us out. In the observed run the model re-issued `file_write(path=library-mgmnt-sys/requirements.txt)` **22–23 times per turn** for multiple turns, producing ~18 iterations, **93,095 prompt tokens (72.7% of the 128k budget)**, a torrent of "skipped calls" warnings, and finally a hard `RATE_LIMIT` failure with the task left ~10% done.

## 2. What is currently happening (evidence)

From the backend log:

```
Agent turn 17 response: 0 chars, 22 tool calls, clean=0 chars finish=stop
All requested calls already executed this turn; falling through ...
Agent turn 18 response: 0 chars, 23 tool calls, clean=0 chars finish=stop
No new tool work for several consecutive iterations; finalizing the turn.
SUCCESS: iterations=18 token_info={'used': 93095, 'remaining': 34905, 'total': 128000, 'percent': 0.727, ...}
```

From the frontend log, the same `file_write` path was written **10 times** with *different* content (233 → 207 → 188 → 183 → 177 → 83 → 100 → 161 → 93 → 177 bytes), each write followed by:

```
▲ [WARNING] Skipped calls already completed with identical params this turn:
   file_write(path=library-mgmnt-sys/requirements.txt), file_write(path=library-mgmnt-sys/requirements.txt), ...
▲ [WARNING] [System] No new tool was executed this iteration; every call you emitted was already attempted earlier ...
```

Then, after the loop finally "finalized", the very next stream call died:

```
STREAM ERROR ... error=litellm.MidStreamFallbackError: ... 429 quota exceeded ...
ERROR: message=Rate limited by provider 'google' ... code=RATE_LIMIT recoverable=False
```

### The two distinct failure modes we observed

1. **Pure re-emission of an identical call.** The model calls `file_write(path=..., content=A)` that already succeeded this turn. Dedup correctly skips it (see §3.1), but the model *keeps emitting it anyway*, every iteration.
2. **Re-writing the same path with new content.** The model writes `requirements.txt` with content A, then content B, C, D… (bytes differ each time, so dedup correctly lets each one run). The file ends up being clobbered ~10 times and its final content is whatever the last write happened to be.

Both behaviours are the same underlying bug: **the agent loop does not detect "the model is stuck on one file/path/tool" and stop with a graceful summary.**

## 3. Root causes (code-level)

### 3.1 Dedup is correct — the problem is the *fall-through* behaviour
`loop.py:54` builds a signature that *includes the full params* (including `content`), so two calls with different content are correctly treated as different calls:

```python
def _call_signature(tool_name: str, params: dict) -> tuple[str, str]:
    return (tool_name, json.dumps(params, sort_keys=True, ...))
```

When every requested call is already executed (`_all_calls_repeat`, `loop.py:83`), `loop.py:526` just **falls through** and lets the per-call loop skip them so the "stall handler can guide the model". Guidance comes only as a giant system/user message. Nothing *stops* the turn here.

### 3.2 The stall handler is too slow (2 full iterations of nothing)
`loop.py:747-784`:
- On the **1st** consecutive stall it injects a huge "[System] You are stuck repeating previous work… Tools still NOT used: agent, bash, file_delete, …" message.
- Only on the **2nd** consecutive stall does it set `task_completed = True` and break.

So the minimum cost of a stuck model is **two full LLM round-trips of pure noise**, each one resending the whole (growing) context. In this run it took *many* more because the model alternated between "new content write" (counts as progress, resets `stall_count` at `loop.py:785-786`) and "identical re-emission" — never hitting two *consecutive* stalls until late.

### 3.3 Re-writing the same path resets the stall counter
`loop.py:785`: `elif newly_executed: stall_count = 0`. A different-content write to the *same* path counts as "new work", so the loop never sees the model is path-stuck. There is no "same path, N writes" detector anywhere.

### 3.4 LoopDetector is configured too loosely (or never triggers)
`LoopDetector.record()` is called at `loop.py:721`, but no `is_loop_detected()` fired in this run (the only trigger would have produced a `LOOP_DETECTED` error). A model that repeats a *path* rather than an exact *call signature* slips through it.

### 3.5 Feedback messages bloat the context
Each stalled iteration appends two big messages (skip warning listing up to `_SKIP_WARNING_CAP = 6` calls + `+N more`, and the stall message listing all ~17 unused tools). Across ~18 iterations this added tens of thousands of tokens and pushed the model further into degenerate repeat behaviour (the messages themselves are the last thing in context when it picks its next call).

### 3.6 Provider/stream errors are not counted against the turn
`consecutive_failures` (`loop.py:308`) only counts **tool** failures. Stream/rate-limit errors raised inside `stream_with_retries` never increment it, so a rate-limited provider cannot trigger `REFLECTION_LIMIT`; the loop just keeps calling the API.

## 4. Impact

- **Token waste:** ~93k tokens for a task that should take a few tool calls.
- **Rate-limit starvation:** each iteration = 1 API call; on Google's free tier (15 req/min) this guarantees a 429 mid-task, killing the whole turn (see `02-rate-limiting-quota-handling.md`).
- **Data corruption:** `requirements.txt` was clobbered ~10 times with different content; final state is arbitrary.
- **Bad UX:** the frontend is flooded with 13+ identical "Skipped calls" warnings and then a dead `[FAILED] Execution halted` panel with no way to resume.
- **Lost trust:** the assistant appears broken instead of gracefully saying "I got stuck rewriting X; here's what's done and here's what remains."

## 5. What the correct behaviour should be

The agent should detect a stuck model **within 1 extra iteration** and end the turn *successfully* with an honest summary, never by falling into a rate-limit wall.

### 5.1 Hard rules for the loop
1. **One write per path per turn.** A second `file_write` to a path already written this turn is blocked up front and replaced with feedback: *"`path` was already written this turn. To modify it, read it first and use file_edit; or delete it."* This kills failure mode 2 instantly.
2. **First full-batch repeat → feedback; second → finalize.** If every requested call was already executed this turn *and* nothing new executed, set `task_completed = True` and `break` immediately (no third round-trip).
3. **Path-stuck detector.** Track writes/edits per path; if the same path is targeted ≥ 2 times with no other file touched in between, treat as a stall and finalize.
4. **Stream/provider errors count toward the turn.** Increment `consecutive_failures` on `RateLimitError` / non-recoverable provider errors inside the iteration so `REFLECTION_LIMIT` can fire, and add a small cooldown between iterations after a 429.

### 5.2 Feedback message hygiene
- Collapse the skip warning to **one compact line**: `3 duplicate tool call(s) skipped (file_write → requirements.txt)`.
- Do **not** list all remaining tools in a system message; that text became part of the loop. Replace with a short directive: *"No new work happened. If the task is complete, write your final summary now and stop."*
- Keep the injected message small so it cannot dominate the context.

### 5.3 Graceful finalization
- When finalizing due to a stall, emit a `success`/summary event: *"Stopped after N iterations because the model stopped making progress. Created: [files]. Not yet done: [remaining steps]."* instead of a hard error.
- If the task is genuinely incomplete (created files but no final summary), show the partial state + a one-key "Continue" affordance (see `05-integrity-and-ux.md`).

## 6. Happy flow (step by step)

1. User asks: *"Build a complete FastAPI application named library-mgmnt-sys."*
2. Model calls `file_write(path=library-mgmnt-sys/requirements.txt, content=...)` → executes, result shown.
3. Model attempts `file_write` again on the same path (any content) → **blocked by the one-write-per-path guard** with a single-line feedback message appended; model switches to writing the next file (`app/main.py`, `app/models.py`, …).
4. Model accidentally re-emits an identical call → dedup skips it silently (no UI spam), one compact "N duplicates skipped" line appears, and the model continues with new work.
5. Iteration ends when the model produces a text summary with no tool calls → normal `break`.
6. Turn reports token usage accurately and lists created/modified files.
7. If the provider starts rate-limiting, the loop **paces itself** (cooldown + server-provided retry delay) instead of hammering, and never dies mid-task (see `02-…`).

## 7. Fix checklist

- [ ] Add "one write per path per turn" guard in `loop.py` (before `execute_tool`), with a clear feedback message.
- [ ] Make the stall handler finalize after the **first** no-progress iteration (`task_completed=True`) — remove the requirement for 2 consecutive stalls.
- [ ] Add a path-stuck detector (same path ≥ 2 writes without other progress).
- [ ] Count stream/provider errors into `consecutive_failures`; add iteration cooldown after 429.
- [ ] Replace the huge skip/stall system messages with short, actionable ones; cap the skip list to 3 entries + "+N more".
- [ ] On stall-finalize, emit a graceful `success` summary with created files + remaining work instead of an error.
- [ ] Tune/verify `LoopDetector` so a repeated *path* (not just exact signature) triggers `LOOP_DETECTED` within 3 iterations.
- [ ] Regression test: simulate a model that re-emits `file_write(path=X)` with (a) identical params, (b) different content, and assert the turn finalizes ≤ 2 iterations with a summary.
