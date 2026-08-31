# Turn / Loop

## Overview

The turn/loop is the engine core. User types a prompt â†’ LLM streams a response â†’ if the response contains tool calls, execute them and loop â†’ if no tool calls, stop. That is the entire loop.

### How opencode does it

The loop is a `while(true)` in `packages/opencode/src/session/prompt.ts`. Each iteration:
1. Assembles messages (user + assistant history + compaction summary if present).
2. Calls `processor.process()` which streams the LLM and handles events (reasoning deltas, text deltas, tool calls, tool results).
3. After the stream finishes, the processor returns one of three values: `"stop"`, `"continue"`, or `"compact"`.
4. `"stop"` = the last assistant message has no pending tool calls. The loop exits. This is emergent â€” the model decides when to stop.
5. `"continue"` = tool calls were present and executed. Loop again.
6. `"compact"` = context overflow detected. Run compaction, then continue.
7. One advisory guard: if the step count reaches `agent.steps` (configurable, default Infinity), append `MAX_STEPS_PROMPT` (a text nudge to wrap up).
8. One safety guard: `DOOM_LOOP_THRESHOLD = 3` â€” if 3 consecutive tool calls have identical name and input, ask the user for permission before continuing.

### How codex does it

The loop is in `codex-rs/core/src/session/turn.rs`. Each turn:
1. Builds a `Prompt` (instructions + history as `ResponseItem[]` + tool specs).
2. Calls `client.run(prompt)` which hits the OpenAI Responses API.
3. Processes the response stream as `EventMsg` variants (tool calls, content deltas, reasoning).
4. Continuation is driven by response events: if the response includes tool-use items, tools execute and a new turn starts. If no tool-use items, the turn ends.
5. No mid-turn guidance injection. No harness-level loop detectors. The model controls the flow.

### What zenith has today

**Files:**
- `server/agents/loop.py` â€” 2110 lines. The main `AgentLoop` class.
- `server/agents/prompt_executor.py` â€” 1203 lines. Orchestrator that routes to captain/crewmate/default paths.
- `server/agents/recovery.py` â€” Wraps the loop with error recovery (provider errors â†’ events).
- `server/agents/validation.py` â€” Post-turn validation.
- `server/agents/provider_adapters.py` â€” Provider-specific adaptation.
- `server/agents/loop_detection.py` â€” `LoopDetector`: SHA-256 signatures over tool params, window of 10, repeats threshold of 2, consecutive identical limit of 3.

**The loop's per-iteration pipeline (loop.py lines 907â€“1791):**
1. Build context via `context_manager.build_messages` using 5 tiers (T0â€“T5).
2. Inject `SESSION_STATE` (list of files already written this session).
3. Check compaction thresholds â†’ summarize if needed.
4. **Inject PROGRESSIVE_GUIDANCE** â€” advisory user-role messages at 40K/70K/100K token thresholds.
5. **Inject ITERATION_GUIDANCE** â€” advisory user-role messages at 6/10/14 LLM calls.
6. Stream LLM completion â†’ raw text + tool calls.
7. Process tool calls with duplicate-call blocking, file-write-replay blocking, file-read caching, heavy-output isolation, output compaction.
8. **Done detection**: all calls repeated + no work â†’ "task_completed".
9. **Stall detection**: `STALL_FINALIZE_AFTER_ITERATIONS = 2` â†’ "stall_finalized".
10. **Loop detection**: `LoopDetector.is_loop_detected()` â†’ error event.
11. **Salvage pass**: any forced exit â†’ one tools-free completion asking the model to produce a final answer from gathered evidence.
12. Turn-manifest + false-claim rewriting (if model claims work was done but manifest says otherwise, rewrite the claim).
13. Safety iteration bound: `max(10, min(ctx_tokens // 2000, 150))`.

**Key constants (server/config/constants.py):**
- `PROGRESSIVE_GUIDANCE_LEVELS` â€” 3 levels at 40K/70K/100K tokens
- `ITERATION_GUIDANCE_LEVELS` â€” 3 levels at 6/10/14 calls
- `SALVAGE_INSTRUCTION` â€” forced text for salvage completion
- `STALL_FINALIZE_AFTER_ITERATIONS = 2`
- `LOOP_DETECTION_WINDOW_SIZE = 10`, `LOOP_DETECTION_MAX_REPEATS = 2`
- `HARD_STOP_USAGE_RATIO = 0.95`
- `DEGENERATE_MESSAGE_PATTERN` â€” regex to detect meta-placeholder messages

**The 3-way delegation branch (prompt_executor._execute):**
- Captain path: proactive explore delegation.
- Crewmate path: planâ†’build handoff.
- Default path: the loop above.

### What is correct

- The core `stream â†’ execute â†’ loop` pattern exists. It's just buried under heuristics.
- `RecoverableAgentLoop` wrapping provider errors into events is reasonable.
- Compaction triggering on threshold is correct.

### What is wrong / over-engineered / incorrect / missing

**Over-engineered (remove entirely):**
- PROGRESSIVE_GUIDANCE_LEVELS. Neither opencode nor codex inject mid-turn guidance. The model decides when to stop.
- ITERATION_GUIDANCE_LEVELS. Same reason.
- SALVAGE_INSTRUCTION and the salvage pass. opencode/codex just stop. No forced "produce final answer" pass.
- STALL_FINALIZE_AFTER_ITERATIONS. opencode/codex have no stall detection.
- LoopDetector (SHA-256 signatures, window, repeats). opencode has DOOM_LOOP_THRESHOLD=3 (same tool+input, permission ask). zenith's 3-deep detection with hashing is overkill.
- Turn-manifest and false-claim rewriting. Not in opencode/codex.
- Safety iteration bound computed from context window. opencode uses configurable `agent.steps` (default Infinity).
- The 3-way delegation branch. Not in opencode/codex.
- `DEGENERATE_MESSAGE_PATTERN` regex. No opencode/codex equivalent.

**Static/simulation code to remove:**
- `_E2E_INSTRUMENT` flag and `_instrument()` in context.py.
- `E2E_REQUEST` logging.

**Missing:**
- No clear "pending work" check like opencode's `hasToolCalls` on the last assistant message.
- No `DOOM_LOOP_THRESHOLD` equivalent (simple, clean safety).

## What we will do

Build a new loop following the opencode/codex pattern. The loop is a simple while-true:
1. Build context (system prompt + history).
2. Stream one LLM turn.
3. If the assistant response has no tool calls â†’ stop. Emergent termination.
4. If tool calls present â†’ execute them with hooks â†’ loop again.
5. If context overflow â†’ run compaction â†’ loop again.
6. One advisory guard: configurable MAX_STEPS (append nudge text when reached).
7. One safety guard: DOOM_LOOP_THRESHOLD=3 (same tool+input repeated â†’ ask permission).
8. No guidance injection. No salvage. No stall detection. No loop-detection hashes. No turn-manifest. No false-claim rewriting.

## What we will REMOVE
- `PROGRESSIVE_GUIDANCE_LEVELS`, `ITERATION_GUIDANCE_LEVELS`
- `SALVAGE_INSTRUCTION`, `DEFAULT_SALVAGE_TIMEOUT_SECONDS`, `SALVAGE_TIMEOUT_ENV`, `SALVAGE_DIGEST_MAX_ITEMS`
- `STALL_FINALIZE_AFTER_ITERATIONS`
- `LOOP_DETECTION_WINDOW_SIZE`, `LOOP_DETECTION_MAX_REPEATS`, `LOOP_IDENTICAL_CONSECUTIVE_LIMIT`
- `HARD_STOP_USAGE_RATIO`, `CONTEXT_SUMMARY_THRESHOLD`
- `DEGENERATE_MESSAGE_PATTERN`
- `RecoverableAgentLoop` (merge error handling into processor)
- `validation.py`, `provider_adapters.py`
- Turn-manifest, false-claim rewriting
- The 3-way delegation branch in prompt_executor
- `_E2E_INSTRUMENT` and `_instrument()`

## Regex audit
| Regex | opencode/codex uses it? | Action |
|---|---|---|
| `DEGENERATE_MESSAGE_PATTERN` | No | Remove |

## Verification / signoff
- [ ] New loop runs without guidance injection
- [ ] Stop is emergent (model emits zero tool calls)
- [ ] Doom-loop guard works (3 identical calls â†’ permission ask)
- [ ] Compaction triggers on overflow threshold
- [ ] No salvage, no stall detection, no loop-detection hashes
- [ ] No turn-manifest, no false-claim rewriting
- [ ] TUI receives events via transport adapter
- [ ] ruff + pytest + runtime smoke pass

## Status: Pending
