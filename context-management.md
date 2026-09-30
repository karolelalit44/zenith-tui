# Context Management & Smart Compaction — Research and Implementation Analysis

**Status:** Design proposal. No code changed.
**Scope:** `server/` (Python agent), compared against `ref_repo/opencode`, `ref_repo/codex`, `ref_repo/pi` (Cortex substrate) + `@animus-labs/cortex` docs, plus the 2024–2026 literature.
**Method:** Direct source reading with `file:line` citations. Claims about our own code were verified by reading the files, not inferred.

---

## Table of contents

1. [Executive summary](#1-executive-summary)
2. [Current-state analysis](#2-current-state-analysis)
3. [Problems and failure modes](#3-problems-and-failure-modes)
4. [Research findings from the reference systems](#4-research-findings-from-the-reference-systems)
5. [Academic and industry research](#5-academic-and-industry-research)
6. [Context architecture proposal](#6-context-architecture-proposal)
7. [Recommended data structures](#7-recommended-data-structures)
8. [Context priority hierarchy](#8-context-priority-hierarchy)
9. [Context layout and ordering](#9-context-layout-and-ordering)
10. [Context lifecycle](#10-context-lifecycle)
11. [Smart-compaction architecture](#11-smart-compaction-architecture)
12. [Refresh and invalidation strategy](#12-refresh-and-invalidation-strategy)
13. [Model-aware context strategy](#13-model-aware-context-strategy)
14. [Token optimization strategy](#14-token-optimization-strategy)
15. [Recommended metadata schema](#15-recommended-metadata-schema)
16. [Recommended state machine](#16-recommended-state-machine)
17. [Detailed implementation architecture](#17-detailed-implementation-architecture)
18. [Trade-offs and alternatives considered](#18-trade-offs-and-alternatives-considered)
19. [Failure modes and safeguards](#19-failure-modes-and-safeguards)
20. [Benchmarking and evaluation methodology](#20-benchmarking-and-evaluation-methodology)
21. [Concrete recommendations for our codebase](#21-concrete-recommendations-for-our-codebase)
22. [Phased implementation plan](#22-phased-implementation-plan)
- [Appendix A — reference-system constant tables](#appendix-a--reference-system-constant-tables)
- [Appendix B — dead / unwired context machinery in our codebase](#appendix-b--dead--unwired-context-machinery-in-our-codebase)

---

# 1. Executive summary

## 1.1 The finding that drives everything

Our context system is a **flat, undifferentiated message list rebuilt from scratch every turn**, with a single lossy summarization pass, a globally-shared tool-output truncation rule that is not differentiated by tool, and **no notion of a stable, ordered, individually-refreshable context region**.

Concretely, in `server/agents/context.py:170-293`, `build_messages` produces:

```
[0]  system   "<instructions>…</instructions><env>…</env><web_research>…<tool_reference>…"
[1]  system   "<repo_map>…</repo_map>"                     # only if history is non-empty
[2]  system   "<plan_to_execute>…</plan_to_execute>"       # only if a plan was adopted
[3]  system   "[Previous conversation summary]\n…"         # only if a summary exists
[..] user/assistant/user("[Tool: …]")…                     # one undifferentiated tail
[N]  user     <the new prompt>
```

Three structural consequences:

1. **No stable prefix.** Every turn re-renders `<env>` (which contains `datetime.now()`) and the system prompt is re-composed from lambdas (`server/agents/prompts.py:106-118`). This is *byte-stable within a day* by accident, not by design, and there is no cache breakpoint policy at all — `_cache_prefix_for` (`server/agents/compaction_service.py:221-237`) looks for `cache_control` markers that **no code ever sets**, so it always returns `[]`.
2. **Tool results are indistinguishable from user speech.** They arrive as `role="user"` messages whose content begins with `[Tool: <name> | Status: …]` (`server/toolkit/executor.py:166-195`). The model is told about the `[Tool:` convention nowhere in the system prompt, and `build_messages` *detects* them by string-prefix sniffing (`context.py:259-261`).
3. **Compaction is a single cliff.** `CompactionService.compact` summarizes a prefix once and then deletes it (`server/agents/compaction_service.py:510-531` → `session_store.py:289-334` rewrites the JSONL). Repeated compaction is summary-of-summary with no per-category retention, no reversal path, and no independent re-derivation of state that was thrown away.

## 1.2 What the reference systems do that we do not

| Capability | OpenCode | Codex | pi / Cortex | Zenith |
|---|---|---|---|---|
| Append-only durable event log, compaction as a **view**, not a deletion | ✅ `session`/`compaction` message rows, `history.ts:13-53` | ✅ rollout JSONL, `replace_compacted_history` | ✅ `SessionTreeEntry` with `CompactionEntry{firstKeptEntryId}` | ❌ JSONL prefix is **physically rewritten** |
| Named, ordered, individually-refreshable context **slots** | ⚠️ partial (`SystemContext` sources with `reconcile`/`replace`) | ✅ 40+ `ContextualUserFragment`s with diffing | ✅ `ContextManager` slots, stability-ordered | ❌ |
| Diff-based refresh (only re-emit what changed) | ✅ `SystemContext.reconcile` | ✅ `WorldStateSection` diff + `merge_contextual_fragments` | n/a (slots are consumer-driven) | ❌ |
| Tool-output **category-aware** degradation ladder | ✅ (V1 prune) / ⚠️ (V2 has none) | ✅ `TruncationPolicy`, `ensure_call_outputs_present` | ✅ 4 categories × 3 zones, cache-gated | ⚠️ one global 1000/2000-char rule |
| Overflow recovery that preserves the prefix | ✅ re-derives from the *pre-compaction* transcript | ✅ head-trim preserves cache | ✅ synthetic orphan tool results | ❌ |
| Token accounting = **provider usage anchor + estimated tail** | ❌ (chars/4 only) | ⚠️ (usage + 4-bytes heuristic) | ✅ `estimate.ts:63-143` | ⚠️ pure local count, tools counted as **0** |
| Machine-extracted, carried-forward state sidecar | ❌ | ❌ | ✅ `<read-files>` / `<modified-files>` accumulate across compactions | ❌ |
| Reversible compaction (can re-query raw history) | ❌ | ❌ (v1 server-side only) | ❌ | ❌ |

**Nobody in the reference set is reversible either.** ACM (arXiv 2607.23809) is the paper that makes the case: archive the raw messages to disk, return a summary plus a retrieval handle, and give the agent a `query_memory(summary_id, query)` tool. That single mechanism removes the dominant risk of summarization and is cheap to build on our existing JSONL store.

## 1.3 The single most important empirical finding for our goals

The user's stated goal is *"small models with good context ≈ large models with bad context."* The literature supports this only for **decision** quality, not bulk:

- **Squeez** (arXiv 2604.04979): a LoRA-tuned **Qwen 3.5 2B** tool-output compressor beats zero-shot **Qwen 3.5 35B** by 11 recall points at identical compression, while BM25 gets 0.22 recall and Last-N gets 0.05. *Supervised compression of one narrow decision beats a bigger model making that decision generically.*
- **ACM** (arXiv 2607.23809): **Qwen3.5-9B** + context-management tools gains +8% SWE-bench Verified over ReAct, with ~20% lower peak token use.
- **MEM1** (arXiv 2506.15841): **7B beats 14B** at 3.7× less memory.
- **PA-Tool** (arXiv 2510.07248): renaming tool schemas to match model pretraining priors gives Llama3.1-8B **+9.6pp** on multi-tool selection, beating Claude Sonnet 4.5. Zero tokens. Nobody classifies this as context management.
- **The counterweight:** **ToolStretch** (arXiv 2604.01955) measures degradation as **logarithmic** in window size: `acc(n) = a − b·log₂n` with `b ∈ [0.018, 0.031]` per doubling, R² = 0.946. Inverting gives a directly usable budget formula: `n* = 2^((a−α)/b)`. A representative model hits an 80% floor at **≈67K tokens**. Length alone is a much weaker lever than assumed; **structure, ordering, and reversibility are the real levers.**

## 1.4 The seven conclusions that define the proposal

1. **Adopt a slot model, not a message list.** A fixed, ordered, named set of context regions, each with its own refresh policy, its own staleness fingerprint, and its own budget. This is Cortex's `ContextManager` + Codex's `ContextualUserFragment` merged, and it is the single highest-leverage structural change.
2. **Make compaction a view, not a deletion.** Store an append-only entry log; compaction writes a `CompactionEntry{summary, first_kept_entry_id, sidecar}`. Reads stop at the compaction. This is pi's design and it is strictly better than our current JSONL rewrite.
3. **Make it reversible.** Every compaction archives the raw prefix and hands the model a retrieval handle. This is the ACM design and it is the only thing that makes lossy summarization safe.
4. **Differentiate tool output by category and distance from the end.** Four categories (re-readable / computational / non-reproducible / ephemeral) × three zones (hot / degrading / placeholder). Our current single rule over-compresses `file_read` and `bash` and under-compresses nothing — it just isn't tuned.
5. **Never hard-cut state into a summary alone.** Extract a machine-readable sidecar (files read, files modified, errors observed, commands run) deterministically, accumulate it across compactions, and re-inject it as a **slot** that compaction can never touch. This is the Cortex "slots are sacred" principle and pi's `<read-files>` sidecar, and it is the answer to Codex's failure mode (local compaction keeps only 20K tokens of user text and destroys everything else, `compact.rs:526-733`).
6. **Use provider usage as the token-count anchor.** Adopt pi's `estimate.ts:63-143`: find the newest assistant usage whose timestamp is not preceded by a newer prefix insertion, count the tail heuristically, and add tool-definition tokens. Fixes our "tools count as 0" bug.
7. **Order by position, deliberately.** Start = stable + high-value, end = fresh. But check which regime you are in: Veseli et al. (arXiv 2508.07479) show primacy holds only below ~50% window utilization; above that, primacy *fades* and later placement wins.

---

# 2. Current-state analysis

## 2.1 Component map

| Concern | Owner | Notes |
|---|---|---|
| Message array composition | `server/agents/context.py::ContextManager.build_messages` (L170-293) | Pure function; no persistence |
| Turn loop | `server/agents/simple_loop.py::SimpleLoop._run` (L344-1470) | `loop.py` is a 75-line compat shim |
| Compaction primitives | `server/agents/compaction.py` (219 L) | ANSI strip, head/tail trim, budgeted cut |
| Compaction orchestration | `server/agents/compaction_service.py::CompactionService.compact` (L320-614) | Owns generations, locks, events |
| LLM summarizer | `server/agents/summarizer.py` (130 L) | Never raises; degrades to a string builder |
| System prompt | `server/agents/prompts.py` + `server/prompts/{build,plan}.py` | Re-composed per turn from constants |
| Repo map | `server/workspace/repo_map.py` (489 L) | tree-sitter + PageRank-ish; cached forever |
| Tool-result formatting | `server/toolkit/executor.py::format_tool_result` (L166-195) | One global 10 000-char cap |
| Token counting | `server/providers/token_counter.py` + `context.py:329-335` | tiktoken if available, else chars/4 |
| Persistence | `server/storage/session_store.py` (JSONL, one file per session) | Compaction **rewrites** the file |
| Constants | `server/config/constants/context.py` (65 L) | Every number in the system |

## 2.2 The exact outbound array

From `simple_loop.py:379-390`:

```python
messages = self.context_manager.build_messages(
    history, system_prompt, prompt, model,
    summary=self._summary, plan_block=plan_context,
    use_system_prompt=True, repo_map=repo_map, session_id=session_id, mode=mode,
)
```

then, per iteration (`simple_loop.py:543`):

```python
dispatch_messages, _ = prune_inflight_messages(messages, keep_latest_tools=COMPACTION_KEEP_LATEST_TOOLS)
```

Final shape for a normal BUILD turn:

```
[0]      system    "<instructions>…</instructions>\n\n<env>…</env>\n\n<web_research>…</web_research>\n\n<tool_reference>…</tool_reference>"
[1]      system    "<repo_map>…</repo_map>"                    # only when history is non-empty
[..]     system    "<plan_to_execute>…</plan_to_execute>…"     # only when a plan was adopted
[..]     system    "[Previous conversation summary]\n…"        # only when a summary exists
[..]     user      "…"                                        # persisted user turn
[..]     assistant "…" + tool_calls:[…]                       # persisted assistant turn
[..]     user      "[Tool: file_read | Status: SUCCESS]\n…"    # persisted tool result (role=user!)
[..]     user      "…"                                        # new prompt (or overwrite of last user)
[..]     assistant "…"                                        # live turn
[..]     user      "[Tool: … | Status: …]\n…"                  # live tool result
[N]      user      "…"                                        # ALWAYS the last item
```

Two invariants worth noting as *correct*: `messages[-1]` is always `role="user"` (`context.py:283-291`), and tool-call/tool-result adjacency is preserved by the paired backwards walk (`context.py:262-268`).

## 2.3 Token accounting

`context.py:329-335`:

```python
def usage_tokens_composed(self, messages, model) -> int:
    return self.token_counter.count_messages(messages, model) + self._aux_tokens
```

**`_aux_tokens` is always 0.** `set_aux_tokens` (`context.py:135-136`) has zero production call sites. Tool schemas are therefore counted as **zero tokens** in every occupancy figure the TUI shows. `SchemaResolver.schema_tokens` (`server/toolkit/resolver.py:112`) exists and is also unused.

`TokenCounter.count_messages` (`server/providers/token_counter.py:81-90`) adds `SUMMARY_FRAMING_TOKENS=4` per message and `_REPLY_PRIMING=2` total, on top of a tiktoken or `cl100k_base` count. `token_breakdown` (`context.py:340-371`) is a *different*, cruder estimator (`len(content)//4`) and is what the compaction UI reports.

Consequence: every occupancy number we display is a lower bound that omits the tool schemas, and the two internal accounting paths disagree with each other.

## 2.4 Triggers

| Trigger | Location | Condition |
|---|---|---|
| Pre-loop compaction | `simple_loop.py:392-397` | `should_summarize` |
| Per-iteration compaction | `simple_loop.py:522-537` | `token_info.percent >= context_compaction_threshold` (default **0.70**) |
| Hard stop | `context.py:305-310` | `used >= total * 0.95` — errors **before** any LLM call |
| Provider overflow | `simple_loop.py:637-648` | `finish_reason` / HTTP error |
| Manual | `handlers.py:606-673` | RPC `context.compact` |

`should_summarize` (`context.py:298-303`):

```python
return used >= max_tokens * self.config.context_compaction_threshold or used >= max_tokens - reserve
```

The per-iteration path uses only the first clause. **The two compaction triggers are not equivalent** — the loop can fire at 70% while `should_summarize` would not.

## 2.5 Compaction mechanics

`CompactionService.compact` (`compaction_service.py:320-614`), in order:

1. Serialize on a per-session lock; skip if already in flight (L337-344).
2. Bump `_generations[session_id]`.
3. **Candidate prune** (L384-398): `prune_tool_outputs(candidate, force_intraturn=True)`. The authoritative `messages` list is untouched.
4. **Cut** (L408-414) via `_find_compaction_cut_budgeted` with `keep_tokens = clamp(8000, 0.25·(window−reserve), 20000, budget)`.
5. **Summarize** the prefix (`summarizer.py`), anchored on the previous summary.
6. **Persist** (L510-531): write `session.metadata["summary"]` and **delete the prefix rows** from the JSONL.
7. **Apply in memory** (L540-547), re-checking the generation.

The summarizer prompt (`summarizer.py:15-16`):

```
Objective
- {Objective}

Important Details
- {Important Details}

Work State
- {Work State}

Next Move
- {Next Move}

Relevant Files
- {Relevant Files}
```

+ rules requiring first-person voice, terse bullets, no fences, and *"Do not mention the summary process, compaction, or that this is a summary."*

**The summary is injected as `role="system"`, third in the array** (`context.py:225-231`), immediately after `<repo_map>` and before all history — the single most attention-favourable position in the request, occupied by a lossy artifact.

## 2.6 What survives compaction

| Retained | Mechanism |
|---|---|
| Tail of recent history | `_find_compaction_cut_budgeted`, `keep_tokens ∈ [8k, 20k]` |
| `file_read` and `todo` tool results | `PRESERVE_ON_COMPACT` (`compaction.py:22`) |
| Plan | `session.plan_output`, re-injected every turn |
| Repo map | `ContextManager._repo_map_cache`, process lifetime |
| System prompt | re-composed every turn |

| Lost | Mechanism |
|---|---|
| All tool output older than the 2nd-newest, replaced by a ≤300-char digest (glob/grep only) or a 1000-char head/tail trim | `prune_inflight_messages` runs **every iteration** |
| All assistant reasoning not in the retained tail | folded into the summary |
| Files read / files modified, unless the summarizer chose to write them | no deterministic sidecar |
| Error text and failing commands, unless the summarizer chose to write them | no deterministic sidecar |
| Git status, test results, environment deltas | never captured |

## 2.7 Refresh / invalidation: four unrelated mechanisms, no epoch

1. `ContextManager._window_estimated` — a flag, not staleness.
2. `session_workspace.py` read cache — `(mtime_ns, size)` fingerprint. This is the **only** working content-staleness system, and it is genuinely good.
3. `compaction_service._generations` — the only "epoch" in the system, scoped to compaction concurrency.
4. `RepoMap._snapshot()` (`repo_map.py:149-172`) — md5 of `rel|mtime_ns|size` + HEAD sha — **defined and never called**. The repo map never self-invalidates.
5. `index._CACHE` — 120 s TTL, and `WorkspaceStats` never reaches the prompt.

---

# 3. Problems and failure modes

Ordered by expected damage. Each is traced to code.

### P1 — Tool schemas are counted as zero tokens *(severity: high, silent)*

`context.py:130,135-136` — `set_aux_tokens` has no callers. Every occupancy figure, every compaction threshold decision, and every TUI gauge omits the tool-definition block. With ~16 active tools at 200–800 tokens of JSON schema each, the real context is 3–12k tokens larger than we believe. Compaction therefore fires later than intended, and the TUI under-reports.

### P2 — Tool results are `role="user"` with a string-prefix convention the prompt never defines *(severity: high)*

`executor.py:166-195` emits `[Tool: bash | Status: SUCCESS]\n…` as a **user message**. `context.py:259-261` detects them with `str(entry["content"]).startswith("[Tool:")`. Nothing in `BUILD_MODE_PROMPT` tells the model that this convention exists, and there is no `role="tool"` wire message. Consequences: (a) the model may treat a 10 000-char bash dump as something the user said; (b) any future provider that authenticates user messages differently from tool messages will behave unpredictably; (c) a tool result that legitimately begins with `[Tool:` would be misclassified.

### P3 — Compaction physically deletes history, so it is irreversible and unrecoverable *(severity: high)*

`session_store.py:289-334` rewrites the session JSONL, dropping the `{"t":"msg"}` rows whose ids are in `delete_ids`. After two compactions the only record of turn 1 is a paragraph of prose. There is no retrieval path, no archive, and no `query_memory` equivalent. Contrast: pi stores `CompactionEntry{firstKeptEntryId}` in an append-only tree and stops reads at it (`storage/index.ts:108-127`); OpenCode's `SessionHistory.latestCompaction` returns `max(seq)` and never loads pre-boundary rows (`history.ts:13-53`).

### P4 — A single lossy summary carries all durable state *(severity: high)*

The `SESSION_STATE_MARKER` constant is defined (`constants/agent.py`) and **never produced**. `todo_state` and `run_state` reach the model *only* as `todo` tool result strings, and `todo` is not in `PRESERVE_ON_COMPACT` — so after a prune the model sees `"[Old tool result content cleared]"`-equivalent content while the row still says `in_progress`. Codex's local compaction is worse: it retains **only** the last ~20K tokens of user text and destroys every assistant message, tool call, tool output, and world-state fragment (`compact.rs:526-733`). Cortex's answer — *"Slots are sacred. Context slots are never touched by compaction"* — is the correct one.

### P5 — Global, undifferentiated tool-output degradation *(severity: high)*

`prune_inflight_messages` (`compaction.py:154-219`) runs **every loop iteration** and reduces every tool result older than the newest 6 to either a ≤300-char digest (glob/grep only, `simple_loop.py:1213-1216`) or a 1000-char head/tail trim. So:

- `bash` output (build logs, test output, stack traces) is trimmed to 1000 chars with **no error-aware retention** — the failing line is often in the middle.
- `webfetch` results are trimmed to 1000 chars.
- `file_read` is exempt from digest-collapse but **not** from the 1000-char trim.
- TACO (arXiv 2604.19572) measured that observations with explicit error/failure signals must pass through unmodified; trimming them is the failure mode every serious system avoids.

### P6 — The system prompt duplicates the tool catalogue and the todo contract *(severity: medium, pure waste)*

`BUILD_MODE_PROMPT` enumerates all 10 tools with prose; the same 10 tools are delivered as JSON schemas in `openai_tools` (`simple_loop.py:377`); `<tool_reference>` then tells the model to call `get_tool_definition` for full schemas. The todo contract is stated three times in the template and a fourth time in-band by `_todo_nudge_text` (`simple_loop.py:166-187`). On a 128k window this is maybe 1.5–2k tokens of pure duplication on every single request, forever.

### P7 — Two non-equivalent compaction triggers, and no provider-usage feedback loop *(severity: medium)*

`should_summarize` (two clauses) vs. the loop's per-iteration percent check (one clause). And `usage_tokens` is a pure local count — `test_loop_regression.py:435-459` explicitly asserts that 127k of cumulative provider usage must *not* hard-stop. That test is right in spirit (cumulative ≠ occupancy) but it means we never use the provider's authoritative number at all. pi uses it as an anchor and falls back to a heuristic only for the tail.

### P8 — Silent compaction livelock on unknown/small models *(severity: medium)*

OpenCode: `if (context === undefined || context <= 0) return false` (`compaction.ts:173, 228`) — a model with no catalog entry **disables auto-compaction entirely**, and a long instruction baseline that makes the summarization prompt itself exceed `context − 4096` (`compaction.ts:183-184`) makes compaction a silent no-op forever with no event, no log, no error.

We have the same class of bug in `context.py:143-149`: an unknown model falls back to `min(128_000, config.max_context_tokens)` and sets `_window_estimated = True`, which is surfaced to the TUI but **never acted on**. We will therefore try to compact at 70% of a guessed window, which may be 8× off.

### P9 — In-flight pruning mutates content the model has already "read" *(severity: medium)*

`prune_inflight_messages` returns a new list but mutates shallow dict copies. It runs on the dispatch array every iteration, so the model sees `file_read` content shrink *between two turns of the same tool batch* without any notification. There is no "this was trimmed" marker in the general case — only a `time="compacted"` private key the model never sees.

### P10 — Dead machinery suggests an unfinished migration *(severity: low, but diagnostic)*

`RunningSummaryScheduler` is constructed (`prompt_executor.py:382`) and `schedule()` is never called. `_maybe_summarize_heavy_output` is a stub returning `None`. `_dynamic_max_output` never runs, so `MAX_TOOL_OUTPUT_TIERS` is inert. `summary_threshold` (0.8) and `CONTEXT_SUMMARY_THRESHOLD` (0.85) have no consumers. This is what an interrupted migration looks like, and it means **there is no single owner of context policy today** — which is the root cause of P1, P2, P4, P5 and P7 simultaneously.

### P11 — The repo map is a once-per-process snapshot with a dead invalidation hook *(severity: medium)*

`ContextManager._repo_map_cache` (`context.py:133, 161-168`) is set once and never invalidated. `RepoMap._snapshot()` is the intended hook and is never called. Worse, the map is injected *only when history is non-empty* (`context.py:190, 199`) — so a fresh session's first turn, the exact moment a model most needs orientation, gets no map at all.

### P12 — Tool-result media is base64-inlined every turn *(severity: low today, latent)*

`media()` in OpenCode's `to-llm-message.ts:13-19` puts `data: file.uri` into the request every turn; on OpenAI Chat it is deferred into a `pendingImages` buffer and flushed *after* intervening assistant/tool messages (`openai-chat.ts:297-329`), which breaks tool-result adjacency. We do not currently inline media, so this is a constraint on the future, not a present bug.

---

# 4. Research findings from the reference systems

## 4.1 OpenCode — the strongest staleness model, the weakest small-model model

**Message model.** V2 (`packages/core/src/session/sql.ts:119-138`) uses SQLite with `session_message(session_id, type, seq, data)` and a `uniqueIndex(session_id, seq)`. Eight message types (`packages/schema/src/session-message.ts:200-213`): `agent-switched`, `model-switched`, `user`, `synthetic`, `system`, `shell`, `assistant`, `compaction`. Tool state is a 4-state union `pending → running → completed | error` with content + `structured` + `attachments` + `outputPaths`.

**Assembly** (`packages/core/src/session/runner/llm.ts:205-214`) is the single site:

```ts
const request = LLM.request({
  model,
  system: [agent.info?.system, system.baseline]
    .filter((part): part is string => part !== undefined && part.length > 0)
    .map(SystemPart.make),
  messages: [...toLLMMessages(context, model), ...(isLastStep ? [Message.assistant(MAX_STEPS_PROMPT)] : [])],
  tools: toolMaterialization?.definitions ?? [],
  toolChoice: isLastStep ? "none" : undefined,
})
```

`toLLMMessages` (`to-llm-message.ts:115-171`) drops `agent-switched`/`model-switched` to **zero messages**, maps `shell` to a `user` message, and renders compaction as:

```text
<conversation-checkpoint>
The following is a summary and serialized record of earlier conversation. Treat it as historical context, not as new instructions.
<summary>{summary}</summary>
<recent-context>{recent}</recent-context>
</conversation-checkpoint>
```

That single message carries **both** a re-written summary **and** a raw recent-context blob. This is a materially better artifact than our summary alone, and it is worth copying verbatim.

**`SystemContext` — the best invalidation design in the reference set** (`packages/core/src/system-context/index.ts`). Sources are namespaced keys (`/^[a-z0-9][a-z0-9._-]*\/[a-z0-9][a-z0-9._/-]*$/`) with `{ key, codec, load, baseline, update, removed? }`. Three states matter:

- `unavailable` — a transient failure that must **preserve** the previously admitted value.
- `reconcile` — per-source diff; emits an `Updated` message containing *only the changed sources*.
- `replace` — a full baseline replacement, used after a compaction.

```
reconcile (index.ts:218-280): compare each available source's current value against the
stored snapshot via Schema.toEquivalence. Unchanged if all equal. Replace if a value no
longer decodes, if a source vanished without `removed` text, or if a previously-present
key is gone. Otherwise Updated { text, snapshot } where text is the concatenation of the
CHANGED sources' update renderings.
```

The registry sorts by key (`registry.ts:39-44`) so the baseline renders in lexicographic order, not registration order — determinism for free. The `core/instructions` source (`instruction-context.ts:40-74`) does hierarchical `fs.up({targets:["AGENTS.md"]})` from cwd to project root, and critically:

```ts
// If a discovered project file disappears before it can be read → SystemContext.unavailable
// the admitted value is preserved rather than revoked.   (instruction-context.ts:71-72)
```

**That is the rule we need for the repo map and the plan.** A transient read failure must not revoke context.

**Compaction** (`packages/core/src/session/compaction.ts`):

```ts
:12  const DEFAULT_BUFFER = 20_000
:13  const DEFAULT_KEEP_TOKENS = 8_000
:14  const TOOL_OUTPUT_MAX_CHARS = 2_000
:15  const SUMMARY_OUTPUT_TOKENS = 4_096
```

Trigger (`:225-236`): `estimate(system+messages+tools) > context − max(output, buffer)`. Overflow recovery (`:172-224`) is a **separate** path and requires **no durable assistant output yet** (`llm.ts:231-241` — `!publisher.hasAssistantStarted()`); otherwise a retry would be duplicating a partially-emitted turn. The summary request has `tools: []` and `maxTokens = min(output || 4096, 4096)`.

The head/recent split (`:128-159`) walks backwards accumulating `Token.estimate` until the next message would exceed `keep.tokens`, then **splits the boundary message mid-string**, putting the head into the summarization input and the tail into `recent`:

```ts
const remaining = Math.max(0, tokens - total) * 4
if (remaining > 0) {
  splitPrefix = conversation[index].slice(0, -remaining)
  splitSuffix  = conversation[index].slice(-remaining)
  split = index + 1
}
```

`select` filters out `type === "compaction"` entries, history loading hard-stops at the latest compaction seq, and `compactAfterOverflow` refuses when there is nothing to compact — three independent guards against summarizing a summary.

**Idempotency via message type, not a flag.** The compaction is *another message row*; pre-compaction rows are simply not selected. Failure is clean because `Compaction.Started` is durable and `Compaction.Ended` only fires on success (`projector.ts:395`, `message-updater.ts:375-389`).

**Pruning (V1 only)** (`packages/opencode/src/session/compaction.ts:243-287`) is the closest thing in the reference set to a good degradation ladder, and it has a hard bug:

```ts
:29  const PRUNE_PROTECT = 40_000
:30  const TOOL_OUTPUT_MAX_CHARS = 2_000
:31  const PRUNE_PROTECTED_TOOLS = ["skill"]
...
if (part.state.time.compacted) break loop    // idempotency marker
...
part.state.time.compacted = Date.now()        // marker, not deletion
```

`PRUNE_PROTECTED_TOOLS` is a **one-element list protecting `skill` — the most expensive output in the system — while leaving `todowrite`, the cheapest structured state, unprotected.** That is backwards, and it is exactly the mistake our `PRESERVE_ON_COMPACT = {"file_read", "todo"}` half-avoids.

**Tool-output bounding** (`packages/core/src/tool-output-store.ts:13-15`): `MAX_LINES = 2_000`, `MAX_BYTES = 50*1024`, `RETENTION = 7 days`. Overflow writes the full text to `<data>/tool-output/tool_<id>` and returns head+tail with `... output truncated; full content saved to ${path} ...`. The V1 agent-aware hint (`:129-131`) is excellent:

```
The tool call succeeded but the output was truncated. Full output saved to: {file}
Use the Task tool to have explore agent process this file with Grep and Read (with offset/limit).
Do NOT read the full file yourself - delegate to save context.
```

**Dead and hazardous:**
- `packages/core/src/config/compaction.ts:12-17` declares `prune` but **no core code reads it**. `AssistantTool.time.pruned` (`session-message.ts:136`) is never written. So **V2 has no pruning at all** — before compaction, every post-compaction tool result is resent at full fidelity on every turn; after compaction, all pre-compaction bytes vanish wholesale. `specs/v2/session.md:37,121,145` says so: *"Deterministic old tool-result pruning remains a separate follow-up."*
- `packages/core/src/util/token.ts` is the entire token estimator: `Math.round(input.length / 4)`. **No tokenizer anywhere in the repo.** A 10 MB attachment counts as ~3.5M phantom tokens.
- V1 has 9 provider-specific base prompts selected by **name substring** (`packages/opencode/src/session/system.ts:27-42`) — `muse-spark`→META, `gpt-4|o1|o3`→BEAST, `gpt`+`codex`→CODEX, `gpt`→GPT, `gemini-`→GEMINI, `claude`→ANTHROPIC, `trinity`→TRINITY, `kimi`→KIMI. Sizes 1.9k–3.9k tokens. Only `beast.txt` changes *turn policy* ("keep going until the user's query is completely resolved… your thinking should be thorough"); `default.txt:17-19,84` does the opposite ("minimize output tokens as much as possible… fewer than 4 lines"). **V2 ships none of these.**
- Small-model handling is title-generation only (`provider.ts:1878-1945` picks `gemini-flash`/`gpt-nano`/`claude-haiku` by *family name regex*, and the sole consumer is the title agent at `prompt.ts:216-236`). `capabilities.tools` is written (`plugin/models-dev.ts:100-104`) and **never read** — a model with `tool_call: false` is still offered every tool.
- `supportsNativeSystemUpdates` is `String(model.id) === "claude-opus-4-8"` (`anthropic-messages.ts:356`) — exact string equality on one model id, while the same file uses a tolerant regex family for the same model generation at `:664-676`.
- The OpenAI-Chat adapter defers tool-result images into a trailing `user` message (`openai-chat.ts:297-329`), silently relocating them past intervening assistant/tool messages and breaking the adjacency the model was told about.
- Cache breakpoints in V1 are `msgs.filter(role==="system").slice(0,2)` and `msgs.filter(role!=="system").slice(-2)` (`transform.ts:357-406`) — so the second-to-last message changes every turn and invalidates the tail breakpoint regardless of how long the tool loop runs.
- V2 uses a better policy (`packages/llm/src/cache-policy.ts:18-22`): `{ tools: true, system: true, messages: "latest-user-message" }`.

**Steal:** the `SystemContext` three-state reconcile/replace algebra; the `<conversation-checkpoint>` artifact shape; the "no durable assistant output yet" precondition on overflow recovery; the 7-day spill file with the agent-aware re-read hint; `applyCachePolicy`'s `latest-user-message` breakpoint.

**Avoid:** the name-substring prompt dispatch; single-element protection lists; a chars/4 estimator with no tokenizer; mid-message splitting in the head/recent boundary (it produces unparseable halves).

## 4.2 Codex — the best fragment/diff architecture, the worst lossy compaction

**`codex-rs/context-fragments/` is the single most reusable idea in the reference set.** Two dependencies, four files, ~350 lines, no serde, no tokio.

`ContextualUserFragment` (`context-fragments/src/fragment.rs:64-119`):

```rust
pub trait ContextualUserFragment {
    fn role(&self) -> &'static str;
    fn content_kind(&self) -> ContentItemKind;   // stable "<feature>.<name>"
    fn requires_separate_message(&self) -> bool { false }
    fn markers(&self) -> (&'static str, &'static str);
    fn body(&self) -> String;
    fn type_markers() -> (&'static str, &'static str) where Self: Sized;
    fn matches_text(text: &str) -> bool where Self: Sized { /* default impl */ }
    fn render(&self) -> String {
        let (start_marker, end_marker) = self.markers();
        let body = self.body();
        if start_marker.is_empty() && end_marker.is_empty() { return body; }
        format!("{start_marker}{body}{end_marker}")
    }
    fn render_fragment(&self) -> RenderedFragment { /* … */ }
}
```

Four decisions worth taking verbatim:

1. **`role()` returns `&'static str`, not an enum** — no protocol dependency, and extension crates can emit arbitrary roles.
2. **`render()` adds no separators.** The doc comment says implementations must include needed whitespace in `body()` — which is why nearly every `body()` starts with `format!("\n{}\n", …)`.
3. **`type_markers()` is an *associated function*, not a method**, so `matches_text` works without an instance. That is what makes re-recognition of a legacy fragment from raw text possible. Unmarked fragments (`("", "")`) never match arbitrary text — deliberately, so unmarked developer text is never mistaken for a fragment.
4. **`requires_separate_message()`** is the crucial escape hatch. Only 8 impls override it: `BaseInstructionsFragment`, `ModelSwitchInstructions`, `TokenBudgetContext`, `ManagedDeveloperInstructions`, `PersonalitySpecInstructions`, `MultiAgentUsageHint`, `MultiAgentRoleInstructions`, `ImageResizeNotice`, `GuardianPolicy`.

**The merge rule** (`core/src/context_manager/updates.rs:32-60`) is a 15-line run-length collapse:

```rust
match messages.last_mut() {
    Some((previous_role, previous_group, rendered_fragments))
        if *previous_role == role
            && *previous_group == MessageGroup::Mergeable
            && group == MessageGroup::Mergeable =>
    { rendered_fragments.push(rendered); }
    _ => messages.push((role, group, vec![rendered])),
}
```

Consecutive same-role mergeable fragments → one message with N `ContentItem`s. A role change or any `Standalone` breaks the run. `id: None` — **positional identity, not UUID**.

**The trust split** (`context-fragments/src/additional_context.rs` + `core/src/state/additional_context.rs:23-30`) is the security-relevant bit:

| Kind | Role | Markers | Example |
|---|---|---|---|
| `Untrusted` (browser DOM, external text) | `user` | `<external_browser_info>…</external_browser_info>` | fenced, cannot override developer policy |
| `Application` (host-trusted) | `developer` | `<automation_info>…</automation_info>` | can carry instructions |

Values are truncated to `MAX_ADDITIONAL_CONTEXT_VALUE_TOKENS = 1_000` at construction. `AdditionalContextStore::merge` (`state/additional_context.rs:16-34`) emits only keys whose value actually changed — verified by `additional_context_is_deduplicated_between_turns_while_retained`.

**World-state diffing** (`core/src/context/world_state/mod.rs`) is the mechanism that makes refresh cheap. `WorldState.sections` is an insertion-ordered `IndexMap<&'static str, Box<dyn ErasedWorldStateSection>>` (`mod.rs:287-289`); `render_full()` emits everything, `render_diff(previous_snapshot)` emits only changes. Registration order (`core/src/session/world_state.rs:35-322`) is the authoritative layout:

| # | Section | Fragment | Role | Markers |
|---|---|---|---|---|
| 1 | `model` | `ModelSwitchInstructions` | developer | `<model_switch>` |
| 2 | `personality` | `PersonalitySpecInstructions` | developer | `<personality_spec>` |
| 3 | `context_window` | `TokenBudgetContext` | developer | `<context_window>` (standalone msg) |
| 4 | `context_window_guidance` | `ContextWindowGuidance` | developer | `<context_window_guidance>` |
| 5 | `realtime` | realtime start/end | developer | `<realtime_conversation>` |
| 6 | `agents_md` | `UserInstructions` | **user** | `# AGENTS.md instructions` |
| 7 | `permissions` | `PermissionsInstructions` | developer | `<permissions instructions>` |
| 8 | `collaboration_mode` | | developer | `<collaboration_mode>` |
| 9 | `persistent_mode` | | developer | `<persistent_mode>` |
| 10 | `environments` | `EnvironmentsState` | **user** | `<environment_context>` |
| 11 | `environments_instructions` | | developer | `<environments_instructions>` |
| 12-13 | `apps` / `plugins` | | developer | `<apps_instructions>` / `<plugins_instructions>` |
| 14 | `tools` | | developer | `<tools>` |
| 15 | extensions | | varies | varies |
| 16 | `multi_agent_usage_hint` | | developer | standalone msg |
| 17 | `multi_agent_mode` | | developer | `<multi_agent_mode>` |
| 18 | `managed_developer_instructions` | | developer | standalone msg |

Note the **role alternation**: sections 6 and 10 are `user`-role, everything around them is `developer`. That is deliberate — AGENTS.md and environment facts are *context*, not *policy*, and must not be able to override policy.

Observed output (`core/tests/suite/context_annotations.rs:203-215`):

```
message developer ["guardian.approved_action"]
message developer ["generic.developer_instructions","token_budget.context_window_guidance",
                   "permissions.instructions","environments.instructions"]
message developer ["token_budget.context_window"]
message developer ["multi_agent.usage_hint"]
message developer ["multi_agent.mode_instructions"]
message user     ["environments.environment_context"]
message developer ["additional_content.automation_info"]
message user     ["additional_content.browser_info"]
message user     ["user.text","user.image","user.audio"]
message developer ["rollout_budget.remaining_tokens"]
message developer ["current_time.reminder"]
```

`AGENTS.md` render (`core/src/context/user_instructions.rs:23-34`):

```rust
fn type_markers() -> (&'static str, &'static str) { ("# AGENTS.md instructions", "</INSTRUCTIONS>") }
fn body(&self) -> String {
    let directory = self.directory.as_ref().map(|d| format!(" for {d}")).unwrap_or_default();
    format!("{directory}\n\n<INSTRUCTIONS>\n{}\n", self.text)
}
```

and its diff render prepends `"These AGENTS.md instructions replace all previously provided AGENTS.md instructions."` / on removal `"The previously provided AGENTS.md instructions no longer apply."` (`world_state/agents_md.rs:9-11`).

**`ContextManager` (`context_manager/history.rs:46-69`)** — the storage shape to copy:

```rust
pub(crate) struct ContextManager {
    /// The oldest items are at the beginning. Snapshots share the vector until a
    /// caller needs to mutate it, avoiding deep copies for read-only consumers.
    items: Arc<Vec<ResponseItemEnvelope>>,
    /// Bumped whenever history is rewritten, such as compaction or rollback.
    history_version: u64,
    /// Monotonic user-input/reset revision, independent of compaction's history generation.
    user_message_revision: u64,
    token_info: Option<TokenUsageInfo>,
    reference_context_item: Option<TurnContextItem>,   // the diffing baseline
    world_state_baseline: Option<WorldStateSnapshot>,
}
```

`Arc` + copy-on-write makes `for_prompt()` O(1) for read-only consumers. `history_version` and `user_message_revision` are **two separate revision counters** because compaction and rollback invalidate different things.

**Read path** (`history.rs:232-249`):

```rust
pub(crate) fn for_prompt(self, input_modalities: &[InputModality]) -> Vec<ResponseItem> {
    self.for_prompt_annotated(input_modalities).into_iter().map(ResponseItemEnvelope::into_item).collect()
}
pub(crate) fn for_prompt_annotated(mut self, input_modalities: &[InputModality]) -> Vec<ResponseItemEnvelope> {
    self.normalize_history(input_modalities);
    Arc::unwrap_or_clone(self.items)
}
```

`normalize_history` (`:487-505`) runs four passes, **on the read path, not the write path**:

```rust
normalize::ensure_call_outputs_present(items);       // synthesize "aborted" for unpaired calls
normalize::remove_orphan_outputs(items);            // drop outputs with no call
normalize::strip_images_when_unsupported(input_modalities, items);
normalize::strip_audio_when_unsupported(input_modalities, items);
```

Synthetic IDs are **deterministic UUIDv5** (`normalize.rs:18-19, 146-153`) specifically to keep the prompt cache stable:

```rust
// Changing this value would change model-visible IDs and invalidate prompt caches.
const SYNTHETIC_OUTPUT_ID_NAMESPACE: Uuid = Uuid::from_u128(0x90d38d3e_6a5b_4d52_bfe2_2f1e634bfac4);
```

The stability requirement is a class invariant:

| Unpaired call | Synthetic output | Payload |
|---|---|---|
| `FunctionCall` | `FunctionCallOutput` | `"aborted"` (info-level log only) |
| `ToolSearchCall` | `ToolSearchOutput` | `{status: completed, execution: client, tools: []}` |
| `CustomToolCall` | `CustomToolCallOutput` | `"aborted"` + `error_or_panic` (panics in debug) |
| `LocalShellCall` | `FunctionCallOutput` | `"aborted"` + `error_or_panic` |

And `remove_orphan_outputs` (`:155-225`) drops unpaired outputs, **except** `ToolSearchOutput` with `execution == "server"` (allowed standalone) and `FunctionCallOutput` with `call_id: None` (a named external tool event).

**Truncation at record time** (`history.rs:200-230`):

```rust
if let ResponseItem::FunctionCallOutput { output, .. } | ResponseItem::CustomToolCallOutput { output, .. } = &mut processed.item {
    // The override already includes the tool's serialization allowance.
    let policy = metadata.and_then(|m| m.fallback_token_limit_override)
        .map(TruncationPolicy::Tokens).unwrap_or(policy * 1.2);
    truncate_function_output_payload(output, policy, estimate_audio_token_count);
}
Arc::make_mut(&mut self.items).push(processed);
```

`policy * 1.2` is the serialization allowance (`protocol.rs:3270-3283`, `ceil`). The rollout therefore persists the **truncated** text, so history and context cannot diverge.

**Middle truncation** (`utils/string/src/truncate.rs:38-153`), char-boundary safe, budget split in half:

```rust
fn split_budget(budget: usize) -> (usize, usize) { let left = budget / 2; (left, budget - left) }
fn format_truncation_marker(use_tokens: bool, removed_count: u64) -> String {
    if use_tokens { format!("…{removed_count} tokens truncated…") } else { format!("…{removed_count} chars truncated…") }
}
```

Wrapper (`utils/output-truncation/src/lib.rs:14-25`):

```
Warning: truncated output (original token count: 10)
Total output lines: 1

0123456789…5 tokens truncated…0123456789
```

`TruncationPolicy` is `{ Bytes(n) | Tokens(n) }` (`protocol.rs:3233-3283`) and comes from `ModelInfo.truncation_policy` with an unknown-slug fallback of `bytes(10_000)` (`models-manager/src/model_info.rs:170`). The 4-bytes-per-token heuristic lives in one place:

```rust
// codex-rs/utils/string/src/truncate.rs:4
const APPROX_BYTES_PER_TOKEN: usize = 4;
pub fn approx_token_count(text: &str) -> usize { (text.len() + 3) / 4 }
```

**Compaction — four implementations, dispatched in `run_auto_compact` (`session/turn.rs:1199-1279`):**

| Feature | Implementation | Behaviour |
|---|---|---|
| `Feature::TokenBudget` | `compact_token_budget.rs:66-93` | **Window rollover.** Throws away ALL history, installs only initial context + optionally retained client-authored developer messages. `CompactedHistoryMetadata{ message: String::new() }` — no summary at all. |
| `RemoteCompactionSupport::V2` | `compact_remote_v2.rs` | In-band `compaction` output item from the server. Retains `user`/`developer`/`system` messages + `AgentMessage`s under `RETAINED_MESSAGE_TOKEN_BUDGET = 64_000`; caps a single `AgentMessage` at 10k tokens. |
| `RemoteCompactionSupport::V1` | `compact_remote.rs` | `POST /responses/compact`. |
| `Unsupported` | `compact.rs` | Local in-band summarization. |

The **90% rule** (`protocol/src/openai_models.rs:499-510`):

```rust
pub fn auto_compact_token_limit(&self) -> Option<i64> {
    let context_limit = self.resolved_context_window().map(|w| (w * 9) / 10);
    let config_limit = self.auto_compact_token_limit;
    if let Some(context_limit) = context_limit {
        return Some(config_limit.map_or(context_limit, |l| std::cmp::min(l, context_limit)));
    }
    config_limit
}
```

The trigger itself (`session/context_window.rs:52-121`) computes the **minimum** of two independent limits:

```rust
let base_window_tokens_remaining = [
    tokens_remaining(auto_compact_scope_limit, auto_compact_scope_tokens),
    tokens_remaining(full_context_window_limit, active_context_tokens),
].into_iter().flatten().min();
```

where `full_context_window_limit` is the model's real window × `effective_context_window_percent` and is described as *"a hard cap, independent of the auto-compaction scope."* **That two-limit `min()` is the right shape for us** (§13.3).

**The local compaction summary prompt** (`codex-rs/prompts/templates/compact/prompt.md`, whole file):

```
You are performing a CONTEXT CHECKPOINT COMPACTION. Create a handoff summary for another LLM that will resume the task.

Include:
- Current progress and key decisions made
- Important context, constraints, or user preferences
- What remains to be done (clear next steps)
- Any critical data, examples, or references needed to continue

Be concise, structured, and focused on helping the next LLM seamlessly continue the work.
```

and the prefix (`summary_prefix.md`, one line, no trailing newline):

```
Another language model started to solve this problem and produced a summary of its thinking process. You also access the state of the tools that were used by that language model. Use this to build on the work that has already been done and avoid duplicating work. Here is the summary produced by the other language model, use the information in this summary to assist with your own thinking process, and continue from where the other model left off.
```

**And then the damage.** `build_compacted_history_with_limit` (`compact.rs:526-733`):

```rust
const COMPACT_USER_MESSAGE_MAX_TOKENS: usize = 20_000;
...
for message in user_messages.iter().rev() {
    if remaining == 0 { break; }
    let tokens = approx_token_count(&message.message);
    if tokens <= remaining { selected_messages.push(message.clone()); remaining -= tokens; }
    else { selected_messages.push(truncate_text(&message.message, TruncationPolicy::Tokens(remaining))); break; }  // ← stops at the FIRST over-budget message
}
```

**Everything except the last ~20K tokens of *user text* is destroyed**: all assistant messages, all tool calls and outputs, all reasoning, all inter-agent traffic, and the entire world-state bundle. The first over-budget user message is middle-truncated and then the walk **stops**, so older-but-small messages are skipped too. This is the concrete illustration of why "summary-only" compaction is unacceptable and why §11 mandates a sidecar.

Observed post-compaction layout (checked-in snapshot `all__suite__compact__manual_compact_with_history_shapes.snap`):

```
## Local Post-Compaction History Layout
00:message/user:first manual turn
01:message/user:<COMPACTION_SUMMARY>\nFIRST_MANUAL_SUMMARY
02:message/developer:<PERMISSIONS_INSTRUCTIONS>
03:message/user:<ENVIRONMENT_CONTEXT:cwd=<CWD>>
04:message/user:second manual turn
```

**The mid-turn snapshot** shows a tool call and its output *dropped entirely*, and initial context landing *below* the summary because `BeforeLastUserMessage` inserts before the last real user message.

Idempotency is **text-prefix only**:

```rust
pub(crate) fn is_summary_message(message: &str) -> bool {  // compact.rs:572-574
    message.starts_with(format!("{SUMMARY_PREFIX}\n").as_str())
}
```

No `compacted` boolean, no `conversation-history-items` count. If a user ever types text beginning with that exact sentence, they are silently dropped from the retained history.

Overflow recovery is **unbounded head-trimming** (`compact.rs:296-350`):

```rust
Err(e) if matches!(e.details(), CodexErrorDetails::ContextWindowExceeded) => {
    if turn_input_len > 1 {
        // Trim from the beginning to preserve cache (prefix-based) and keep recent messages intact.
        history.remove_first_item();
        retries = 0;                    // ← retry counter reset: unbounded head-trimming
        continue;
    }
    sess.set_total_tokens_full(turn_context.as_ref()).await;
    ... return Err(e);
}
```

And the post-compaction user-facing warning (`compact.rs:394-397`):

> "Heads up: Long threads and multiple compactions can cause the model to be less accurate. Start a new thread when possible to keep threads small and targeted."

**AGENTS.md** (`core/src/agents_md.rs`) is the reference implementation for hierarchical instruction discovery:

```
1.  Determine the project root by walking upwards from cwd until a configured
    project_root_markers entry is found. Default marker list: (.git). If none is
    found, only cwd is considered. An empty marker list disables parent traversal.
2.  Collect every AGENTS.md found from the project root DOWN TO the cwd (inclusive)
    and concatenate their contents in that order.
3.  We do not walk past the project root.
```

Candidate names per directory, first hit wins (`agents_md.rs:267-281`): `AGENTS.override.md` → `AGENTS.md` → `project_doc_fallback_filenames`. So `AGENTS.override.md` **shadows** rather than merges with `AGENTS.md` in the same directory. Merge order is root-most first, cwd-most last, assembled after a 256-way concurrent probe so concurrency doesn't affect ordering (`:218-257`).

32 KiB budget, and the truncation is **byte-wise and lossy at both ends**:

```rust
let size = data.len() as u64;
if size > remaining { data.truncate(remaining as usize); }         // cuts mid-UTF8
if size > remaining {
    tracing::warn!(path = %p, remaining_bytes = remaining, "project doc exceeds remaining budget; truncating");
}
...
if remaining == 0 { break; }   // all deeper AGENTS.md files silently dropped, NO notice injected
```

Caching (`agents_md_manager.rs`) is keyed on **exactly two** things: environment selection set and project trust level. **Editing an `AGENTS.md` during a session does NOT invalidate the cache.** There is no watcher and no mtime check. `refresh()` runs per *sampling step*, not per turn.

Untrusted project ⇒ **no filesystem `AGENTS.md` at all**, only host-provided user instructions (`:61-63`).

**Steal:** the `ContextualUserFragment` trait (all four decisions); `merge_contextual_fragments` run-length collapse; the role alternation (user for facts, developer for policy); the `Untrusted`/`Application` trust split with `<external_*>` fencing; `Arc`-based COW history with two revision counters; the four normalization passes with deterministic UUIDv5 synthetic ids; record-time truncation with a 1.2× serialization allowance; the two-limit `min()` trigger; the `remove_first_item()` overflow ladder.

**Avoid:** summary-only retention; text-prefix idempotency markers; unbounded head-trim with a reset retry counter; the 32 KiB byte-truncation that silently drops deeper files; the `is_summary_message` prefix heuristic.

## 4.3 pi (`@earendil-works/pi`) — the substrate Cortex builds on

**The canonical message model is its own, not OpenAI's** (`packages/ai/src/types.ts:393-433`):

```ts
export interface UserMessage {
	role: "user";
	content: string | (TextContent | ImageContent)[];
	timestamp: number; // Unix ms
}
export interface AssistantMessage {
	role: "assistant";
	content: (TextContent | ThinkingContent | ToolCall)[];
	api: Api; provider: ProviderId; model: string; responseModel?: string; responseId?: string;
	usage: Usage; stopReason: StopReason; errorMessage?: string; timestamp: number;
}
export interface ToolResultMessage<TDetails = any> {
	role: "toolResult";
	toolCallId: string;
	toolName: string;
	content: (TextContent | ImageContent)[];
	details?: TDetails; usage?: Usage; addedToolNames?: string[];
	isError: boolean; timestamp: number;
}
export type Message = UserMessage | AssistantMessage | ToolResultMessage;
```

**`role: "toolResult"` is a first-class top-level role** with a `toolCallId`. The adapter layer lowers it to `role:"tool"` (OpenAI) or a `tool_result` block inside a `user` turn (Anthropic). This is the cleanest resolution of our P2.

**There is no `system` role and no `file` part type.** The system prompt is a side-channel field (`types.ts:487-491`):

```ts
export interface Context { systemPrompt?: string; messages: Message[]; tools?: Tool[]; }
```

**Signatures live on content blocks** — this is the stateless-reasoning-replay trick, and it is the single best idea in the repo:

```ts
export interface ThinkingContent {
	type: "thinking";
	thinking: string;
	thinkingSignature?: string;   // OpenAI: the ResponseReasoningItem id; Anthropic: the signature; Google: thoughtSignature
	redacted?: boolean;           // opaque encrypted payload stored in thinkingSignature for multi-turn continuity
}
export interface TextContent { type: "text"; text: string; textSignature?: string; }
export interface ToolCall { type: "toolCall"; id: string; name: string; arguments: Record<string, any>; thoughtSignature?: string; }
```

For OpenAI Responses the "signature" is the **entire serialized reasoning item** (`openai-responses-shared.ts:662-667`):

```ts
if (item.type === "reasoning" && slot?.type === "thinking") {
	const summaryText = item.summary?.map(s => s.text).join("\n\n") || "";
	const contentText = item.content?.map(c => c.text).join("\n\n") || "";
	slot.block.thinking = summaryText || contentText || slot.block.thinking;
	slot.block.thinkingSignature = JSON.stringify(item);      // ← includes encrypted_content
}
```

**`transformContext` is the designated pruning seam** (`packages/agent/src/types.ts:175-195`):

```ts
/**
 * Optional transform applied to the context before `convertToLlm`.
 * Use this for operations that work at the AgentMessage level:
 * - Context window management (pruning old messages)
 * - Injecting context from external sources
 * Contract: must not throw or reject.
 */
transformContext?: (messages: AgentMessage[], signal?: AbortSignal) => Promise<AgentMessage[]>;
```

Position in the path (`agent-loop.ts:288-302`), precisely:

| # | Stage |
|---|---|
| 1 | `context.messages` (AgentMessage[]) |
| 2 | **`transformContext`** ← runs here |
| 3 | `convertToLlm` (custom roles → UserMessage) |
| 4 | `Context { systemPrompt, messages, tools }` built |
| 5 | provider `transformMessages()` in pi-ai (cross-model signature/image downgrade) |
| 6 | adapter `convertMessages()` (provider shape) |

`transformContext` runs **before all token counting and before compaction**, at the *canonical* message level. The extension runner hands it a **`structuredClone`** (`extensions/runner.ts:984-1014`), so it must return a new list — it cannot mutate in place. That is the correct contract: it makes the hook pure and side-effect-free.

**System-message rules: pi has none.** `system-transcript`, `syncTranscript`, `SystemPromptState`, `supportsMidConvoSystemMessages`, `promptCacheLifetimes` — **none exist.** pi rebuilds the whole system prompt string from a byte-stable template whenever tools or resources change (`agent-session.ts:926-941`, `:1021-1055`, `buildSystemPrompt` at `core/system-prompt.ts:28-162`), and `Set`-dedupes guidelines (`:87-95`) so re-adding a tool doesn't change bytes. Cache-friendliness comes from **determinism of the template**, not from a diff protocol. That is a legitimate and much simpler alternative to Codex's fragments, and for a codebase at our size it may be the right first step.

Tool-set changes reach the model through three provider-specific channels, not a transcript message:

- **Anthropic** `tool_reference` blocks inside a tool result (`anthropic-messages.ts:1081-1114`), with the displaced content pushed as a *sibling block in the same user turn* (`:1248-1252`) because Anthropic rejects tool references mixed with ordinary content.
- **OpenAI Responses** `tool_search_call` / `tool_search_output` items (`openai-responses-shared.ts:305-332`).
- **Kimi** an in-conversation `system` message carrying deferred tool defs (`openai-completions.ts:1269-1279`) — the *only* mid-conversation system message in the repo, and it is Kimi-specific.

The load-point splitter (`utils/deferred-tools.ts:8-39`) is the cleanest reusable idea here: **deferred tools are marked by the transcript itself, not by an out-of-band set.**

```ts
export function splitDeferredTools(context, enabled, normalizeName = identityToolName) {
	// scan messages: assistant.toolCall.name → usedNames; toolResult.addedToolNames → deferredNames
	// a name is "deferred" iff a tool was *added* by a result and never *called*
	...
}
```

**Token accounting — the pattern to steal wholesale** (`packages/ai/src/utils/estimate.ts:63-143`):

```ts
function getLastAssistantUsageInfo(messages) {
	let latestPrefixTimestamp = Number.NEGATIVE_INFINITY;
	let usageInfo;
	for (let i = 0; i < messages.length; i++) {
		const message = messages[i];
		if (message.role === "assistant") {
			const assistant = message;
			// A newer prefix message was inserted after this response (for example, a
			// compaction summary), so its usage cannot describe the current prefix.
			const usageAppliesToPrefix = assistant.timestamp >= latestPrefixTimestamp;
			if (usageAppliesToPrefix && assistant.stopReason !== "aborted"
				&& assistant.stopReason !== "error" && calculateContextTokens(assistant.usage) > 0) {
				usageInfo = { usage: assistant.usage, index: i };
			}
		}
		latestPrefixTimestamp = Math.max(latestPrefixTimestamp, message.timestamp);
	}
	return usageInfo;
}
```

Then the estimate, which **includes tool definitions added after the anchor** — the piece most agents get wrong:

```ts
const estimate = estimateMessages(context.messages);
if (estimate.lastUsageIndex !== null) {
	const addedNames = new Set(context.messages.slice(estimate.lastUsageIndex + 1)
		.filter(m => m.role === "toolResult")
		.flatMap(m => m.addedToolNames ?? []));
	const addedToolTokens = estimateToolsTokens(context.tools?.filter(t => addedNames.has(t.name)));
	return { tokens: estimate.tokens + addedToolTokens, ... };
}
const prefixTokens = (context.systemPrompt ? estimateTextTokens(context.systemPrompt) : 0)
	+ estimateToolsTokens(context.tools);
```

**`isContextOverflow` — three detection cases, all three real** (`utils/overflow.ts:132-161`):

```ts
// Case 1: Check error message patterns
if (message.stopReason === "error" && message.errorMessage) {
	const isNonOverflow = NON_OVERFLOW_PATTERNS.some(p => p.test(message.errorMessage!));
	if (!isNonOverflow && OVERFLOW_PATTERNS.some(p => p.test(message.errorMessage!))) return true;
}
// Case 2: Silent overflow (z.ai style) - successful but usage exceeds context
if (contextWindow && message.stopReason === "stop") {
	const inputTokens = message.usage.input + message.usage.cacheRead;
	if (inputTokens > contextWindow) return true;
}
// Case 3: Length-stop overflow (Xiaomi MiMo style) - server truncates oversized input
// to fit the context window, leaving no room for output.
if (contextWindow && message.stopReason === "length" && message.usage.output === 0) {
	const inputTokens = message.usage.input + message.usage.cacheRead;
	if (inputTokens >= contextWindow * 0.99) return true;
}
return false;
```

Note `input + cacheRead` — **cache reads count against the window.** 25 overflow regexes at `:37-63` and 3 exclusion regexes at `:74-78` (Bedrock's `ThrottlingException: Too many tokens, please wait` would false-positive on `/too many tokens/i`).

**Cross-model normalization** (`api/transform-messages.ts`) is what makes "switch model mid-session" survivable, and every pass is gated on `isSameModel`:

```ts
const isSameModel = assistantMsg.provider === model.provider
	&& assistantMsg.api === model.api && assistantMsg.model === model.id;
...
if (block.type === "thinking") {
	if (block.redacted) return isSameModel ? block : [];   // opaque, only valid for the same model
	if (isSameModel && block.thinkingSignature) return block; // keep even if text is empty
	if (!block.thinking || block.thinking.trim() === "") return [];
	if (isSameModel) return block;
	return { type: "text", text: block.thinking };           // cross-model: demote to text
}
```

Plus: content-null normalization, non-vision image downgrade with consecutive-placeholder coalescing, tool-call-id normalization with a reverse remap so pairing survives renaming, **errored/aborted assistant message drop** ("replaying them can cause API errors, e.g. OpenAI 'reasoning without following item'"), and **synthetic orphan tool results** (`:158-220`) inserted before any user message and at the end of the transcript. That last one is mandatory the moment you allow pruning — we do not have it and our P5 pruning creates exactly this condition.

Compound tool-call ids: `{call_id}|{item_id}` for OpenAI Responses, a hash for foreign providers (`openai-completions.ts:1006-1030`). `call_id` is the pairing key; `id` is the cacheable item identity. The report also notes the OpenAI-Responses id can be 450+ chars with `|`/`+`/`/`/`=` while Anthropic requires `^[a-zA-Z0-9_-]+$` max 64.

**Compaction — the single best model in the reference set** (`packages/agent/src/harness/compaction/compaction.ts`):

```ts
export interface CompactionSettings { enabled: boolean; reserveTokens: number; keepRecentTokens: number; }
export const DEFAULT_COMPACTION_SETTINGS = { enabled: true, reserveTokens: 16384, keepRecentTokens: 20000 };

export function shouldCompact(contextTokens, contextWindow, settings) {
	if (!settings.enabled) return false;
	return contextTokens > contextWindow - settings.reserveTokens;
}
```

**The cut-point rule** (`:328-444`) is the algorithm to copy:

```ts
function findValidCutPoints(entries, startIndex, endIndex): number[] {
	// valid cut points: user / assistant / bashExecution / custom / branchSummary /
	// compactionSummary messages, plus branch_summary and custom_message entries.
	// NEVER a toolResult — you cannot split an assistant's tool batch.
}
export function findCutPoint(entries, startIndex, endIndex, keepRecentTokens) {
	const cutPoints = findValidCutPoints(entries, startIndex, endIndex);
	if (cutPoints.length === 0) return { firstKeptEntryIndex: startIndex, turnStartIndex: -1, isSplitTurn: false };
	let accumulatedTokens = 0, cutIndex = cutPoints[0];
	for (let i = endIndex - 1; i >= startIndex; i--) {
		const entry = entries[i];
		if (entry.type !== "message") continue;
		accumulatedTokens += estimateTokens(entry.message);
		if (accumulatedTokens >= keepRecentTokens) {
			for (let c = 0; c < cutPoints.length; c++) if (cutPoints[c] >= i) { cutIndex = cutPoints[c]; break; }
			break;
		}
	}
	while (cutIndex > startIndex) {                       // never cut immediately after a compaction
		const prevEntry = entries[cutIndex - 1];
		if (prevEntry.type === "compaction") break;
		if (prevEntry.type === "message") break;
		cutIndex--;
	}
	...
	return { firstKeptEntryIndex: cutIndex, turnStartIndex, isSplitTurn: !isUserMessage && turnStartIndex !== -1 };
}
```

Walk backwards until `>= keepRecentTokens`, then **snap forward to the nearest valid cut point**; `toolResult` is never a cut point. If the cut lands mid-turn, `isSplitTurn` is set and a **second summary** is generated for the turn prefix with `maxTokens = min(0.5 * reserveTokens, model.maxTokens)` (`:762-796`).

**Compaction is a session-tree entry, never a deletion** (`harness/types.ts:403-412, 453-464`):

```ts
export interface CompactionEntry<T = unknown> extends SessionTreeEntryBase {
	type: "compaction";
	summary: string;
	firstKeptEntryId?: string;
	tokensBefore: number;
	retainedTail?: AgentMessage[];
	details?: T;
	usage?: Usage;
	fromHook?: boolean;
}
```

The tree union is `MessageEntry | ThinkingLevelChangeEntry | ModelChangeEntry | ActiveToolsChangeEntry | CompactionEntry | BranchSummaryEntry | CustomEntry | CustomMessageEntry | LabelEntry | SessionInfoEntry | LeafEntry`. The projection (`session/session.ts:61-92`):

```ts
export function defaultContextEntryTransform(pathEntries) {
	let compaction = null;
	for (const entry of pathEntries) if (entry.type === "compaction") compaction = entry;
	if (!compaction) return [...pathEntries];
	const entries = [compaction];
	if (compaction.retainedTail) { /* everything after the compaction */ }
	else if (compaction.firstKeptEntryId) { /* from firstKeptEntryId to the compaction */ }
	// plus everything after
	return entries;
}
```

And the read path stops at the compaction (`storage/index.ts:108-127`):

```rust
pub async fn readPathToRootOrCompaction(leafId: Option<&str>) -> Vec<SessionTreeEntry> {
	...
	while let Some(current) = current {
		path.push(current);
		if stop_at_entry_id.is_some() && current.id == stop_at_entry_id { break; }
		if current.r#type == "compaction" {
			if current.retained_tail.is_some() { break; }
			stop_at_entry_id = current.first_kept_entry_id.clone();
		}
		...
	}
}
```

**The summary is a plain `user` message** (`harness/messages.ts:4-17, 120-164`):

```ts
export const COMPACTION_SUMMARY_PREFIX = `The conversation history before this point was compacted into the following summary:\n\n<summary>\n`;
export const COMPACTION_SUMMARY_SUFFIX = `\n</summary>`;
```

**The file-op sidecar is the part we must copy** (`harness/compaction/utils.ts:24-72`):

```ts
sections.push(`<read-files>\n${readFiles.join("\n")}\n</read-files>`);
sections.push(`<modified-files>\n${modifiedFiles.join("\n")}\n</modified-files>`);
```

Extracted from assistant tool calls, persisted structurally in `CompactionEntry.details = { readFiles, modifiedFiles }`, and **carried forward across successive compactions** (`extractFileOperations`, `compaction.ts:49-72`). This is precisely the durable state that Codex's local compaction destroys and that our `SESSION_STATE_MARKER` was supposed to carry.

The summary is iterative (`UPDATE_SUMMARIZATION_PROMPT`, `:483-520`): feed `<previous-summary>` back with rules `PRESERVE all existing information` / `ADD` / `UPDATE Progress` / `PRESERVE exact file paths, function names, and error messages`. The skeleton is `## Goal / ## Constraints & Preferences / ## Progress (### Done / In Progress / Blocked) / ## Key Decisions / ## Next Steps / ## Critical Context`.

`serializeConversation` (`utils.ts:91-132`) emits `[User]:`, `[Assistant thinking]:`, `[Assistant]:`, `[Assistant tool calls]:`, `[Tool result]:` and **truncates each tool result to `TOOL_RESULT_MAX_CHARS = 2_000`** — same constant as OpenCode, independently arrived at.

**Summarization calls deliberately poison nothing and cache nothing** (`:118-138`):

```ts
// Summaries are standalone requests, so isolate routing and avoid cache writes that cannot be reused.
const requestOptions = { ...options, cacheRetention: "none", sessionId: uuidv7() };
```

**Storage** is an append-only tree in SQLite (`packages/storage/sqlite-node/.../001_initial.sql`): `sessions(id, created_at, cwd, parent_session_id, metadata, active_leaf_id)`, `session_entries(session_id, id, entry_seq, parent_id, type, timestamp, payload)` with `uniqueIndex(session_id, entry_seq)`, plus `session_sequences`, `branch_entries`, and **materialized aggregates** (`session_materialized`, `entry_materialized`) cached in the DB so session pickers never replay the transcript. `active_leaf_id` **is** the resume point.

**Capability flags are a `compat` matrix, not a bitfield** — `OpenAICompletionsCompat` includes `cacheControlFormat`, `supportsLongCacheRetention`, `supportsStrictMode`, `supportsOpenAIGrammarTools`, `sendSessionAffinityHeaders`, `deferredToolsMode`, `thinkingFormat` (9 variants: openai/openrouter/deepseek/together/zai/qwen/chat-template/qwen-chat-template/string-thinking/ant-ling), `requiresAssistantAfterToolResult`, `requiresReasoningContentOnAssistantMessages`, `requiresThinkingAsText`. `AnthropicMessagesCompat` includes `forceAdaptiveThinking`, `allowEmptySignature`, `supportsToolReferences`. And the version gate is a *regex*, not string equality (`anthropic-messages.ts:193-200`):

```ts
function defaultSupportsToolReferences(model): boolean {
	if (model.provider !== "anthropic" || model.id.includes("haiku")) return false;
	const version = model.id.match(/^claude-(?:opus|sonnet|fable)-(\d+)(?:-(\d+))?(?:-|$)/);
	if (!version) return false;
	const major = Number(version[1]);
	const minor = version[2] && version[2].length < 8 ? Number(version[2]) : 0;
	return major > 4 || (major === 4 && minor >= 5);
}
```

**pi does zero history trimming in its own request path** — exhaustive grep for `prune|slidingWindow|keepLast|trimHistory|dropOldest` returns only a docstring example. Everything is delegated to `transformContext`, and compaction is a caller. So the ladder lives in `harness/compaction/`.

**Steal:** the `Message` union with `role:"toolResult"` + `toolCallId`; signatures on content blocks; `transformContext` as a pure `(messages) -> messages` seam at the canonical level, before token counting; the two-pass usage-anchor + heuristic-tail estimator *including tool-def tokens*; three-case `isContextOverflow`; `findCutPoint` with valid-cut-point snapping and never-`toolResult`; the `CompactionEntry` view-not-deletion model; the accumulating `<read-files>`/`<modified-files>` sidecar; `cacheRetention:"none"` + throwaway `sessionId` for summarization; `transform-messages.ts` cross-model normalization incl. synthetic orphan tool results; regex-based capability gating.

**Avoid:** the `|` compound-id scheme if we can use plain OpenAI-style ids; the reasoning item serialized into a `textSignature` JSON string (fragile, and it inflates the char count that the estimator sees).

## 4.4 Cortex (`@animus-labs/cortex`) — slots, and the one real "compaction as a subsystem" design

Cortex is built on pi and adds exactly the layer we lack.

**The five-region message array** (`docs/cortex/context-manager.md`):

```
┌─────────────────────────────────────────────────────────────────┐
│ SYSTEM HEAD (position 0)          pi's leading system message   │
├─────────────────────────────────────────────────────────────────┤
│ SLOT REGION (positions 1..N)      ContextManager                │
│   persistent, named, stability-ordered                          │
├─────────────────────────────────────────────────────────────────┤
│ CONVERSATION HISTORY              pi-agent-core                 │
│   COMPACTION TARGET               grows organically             │
├─────────────────────────────────────────────────────────────────┤
│ EPHEMERAL CONTEXT                 ContextManager + Cortex       │
│   rebuilt every LLM call                                         │
├──────────── PREFIX CACHE BOUNDARY ──────────────────────────────┤
│ BACKGROUND TASK STATE             churns every tick             │
├─────────────────────────────────────────────────────────────────┤
│ CURRENT TICK CONTENT + USER PROMPT                              │
└─────────────────────────────────────────────────────────────────┘
```

**Compaction operates exclusively on the CONVERSATION HISTORY region.** Everything above (slots) and below (ephemeral, current prompt) is untouched. That is the structural answer to our P4.

**Slots are fixed, named, ordered, and stability-ranked.** `slots: string[]` — *"Order = position in message array. Most stable first for best prefix caching."* The constructor pushes `N` empty `{role:'user', content:''}` placeholders at construction so `setSlot()` can always overwrite a valid index without gaps. `setSlot()` is a **full replacement, not a merge**.

Cortex's rule: *"Put content that almost never changes first, semi-stable context after that, and high-churn context near the end of the slot list."* And: *"If the slot region grows beyond roughly 20 content blocks, add another explicit breakpoint or reduce slot fragmentation, because Anthropic may not check far enough back from the end-of-slots breakpoint."*

**Four Anthropic cache breakpoints** (`docs/cortex/system-prompt.md`), in Anthropic prefix order `tools → system → messages`:

1. System prompt (the head).
2. End of the slot region.
3. End of the stable prefix: old history + ephemeral + skills, before background state.
4. Last user message.

Cortex **strips** pi's tool-definition breakpoint because the system breakpoint already covers tools and Anthropic allows only four. Provider economics from the docs: Anthropic 90% read discount (1 024–4 096 min tokens), OpenAI 50% (1 024), Gemini 75–90%.

**Ephemeral context is rebuilt every call and never stored** — consumer ephemeral, then loaded skill instructions, then background task state, then a hard-capped headline block (default 2 000 tokens, because *"injected user-role content is never trimmed by microcompaction, so an unbounded block would inflate utilization without ever shrinking"*). All four sit after BP3 so they never extend the cached prefix.

**Tool-result persistence is proactive, at the tool boundary** (`docs/cortex/tool-result-persistence.md`) — five layers:

| Layer | When | Threshold | Action |
|---|---|---|---|
| Per-tool interceptor | Tool execution boundary | 25 000 tokens | Persist or bookend |
| Aggregate budget | `transformContext` after parallel tools | 150 000 tokens/turn | Persist or bookend largest first |
| `capToolResult` | Insertion safety net | 50 000 tokens | Bookend (no persist) |
| Microcompaction trim | Threshold-driven | per category | Persist or bookend |
| L3 emergency truncate | Context overflow | hard cap | Truncate to fit |

```ts
export const MAX_RESULT_TOKENS = 25_000;
export const BOOKEND_CHARS = 1_500;     // head + tail each
export const SKIP_RESULT_PERSISTENCE = new Set(['Read', 'Edit', 'Write', 'Glob']);
export const DEFAULT_TOOL_THRESHOLDS = { Bash: 7_500 };   // verbose, low signal density
```

Skip set reasoning: `Read` (content already on disk, re-readable with offset/limit), `Edit`/`Write` (short confirmation), `Glob` (capped at 100 paths). **Bash gets 7 500 instead of 25 000 because bash output is verbose with low signal density.** That is a per-tool budget keyed on signal density, not a global constant — exactly the dimension our P5 is missing.

Preview format with persistence:

```
[Result persisted: /path/to/tool-results/SubAgent-abc123.txt (45,230 chars, ~11,308 tokens)]

{first 1,500 chars}
... [~9,500 tokens trimmed; full content at /path/to/file.txt] ...
{last 1,500 chars}

Use the Read tool with offset/limit to examine specific sections.
```

**Layered three-tier compaction** (`docs/cortex/compaction-strategy.md`):

- **L1 microcompaction** — *"The agent's own text responses are never touched. Only `tool_result` content blocks are candidates. This means that research findings, analysis, and conclusions the agent has already articulated in its own words survive regardless of what happens to the raw tool output."* Tool categories: `rereadable | non-reproducible | ephemeral | computational`. Three zones by token distance from the end:

```
[Most recent message]
        |  Hot zone — full content, no trimming
        |  size = max(hotZoneMinTokens=16_000, contextWindow * hotZoneRatio=0.05)
        |---[hot zone boundary]
        |  Degradation span — bookended with shrinking sizes
        |  size = contextWindow * degradationSpanRatio=0.40
        |  bookend chars: bookendMaxChars=2_000 → bookendMinChars=256, linearly interpolated
        |---[degradation span boundary]
        |  Beyond — placeholder (most categories) or clear (ephemeral only)
[Oldest message]
```

| Context window | Hot zone | Degradation span | Still bookended | % of window |
|---|---|---|---|---|
| 32k | 16 000 | 12 800 | 28 800 | 90% |
| 200k | 16 000 | 80 000 | 96 000 | 48% |
| 1M | 50 000 | 400 000 | 450 000 | 45% |

Action matrix:

| Distance | rereadable | non-reproducible | computational | ephemeral |
|---|---|---|---|---|
| Hot zone | full | full (extended zone) | full | full |
| Degradation span | bookend (shrinking) | bookend (shrinking, persisted) | bookend (shrinking, persisted) | bookend (shrinking) |
| Beyond span | placeholder | placeholder (persisted) | placeholder (persisted) | **clear** |

Beyond-span placeholder preserves a breadcrumb so the agent doesn't redo work:

```
[Tool result trimmed -- WebFetch: "context compaction techniques 2026" -- see assistant response below for findings]
```

**Cache-aware gating** — L1 is dormant while the prompt cache is warm, and only runs when it has naturally expired:

| Provider | Short TTL | Long TTL |
|---|---|---|
| Anthropic / Bedrock | 5 min | 1 h |
| OpenAI | 10 min | 24 h |
| Google / Mistral / Azure | no caching (L1 runs freely) | no caching |

Plus a trim floor of 25% utilization. Cortex's own cost analysis (200k window, 34 ticks) is the honest bit:

```
                        90% cache    50% cache     No cache
No microcompaction:      707K eff.    1,250K       2,983K
With microcompaction:   841K eff.    1,020K       2,450K
Difference:              +19%         -18%         -18%
```

**With strong caching, microcompaction is ~19% more expensive due to cache invalidation at threshold crossings.** They chose uniformity anyway, buying ~12 extra ticks of headroom before L2. That trade-off should be made explicitly in our design, not by accident.

- **L2 summarization** — threshold **0.70** (deliberately earlier than the 75–83% some agents use and Codex's 90%, *"models degrade before hitting the limit"*). Preserves the last `preserveRecentTurns: 6` verbatim, with the reason spelled out: *"Tool call/result pairs only exist in conversation history. `messages.db` stores user-facing messages and agent replies, not tool calls."* The compaction target is sourced from the **original transcript, not the microcompacted in-memory version**, so the summarizer sees full-fidelity tool output. The summary is one `user`-role message:

```xml
<compaction-summary generated="2026-03-15T10:30:00Z" turns-summarized="24">
...
</compaction-summary>
```

Eleven required sections: Primary Request and Intent (verbatim), Key Technical Concepts, Files and Code Sections, Tool Call Outcomes, Errors and Fixes, **All User Messages**, Problem Solving, Pending Tasks, Current Work, **Key Decisions (Cumulative — "carried forward across compactions to prevent progressive loss")**, Optional Next Step. The prompt requires an `<analysis>` scratchpad first, which is stripped from the output.

- **L3 emergency truncation** — 0.90 of window, or reactively on `isContextOverflow`. *"an assistant message with `toolCall` blocks and its consecutive `toolResult` messages form an atomic group… the whole group is dropped together or kept together, so truncation never orphans a tool call or a tool result."*

**Observational memory (the default since 2026-04-10, replacing L2)** is built on Mastra's research. A background **Observer** extracts a timestamped, priority-annotated event log; a **Reflector** condenses that log at escalating compression levels 0→4. The agent sees the observation slot plus a raw tail. Reported 5–40× compression at 84–95% on LongMemEval.

The parts we should take, and the parts we should not:

| Take | Why |
|---|---|
| `_observations` as **a slot**, not a message | compaction never touches slots |
| Non-blocking background digestion (`digestIdle()`) with a bounded 60s observer timeout | the expensive call happens while nobody is waiting |
| "The observer's observations will be the ONLY information the assistant has about past interactions" | forces honesty about what the agent actually knows |
| **L3 never truncates observations**; force a sync observation before any truncation | prevents losing the compressed layer to save the raw layer |
| Dynamic buffer interval: `clamp((activationThreshold − util)·window / bufferTargetCycles, bufferMinTokens, min(bufferTokenCap, utilityWindow·0.6))` | adapts to any window and any slot configuration with no hard-coded "message budget" |

| Avoid | Why |
|---|---|
| Relying on a 0.9 activation threshold | we cannot justify 0.9 from evidence; the scaling law says ~67k |
| 5–40× compression as a target | compression ratio is not the objective; re-invocation rate is (TRACER) |
| Default `tool_catalogue` inside a system prompt with tool-count caps | OpenCode and Cline both got this wrong (see §5.5) |

**Model tiers** (`docs/cortex/model-tiers.md`) is a two-model design: primary for the loop *and for compaction summarization*, utility for WebFetch summarization and the bash safety classifier. The rationale is exactly ours: *"Conversation history summaries are the only record of what happened during agentic loops… Quality matters significantly here."* A per-provider utility mapping (Anthropic→Haiku 4.5, OpenAI→GPT-4.1 Nano, Google→Gemini 2.5 Flash Lite, Groq/Cerebras→Llama 3.1 8B, Mistral→Mistral Small 2506) with a **same-provider constraint** enforced at construction.

> **Our `weak_model` for summarization is a mistake.** `summarizer.py:41-45` uses `config.weak_model` when set. On Anthropic that means Opus-class conversation history is summarized by Haiku. Cortex explicitly argues the opposite, and Codex/OpenCode/pi all use the *primary* model with a reduced `maxTokens`. **Change this.**

**`model_name` and `provider_name` are accepted and ignored** by our `build_system_prompt` (`prompts.py:126-138`, asserted by `test_prompts_template.py:108-112`). Cortex composes its prompt from the *live toolset* instead: *"A prompt that names an absent tool is an instruction to hallucinate it: the talker followed a static 'use Glob' into an unknown-tool error and narrated the failure to the user."*

**`working-tags.md`** is worth a close read for a different reason: the same behaviour is enforced at **three layers** — a Response Delivery section, an example-driven Tool Usage section, and an `afterToolCall` hook that appends `[Do not narrate…]` to every tool result, *"the last thing the LLM sees before generating its next response, providing the strongest possible signal at the exact point where narration occurs."* ~30 tokens per tool call. This is a general technique we should use for any per-tool-result instruction, at our P5 trim sites.

---

# 5. Academic and industry research

Evidence tiers: **[PEER]** peer-reviewed · **[arXiv]** preprint · **[BLOG]** vendor/practitioner · **[REPO]** code only.

## 5.1 Length-driven degradation — contested, and the disagreement is informative

- **Liu et al., "Lost in the Middle"** [PEER] TACL 12:157–173, 2024; [arXiv] 2307.03172. U-shaped curve. **GPT-3.5-Turbo drops >20%**; at the nadir, 20- and 30-doc settings score **below closed-book (56.1%)** — adding documents made it worse than having none. Reader accuracy **saturates ~20 documents**; 20→50 docs buys ~1.5% (GPT-3.5) / ~1% (Claude-1.3). Their explicit prescription: *"rerank to push relevant docs toward the start, or truncate the ranked list."*
- **Chroma, "Context Rot"** [BLOG — technical report, 14 Jul 2025]. 18 models, methodologically strong because it **holds task complexity constant and varies only input length**. LongMemEval: 113k-token full conversation vs ~300-token focused extract — the gap is real for weak models; reasoning modes "narrowed but did not close" it. **The actionable finding: on ambiguous input, Claude-family models abstain, GPT-family models hallucinate.** That tells you what failure looks like per vendor. Also: a needle's cosine similarity to the query predicts its degradation rate.
- **Modarressi et al., NoLiMa** [PEER — ICML 2025] [arXiv] 2502.05167. 13 models ≥128K. **At 32K, 11 of 13 drop below 50% of their short-context baseline.** GPT-4o: **99.3% → 69.7%.** Add a distractor containing query keywords but irrelevant content and **GPT-4o's effective length collapses to 1K.** CoT and reasoning models do not rescue it.
- **Veseli, Chibane, Toneva, Koller, "Positional Biases Shift as Inputs Approach Context Window Limits"** [arXiv] 2508.07479. **This is the paper that reconciles the contradictions.** Normalizing by *relative* input length: **LiM is strongest only while input ≤50% of the context window.** Beyond 50%, primacy *fades* (at L_rel = 0.5, first-position accuracy can fall below middle-position) and you get a **distance-based bias** — later is better. At full length the ranking is **last > middle > first.** Also: **retrieval success is a prerequisite for reasoning; reasoning position-bias is largely inherited from retrieval.**
- **Zhang, Cui, Huang, Sang, "Positional Failures in Long-Context LLMs"** [arXiv] 2605.23170. At 64K, MiMo-v2-Flash: **96% with the target at the end, 8% in the middle.** Mainstream reasoning benchmarks never control for position, so they hide the effect.
- **"Diagnosing and Mitigating Context Rot in Long-horizon Search"** [arXiv] 2606.29718. Best agentic-realistic study. **Premature termination** — models give up *long before* the window fills, and the rate **correlates positively with context length after controlling for query difficulty.** Two conclusions to design around: (a) context management is **test-time scaling** — it lowers premature termination and buys more exploration, but **costs more tool calls and produces more unfinished trajectories**; (b) **the best method is model-dependent** — with a strong-agentic backbone (Qwen3.5-397B) sub-agent context *isolation* wins; with a weak one (GLM-4.7) plain `keep-latest (+summary)` wins and FoldAgent is near-worst.
- **Jagtap, "Is Context Rot Real?"** [arXiv/preprint, self-labeled null]. Bounded null up to 150K for gpt-5.5/5.4/5.4-mini/claude-sonnet-4-6: 7 330 present-needle trials, **48 failures (99.35%, 95% one-sided CP upper bound 0.87%)**. Its real value is the **scorer-automation warning**: naive scoring manufactured a catastrophic instruction-adherence collapse that resolved to 1.000 under document-level refusal detection.
- **Boolean, "Context Rot Quantified"** [BLOG — vendor, 15 Sep 2026]. 20 terminal-bench v4 tasks, prefill 0k/250k/500k. **GPT-5.6 Sol: 31% → 24% at 250k**, losing ~25% of solved tasks **regardless of whether the prefill related to the task**. **Claude Opus 5: flat under unrelated prefill, but 50% → 40% under *task-related* prefill.** The GPT failure mode is distinctive: it starts doing tool calls, then **reverts to answering questions from the earlier Q&A turns and ends its turn** — never observed for Claude. N=20, directional only.

**Synthesis for us:** length-driven degradation is robust for **non-lexical retrieval, multi-turn accumulation, and reasoning**; it is *not* established for simple literal retrieval on frontier models ≤150K. **Do not size the context window on "1M is fine."** But also: bulk hurts through **cost and position**, which compaction fixes.

## 5.2 Token elasticity — the finding that should change our `max_tokens` logic

**Han et al., "Token-Budget-Aware LLM Reasoning" (TALE)** [PEER] ACL Findings 2025; [arXiv] 2412.18547.

**Token elasticity: a too-small budget is worse than no budget.** Prompt budget of **50 tokens → 86 actual output tokens**; budget of **10 tokens → 157 actual output tokens.** The model abandons the constraint entirely and exceeds it by *more* than a comfortable budget would have. **Never set a hard output cap below some floor.** TALE-EP: 67% average token reduction, 59% dollar reduction, 81.03% vs 83.75% accuracy, 2.3s vs 10.2s.

**Our `default_max_tokens_for_context` (`constants/context.py:64-65`) is `max(DEFAULT_LLM_MAX_TOKENS, min(window // 2, 32_768))`.** The `// 2` on a small window could produce a cap below the floor. Check this.

## 5.3 Agentic context management — the two papers that define the design space

**CAT / SWE-Compressor** [PEER] **Findings of ACL 2026** (`2026.findings-acl.1032`, pp. 20604–20617); [arXiv] **2512.22087** (26 Dec 2025). Beihang University. *Note: the ID `2606.xxxxx` in the original brief was wrong; this is the correct citation.*

Core idea: **context maintenance is a callable tool in the action space**, not a post-hoc heuristic. Three-zone workspace: stable task-semantic anchors + evolvable long-term memory + high-fidelity short-term memory. The agent decides when to "fold" context.

**SWE-Compressor** (Qwen2.5-Coder-32B, SFT on CaT-Instruct, OpenHands scaffold, 65 536 ctx, ≤500 rounds): **57.6% on SWE-bench Verified** vs ReAct 48.8% and Threshold-Compression 53.8% — **on the same scaffold**. Context stabilizes ~32k tokens. **+8.5% scaling 150→500 interaction rounds** where baselines plateau/degrade.

Three transferable points:
1. **The summarizer backbone = the reasoning backbone**, so summaries stay in the model's own voice.
2. **Same SFT budget beats both ReAct and threshold compaction** — the gain is from *when* you compress, not *how much*.
3. **You can build the training set** by retroactively injecting compression into trajectories you already have.

**ACM — Agentic Context Management** [arXiv] **2607.23809** (26 Jul 2026). CMU; Meta advisory. **Lossless + agent-initiated.**

Two tools only:
- `manage_context` — compress since the last boundary via a summarizer LLM, **write the raw messages to `summary_{id}.json` on disk**, return a summary tagged `[summary_id : N]`.
- `query_memory(summary_id, query)` — loads the raw archived messages, an LLM extracts query-matched info.

System prompt + original question are always preserved. Post-training uses **dual constraints**: the teacher marks *where compression should have happened* (student rollouts without tools) **and *where it should not*** (student rollouts with tools).

**Qwen3.5-9B over ReAct: +27% BrowseComp-Plus, +16% DeepSearchQA, +8% SWE-bench Verified. ~20% peak token reduction.** Near-matches open models 40× larger.

The ablation is the important part: the 4B-vs-9B gap is *reasoning*, not context management — 9B issues **16.2 vs 1.2 tool calls/question** and runs **19.4 vs 2.0 turns** (57.3% vs 3.4%). **4B was not out of context when it gave up: 23K of a 131K budget consumed.**

**This is the whole thesis of the user's brief, quantified — and it is the strongest available evidence that better context management lets a smaller model close a large-model gap, provided the smaller model can actually act. It also says the bottleneck may not be where we think.**

## 5.4 Memory architectures

| System | Mechanism | Result |
|---|---|---|
| **LLMLingua / LongLLMLingua** [PEER] EMNLP 2023 / ACL 2024; [arXiv] 2310.06839 | Budget controller + iterative token-level compression + distribution alignment; **query-aware**, document reordering, subsequence recovery | 20× compression / 1.5pt GSM8K loss. LongLLMLingua **+21.4% on NaturalQuestions at ~4× fewer tokens**; 94% cost cut on LooGLE; 1.4–2.6× latency at 2–6× on ~10k prompts. **Critically: vanilla LLMLingua and Selective-Context perform *worse than zero-shot*. Query-awareness is the entire game.** |
| **MemGPT / Letta** [arXiv] 2310.08560 | OS virtual memory: main = RAM, archival = disk, recursive summarization, interrupts, paging | Nested KV: GPT-3.5 → 0% at 1 nesting; GPT-4 → 0% by 3. DMR: MemGPT 93.4% vs recursive summarization **35.3%**. Honest limit: MemGPT *"often stops paging before exhausting the retriever."* |
| **Sleep-time compute** [arXiv] 2504.13171 | Pre-compute against a context *before* the query | ~5× reduction in test-time compute at equal accuracy; +13%/+18% from scaling sleep-time; 2.5× lower cost/query. SWE-Features: ~1.5× fewer test-time tokens at LOW budgets, but plain test-time compute **wins at high budgets**. |
| **ACE** [PEER] **ICLR 2026**; [arXiv] 2510.04618 | **Evolving playbook**, not a summary. Generator/Reflector/Curator. Incremental delta bullets `[id] helpful=N harmful=M :: content`; grow-and-refine with embedding dedup | +10.6% agents, 86.9% lower adaptation latency, +14.8% over ReAct with **no labels**. Names two failure modes to adopt: **brevity bias** and **context collapse**. |
| **A-MEM** [PEER] NeurIPS 2025; [arXiv] 2502.12110 | Zettelkasten; new memory triggers link generation + evolution (rewrites neighbors) | Multi-hop F1 **27.02** vs 21.35 vs **9.65**. ~1 200 tokens/op vs 16 900 (85–93% cut), <$0.0003/op. |
| **Mem0 / Mem0ᵍ** [arXiv] 2504.19413 | Extract+consolidate+retrieve; graph variant adds relational edges | +26% relative LLM-judge; 91% lower p95 latency; >90% token cost saved. **Honest: graph only pays on temporal (58.13 vs 55.51), *hurts* single-hop.** |
| **Zep / Graphiti** [arXiv] 2501.13956 | Temporal KG, non-lossy fact versioning with validity windows | DMR 94.8% vs 93.4%. LongMemEval **71.2% vs 60.2%** full-context, latency **2.58s vs 28.9s**, **1.6k vs 115k tokens**. |
| **MEM1** [arXiv] 2506.15841 | RL-trained **constant memory**: one `<IS_t>` internal state consolidates *and* reasons | **MEM1-7B: 3.5× improvement at 3.7× memory reduction vs Qwen2.5-14B.** |
| **MAGMA** [PEER] ACL 2026 long; [arXiv] 2601.03236 | Four orthogonal graphs (semantic, temporal, causal, entity) + intent-aware router | **For coding agents, the causal graph (what broke what) is the under-served one.** |

**Consensus taxonomy** (four 2026 surveys agree on the content, disagree on the axes): working memory = the context window; episodic = archived raw turns (ACM's `summary_{id}.json`); semantic = repo facts, API signatures, "this broke in commit X" (Zep validity windows, MAGMA temporal/causal/entity); procedural = skill/pattern libraries (Voyager-lineage, ACE's playbook bullets). **The single most-cited open problem across all four surveys is the episodic → semantic consolidation transition.**

## 5.5 Small models — the specific evidence

- **PA-Tool** [arXiv] 2510.07248. Training-free: rename tool schemas to match the model's pretraining priors, using **logprob peakedness** as a familiarity signal. **Llama3.1-8B multi-tool selection 78.7% → 88.3% (+9.6), beating Claude Sonnet 4.5 (85.1%).** "No suitable tool exists" reliability +17.0 (Llama3.2-3B: 43.6 → 60.6). RoTBench 58.1 → 68.6. Schema-misalignment errors cut 80%. End-to-end τ-bench Retail: Qwen2.5-7B 6.8 → 9.7, Llama3.1-8B 9.7 → 11.1. **Free. Do this.**
- **"Can Small Agents Collaborate to Beat a Single Large Model?"** [arXiv] 2601.11327. Qwen3 1.7B–32B. **8B multi-agent with a thinking orchestrator matches 32B single-agent:** GAIA 23.0 vs 23.0, AIME 55.0 vs 45.0. **Orchestrator-limited, not executor-limited** — with orchestrator thinking on, 8B scores 23.0/23.0/23.6 with 1.7B/8B/32B sub-agents, i.e. flat. **Scaling sub-agents can hurt.** **Thinking only at the orchestrator is the win; thinking in sub-agents is neutral-to-negative.** Efficiency: 8B MAS uses **476 tool calls vs 698 (−32%)** at equal accuracy. Ablation: removing the File Inspector costs **GAIA −6.6pp**; web searcher and structured memory are cheap to remove. Also: **tools help retrieval, hurt knowledge reasoning** (GPQA −5.0 — "indiscriminate retrieval overrides correct parametric knowledge").
- **AgentFloor** [arXiv/preprint 2026]. 16 open-weight models 0.27B–32B + GPT-5, 16 542 runs, pre-registered TOST. **gemma4:26b (100%) strictly beats GPT-5 (80%) on no-tool instruction following** (+20.0pp, CI [+8.9, +33.3]). **GPT-5 is strictly better only on long-horizon planning under persistent constraints** (10% vs 0% absolute). Neither side is production-reliable there. Smallest reliable-by-80%-CI: A0 clears at 4B, A at 3B, **B never clears at any size in their corpus.** *They explicitly decline to claim equivalence where n=45 gave 24–35pp CIs — that restraint is the point.*
- **"Rethinking Scale"** [PEER] ACL Industry Track 2026 (`2026.acl-industry.123`). **Structured agent frameworks substantially beat direct prompting; single-agent gives the best performance-cost balance; routing multi-agent adds coordination overhead with limited gain** under small-model constraints.
- **ToolStretch / tool-use accuracy scaling law** [arXiv] 2604.01955. 4 open-weight models 7B–70B, 12 400 synthetic traces, 4K–128K, difficulty fixed. **`acc(n) = a − b·log₂n`**, per-doubling slope **b ∈ [0.018, 0.031]**, **mean R² = 0.946**. Degradation is **logarithmic, not multiplicative-per-token**. Retrieval failure does *not* explain it: even with the target schema in the first 1024 tokens, accuracy at 64K is **6.2pp below the 8K baseline** (0.873 → 0.741, p<0.001). Budget formula: **`n* = 2^((a−α)/b)`**; a representative model (a=0.94, b=0.022) hits an 80% floor at **≈67K tokens**.

## 5.6 Tool-output compression — and the metric that reveals whether it works

**Squeez** [arXiv] 2604.04979. 11 477 examples from SWE-bench repo interactions + synthetic outputs across **27 tool families**; train/dev/test split by repo *and* tool family. LoRA-tuned **Qwen 3.5 2B: precision 0.80, recall 0.86, F1 0.80 at 92% compression** — beats **zero-shot Qwen 3.5 35B A3B (recall 0.75) by 11 recall points** at identical compression, and the untrained 2B (0.53) by 33. **BM25 gets 0.22 recall; Last-N 0.05; First-N 0.14; Random 0.10.** On 59 negative examples Squeez returns empty output 80% of the time vs 7% — correctly saying "nothing here" is a learned tool-specific policy. **Why BM25 fails: relevant lines appear at the beginning, middle, or end, and usefulness depends on the query, not lexical overlap. Do not reach for BM25 on tool output.** Honest limit: measures single observations, not downstream task completion.

**TACO** [arXiv] 2604.19572. Self-evolving compression *rules*, no fine-tuning. Motivation measurement: hand-extracting useful text from 50 TB-2.0 trajectories removes **24.6–44.1%** of raw prompt tokens, and **redundancy is not cleanly separable from signal** — verbose logs contain exact evidence. **Observations with explicit error/failure signals are marked Critical and pass through unmodified**; rules apply only to non-Critical output. Six benchmarks. **TerminalBench: +1–4% standard, +2–3% under matched token budgets. 12–27% total token reduction.** LLM-judge: preserves critical info 96.0%, removes redundancy 81.0%, only 4.0% flagged as critical loss.

**The key ablation: more compression ≠ better.** LLM summarization and 200 human-curated rules remove *more* tokens than TACO yet gain less. Instruction-only LLM rules and static predefined rules both fall well short of interactively-refined rules. **"Preserve task-relevant signals over maximizing compression ratio."** Steal this mechanism: **implicit over-compression complaints as a training signal** — if the agent asks for full output or re-runs the same command, suppress the rule that fired and replace it with a more conservative variant.

**DTOC** [arXiv] 2609.26121. Reversible tool-output compression. `manage_context(enable=[], disable=[])`; disabled outputs become metadata-only placeholders (tool key, timestamp, token estimate); enabled ones restore the full `tool_result`. Model-agnostic, no provider API dependency. DeepSWE: **Sonnet 4.6: 20% → 50% solve, input −10.3%, steps −2.4%, cost/solved $26.27 → $8.65 (−67%). GPT-5.4: 33% → 50%, steps −32.3%, $9.30 → $2.64.** **The negative result: Opus 4.8 and Gemini 3.5 Flash saw solve rate unchanged and token consumption *up* 18–49%.** *"DTOC should not be deployed without model-specific tuning."*

**The reversibility ablation is the whole mechanism:** tracking-only **77.8% @ 87K** (worse than baseline, avg 4.2 file re-reads); disable-only **81.4% @ 57K** (beats baseline but non-zero re-reads = irreversible loss); **full DTOC 83.6% @ 61K with 0.0 re-reads.** The recipe: **disable aggressively, but keep re-enable available.**

**TRACER** [arXiv] 2608.29363. Compression as a sequential per-tool decision, with a named pathology: **the "compression–consequence gap"** — aggressive compression triggers costly tool *re-invocations* that offset the savings. **Static baselines make it worse: truncation and Self-Info *increase* total tokens 3–24%** vs keep-all, with re-invocation ≥0.07. REINFORCE policy: 29–46% token reduction at equal-or-better success, **re-invocation ≤0.025**, +15–18% over a tool-type-conditional static policy.

> **If you remember one thing from §5.6: measure tool re-invocation rate. It is the metric that reveals whether your compaction is actually saving anything.** Our `_HighUsageProvider` test (`test_loop_regression.py:435-459`) shows we think about cumulative-usage correctness; we have no re-invocation metric at all.

**trimout** [REPO, no paper] — the industrial version of "errors pass through unfiltered." Pass-through ≤30 lines; clean long output → first 5 + last 5 + log pointer; **errors ≤500 lines pass through entirely; errors >500 lines → head/tail + up to 30 extracted error lines.** Self-reported: **bash context −49%** across 3 sessions. n=3, unaudited — but the policy is sound and the implementation is a single Go binary.

## 5.7 Structured prompting and delimiters — the weakest-evidenced area, and the folklore is wrong

- **Anthropic's docs** [BLOG]: "Use XML tags in your prompts" — recommendations, not measurements.
- **The Delimiter Hypothesis** [BLOG + REPO — Systima, Mar 2026]. 600 model calls, 4 models (Claude Opus 4.6, GPT-5.2, MiniMax M2.5, Kimi K2.5) × 3 formats × 10 tasks × 5 runs. Primary metric is **deterministic boundary-violation scoring**, not an LLM judge — methodologically the best design here. **Round 1: XML 98.4% / Markdown 98.4% / JSON 98.8% — no meaningful difference.** Round 2 stress: GPT-5.2 delta 0.1pp, Claude Opus 4.6 0.2pp, Kimi K2.5 0.3pp. One model diverges: **MiniMax M2.5 96.4% XML / 84.0% Markdown / 96.4% JSON — a 12.4pp gap**, validated with 20 extra temp-0 runs: **20% failure rate on Markdown trojan injection (4/20, emitting the injected phrase verbatim); 100% on XML and 100% on JSON for the same payload.** Hardest task (18 simultaneous constraints): no model reached 100% on any format. **Verdict: "for 75% of models it does not matter at all."**

> **Design conclusion: there is no evidence that tagged sections help small models more than large ones.** Use XML/JSON for parseability and **injection resistance** (the MiniMax-Markdown trojan result is a reproducible vulnerability), not for reasoning quality. The one real size-sensitivity finding is about *where content sits*, not how it's delimited — see §5.8.

## 5.8 Position matters, and *where* depends on how full you are

**"Where to show Demos in Your Prompt" (DPP bias)** [PEER] EMNLP 2025 (`2025.emnlp-main.1503`). 10 models across 4 open families. **Relocating an identical demo block shifts accuracy up to ~50pp and flips nearly half of predictions.** *"Smaller models are most affected by this sensitivity, though even large models do remain marginally affected on complex tasks."* Concrete: **LLAMA-3-3B improved-prediction rate on GSM8K falls 42.0% → 11%** when demos move from system-prompt-start to end-of-user-message; **LLAMA-3-70B moves the opposite way, 21.5% → 88%.** **QWEN-1.5B strongly prefers early positions.**

**"Serial Position Effects of LLMs"** [PEER] ACL Findings 2025 (`2025.findings-acl.52`). Primacy effect in **73 of 104** model×task instances; most pronounced in T5-3b and Llama2-7b-chat. CoT mitigates SPE across most tasks but doesn't eliminate it; `Last1`/`Middle1` prompts sometimes *invert* the effect. **Prompting at position is unreliable.**

**"Cognitive Biases, Task Complexity"** [PEER] COLING 2025 (`2025.coling-main.120`). **Bigger models show smaller effect sizes** (BLOOM 7.1B vs 1.7B); instruction tuning increases robustness, tuning-dataset dependent. **"Order Matters" (PBIF)** [PEER] ACL Findings 2025 (`2025.findings-acl.646`): **constraints in "hard-to-easy" order** help, generalizing across architectures and sizes.

> **Design conclusion: for small models, front-load. But audit which regime you are in.** Veseli et al. make "put it at the start" conditional on being below ~50% of the window. Our design should therefore make the *layout* fixed but the *compaction threshold* the thing that keeps us in the favourable regime (§13.3).

## 5.9 Code-agent specifics

**Aider** [BLOG/REPO] — no peer-reviewed context-engineering paper. Techniques from `aider.chat/docs/repomap.html`:
- **Repo map:** tree-sitter → graph → **personalized PageRank** → binary search to a token budget within 15%. `map_tokens = 1024`; `map_mul_no_files = 8x`; edge weight = **√(reference count)** so one hot symbol can't dominate; map lines truncated at 100 chars; SQLite cache keyed on mtime. Personalization: **chat files ×50, identifiers mentioned in conversation ×10, named symbols ≥8 chars ×10.**
- `get_repo_map_tokens()` allocates **1/8 of the context window**.
- **ChatSummary = recursive summarization:** split at an assistant-message boundary, summarize the head, **keep the tail verbatim**, recurse if still over budget.
- **ChatChunks** (`aider/chat_chunks.py`): a chunk tree with `all_shown_lines()` and *shelved* lines — a line-level tree that knows exactly which lines it dropped.
- Documented failure modes: **stale in fast-moving monorepos; misleading under metaprogramming** (`method_missing`, metaclasses, macro-heavy Rust); **pointless below ~20 files; harmful when your context window already fits the repo.**
- **The SWE-bench Lite 26.3% resolve figure is widely mis-cited** — the SWE-bench post does not isolate the repo map's contribution. Treat it as end-to-end, not an ablation.

**Our `repo_map.py` is already Aider-grade**: tree-sitter, `git ls-files ∪ git status --porcelain`, per-file `(mtime, symbols)` cache, reference-graph scoring with `chat_files ×3`, binary-search budget fitting, real tiktoken bounding. **The gaps are staleness (§3 P11), the 1024-token cap being a fraction of Aider's 1/8 window, and the personalization signal being only `chat_files` (no conversation-identifier boosting).**

**Cline** [BLOG/REPO] — `ContextManager.ts`:
- `getNextTruncationRange` **preserves the first user/assistant exchange and truncates from the middle, removing an even number of messages** to preserve role alternation.
- `contextHistoryUpdates` replaces re-read file content with a **`[DUPLICATE FILE READ]` notice** at send time — a simple, high-value dedup.
- Auto-Compact is **LLM-based summarization gated on `isNextGenModelFamily()`** — Claude 4+, Gemini 2.5+, GPT-5, Grok 4. Everything else falls back to rule-based truncation. `autoCondenseThreshold` 0.75.
- **Two documented bugs to avoid:** (a) `maxAllowedSize = max(window − 40_000, window × 0.8)` then `min(..., threshold × window)` — **stacked thresholds amplify any misdetected window size** (issue #9181: reported 200K for a 1M model, compacted at ~160K, and **re-read the files afterward**); (b) short aliases like `"sonnet"` fail the version regex so Auto Compact **silently never fires** (#8315).
- **Lesson: log the *source* of the resolved context window, and apply exactly one clamp.** Our `_window_estimated` flag is 60% of this; we just don't act on it.

**Claude Code** [BLOG — official docs + source, `code.claude.com/docs/en/context-window`]. Compaction is lossy and the docs are explicit about what survives. **Re-injected from disk:** project-root `CLAUDE.md`, unscoped rules, auto memory, the plan file, up to **5 most-recently-modified files** (>5 000 tokens returns as a path reference, not content). **Lost until re-triggered:** rules with `paths:` frontmatter, nested `CLAUDE.md`. **Skill bodies: capped at 5 000 tokens/skill, 25 000 total, oldest dropped first, truncation keeps the file head** — put critical instructions at the top of `SKILL.md`.

**Microcompact** (from source, `src/services/compact/microCompact.ts`): `collectCompactableToolIds` → `getToolsToDelete` → `createCacheEditsBlock`. **The cached path uses server-side `cache_edits` so the prompt prefix stays warm.** The time-based path: when the gap since the last assistant message exceeds a threshold, the cache is already cold, so it content-clears all but the last N, and **floors `keepRecent` at ≥1** — the source comment gets it exactly right: clearing *all* results leaves the model with zero working context, "neither degenerate is sensible."

**Anthropic's session-management blog (15 Apr 2026)** [BLOG] is the most useful vendor statement available: **"due to context rot, the model is at its least intelligent point when compacting"**; bad compacts happen "when the model can't predict the direction your work is going." Their rules: **new task → new session**; `/compact <focus>` with instructions before a long task; **`/clear` beats `/compact` when you can write the brief yourself, because the resulting context is what you decided was relevant**; **subagent for anything whose output you only need the conclusion of.**

**API-side compaction** (Beta, header `compact-2026-01-12`) exposes `context_management.edits` with `type: "compact_20260112"`, `trigger: {type:"input_tokens", value: 150000}` (min 50 000), `pause_after_compaction`, and **`instructions` that fully replace the default prompt.** On some models with custom instructions the summarizer sees only the *visible* conversation — earlier thinking blocks are **not** in its input, so the summary is all the model retains of that work.

**Cursor** [BLOG — vendor, Nov 2025]: 12.5% higher accuracy, 2.6% improvement in code retention on 1 000+ file codebases. Vendor-published, sells the index, no methodology. Contrast Sourcegraph dropping embeddings for Cody (third-party data transmission, index maintenance, vector-search cost at 100k+ repos). The Agentless comparison is the useful data point: **prompting-based retrieval locates the ground-truth file 78.7% vs 67.7% embedding-based, 81.67% combined.**

**mini-SWE-agent** [BLOG/REPO] — for the cheap-model angle: **~100 lines of Python, no tools except bash, completely linear history (no compaction, no summarization, no message rewriting)**, and **>74% on SWE-bench Verified** (Gemini 3 Pro, Nov). Used by Meta, NVIDIA, IBM, Princeton, Stanford. The transferable lesson is the **opposite** of compression: **a perfectly linear, uncompressed history plus a single trivially-parseable action format beats elaborate scaffolds.** The v2 docs say it outright: *"SWE-agent jump-started the field in 2024. Back then we placed a lot of emphasis on tools and special interfaces. A year later, a lot of this is not needed."*

Its observation-truncation template is worth copying verbatim:

```
if len(output) < 10_000:  {"returncode": …, "output": …}
else: {"output_head": output[:5000], "output_tail": output[-5000:],
       "elided_chars": n, "warning": "Output too long."}
```

plus a `format_error_template` that specifically handles `finish_reason == "length"`.

**Long Code Arena** [arXiv] 2406.11612 (JetBrains): **project-level completion — composing context from file-tree-adjacent files gives CodeLlama-7B +16% in-file and +53% in-project EM** over target-file-only. CI repair: Mistral-7B/CodeLlama **4–9%**, GPT-3.5 17%. Bug localization: best embedding retriever 0.33 MAP, GPT-4 0.39 — **retrieval is the bottleneck and better embeddings help little.**

**LongCodeU** [arXiv] 2503.04359: 8 tasks, 3 983 examples, up to 128K. **Performance drops dramatically past 32K** despite claimed 128K–1M windows; at 64–128K some tasks go **near 0–10%.** Inter-code-unit *relation* understanding is hardest.

## 5.10 RAG vs long context, 2026

**Retrieval wins when:** the corpus doesn't fit (Zep: 115k → 1.6k tokens, 28.9s → 2.58s, **and accuracy up** 60.2% → 71.2%); reader accuracy saturates ~20 documents; the task is temporally structured (Mem0ᵍ +2.6 on temporal, **−** on single-hop); **distractors are topically adjacent** (NoLiMa's lexical-overlap distractor misleads *both* the long-context reader and BM25); the model is small or the interaction is long.

**Long context wins when:** the evidence is small, you know which part matters, and you need cross-referencing — **LongLLMLingua's +21.4% *over the original prompt*** is because query-aware compression raises key-information density and reorders.

**The 2026 nuance: it's positional discipline, not "RAG vs long context."** Three independent results converge — put what matters at the **start** (Liu et al.'s rerank suggestion; LongLLMLingua reorder; DPP bias) and at the **end** (Veseli et al. past 50%). And audit whether you are above or below 50% before applying primacy tactics.

---

---

# 6. Context architecture proposal

## 6.1 The one-sentence design

> **Context is a fixed, ordered, named, individually-budgeted, individually-invalidated set of regions assembled from an append-only entry log, rendered per model, where compaction is a *view* (a `CompactionEntry` with a retention pointer and a machine-extracted sidecar) and every lossy artifact has a raw handle the agent can query back.**

Everything below is a consequence of that sentence.

## 6.2 The six layers

```
┌─ L0  STORE ────────────────────────────────────────── append-only, never rewritten
│   session.jsonl:  entry log (messages + state events + CompactionEntry)
│   archives/:      raw tool outputs, raw compacted prefixes
├─ L1  REGISTRY ──────────────────────────────────────── what exists, what is valid
│   slot table      name → {source, budget, fingerprint, refresh policy, role, order}
│   entry index     seq → {kind, tokens, refs, superseded_by}
│   model profile   per-model limits + capability flags
├─ L2  ASSEMBLER ─────────────────────────────────────── build the request
│   render(slots, entries, model) → RenderedContext
├─ L3  LIFECYCLE ─────────────────────────────────────── when things change
│   promote / demote / refresh / invalidate / evict
├─ L4  COMPACTOR ──────────────────────────────────────── lossy, reversible, tiered
│   tool ladder → prefix fold → sidecar → archive handle
├─ L5  GOVERNOR ───────────────────────────────────────── model-aware budgets + triggers
│   effective window, reserve, thresholds, cache policy
```

The critical structural property: **L1 owns policy; L0 owns truth; L2 is a pure function of (L0 snapshot, L1 state, L5 profile).** Today our policy is smeared across `context.py`, `compaction_service.py`, `simple_loop.py`, and `prompt_executor.py`, which is why P1/P2/P4/P5/P7 all exist simultaneously.

## 6.3 The five-region layout

Directly adapted from Cortex, with Codex's role split and OpenCode's checkpoint artifact:

```
Region 0  SYSTEM HEAD        system-role  · byte-stable · cache breakpoint 1
          model-specific base instructions + operating invariants + tool policy
          (tool bullets generated from the LIVE toolset, per Cortex)

Region 1  STABLE SLOTS       user/developer-role · ordered most-stable-first · cache breakpoint 2
          1a  agent_identity        (immutable)
          1b  project_rules         AGENTS.md / zenith.md, hierarchical, capped
          1c  memory_ledger         the sidecar — files touched, errors seen, decisions
          1d  workspace_map         repo map (tree + key symbols)
          1e  skill_buffer          loaded skills only

Region 2  CHECKPOINT         user-role · the compaction artifact
          <conversation-checkpoint><summary/><work_state/><recent-context/></…>

Region 3  WORKING SET        chronological · append-only · the compaction target
          user / assistant(+tool_calls) / toolResult · high-fidelity

Region 4  VOLATILE TAIL      user-role · rebuilt every call · after cache boundary 3
          a  task_board           todo / run_state — re-injected, never summarised
          b  live_state           background jobs, in-flight ops, read receipts
          c  budget_notice        remaining context, injected only when it changes materially
          d  user_prompt          the current prompt
```

**Rules:**

1. **Region 1 and 2 are only ever *replaced in place at a fixed index*.** Region 1 is immune to compaction by construction (Cortex: *"Slots are sacred"*). Region 2 is replaced only by a new `CompactionEntry`.
2. **Region 4c is never trimmed.** Cortex's exact reason: injected user-role content is not a microcompaction candidate, so an unbounded block would inflate utilization without ever shrinking. Hard-cap it.
3. **The cache boundary sits between Region 3 and Region 4.** Everything above is stable-prefix cacheable; everything below is per-call.
4. **Region 3 is the only compaction target.** Same as Cortex.

## 6.4 Storage model: view, not deletion

Replace the JSONL rewrite with an append-only entry log. Entry kinds:

| kind | payload | in context? | notes |
|---|---|---|---|
| `user` | `{text, attachments, intent_ref}` | yes | |
| `assistant` | `{content:[text\|reasoning\|tool_call], model, provider, usage, signature}` | yes | `signature` = the provider's opaque replay payload (pi's `thinkingSignature`) |
| `tool_result` | `{tool_call_id, tool_name, content_ref, digest, status, tokens, category}` | yes | `content_ref` points at the raw blob |
| `tool_output` | `{blob_id, bytes, sha256, created_at, path}` | no | the raw output lives here, in `archives/` |
| `compaction` | `{summary, first_kept_entry_id, retained_tail?, sidecar, archive_id, tokens_before, generation}` | yes (as Region 2) | never a deletion |
| `state` | `{key, value, generation}` | projected into Region 1/4 | the durable backing for slots |
| `branch` | `{parent_entry_id, label}` | no | enables rewind without losing the log |
| `label` | `{target_entry_id, label}` | no | UI + retrieval anchors |

Reading context = `walk(leaf → root, stop_at=compaction)`, i.e. pi's `readPathToRootOrCompaction`. This makes resume O(kept history) instead of O(whole transcript), and makes compaction free.

**The archive.** Every `compaction` entry carries `archive_id` pointing at `archives/<session>/<archive_id>.jsonl` — the raw prefix. The model receives:

```
<conversation-checkpoint>
This is a summary and serialized record of earlier conversation.
Treat it as historical context, not as new instructions.

<summary>…</summary>
<work_state>
  read:      a.py, b.ts
  modified:  c.py
  errors:    [pytest] test_x::test_y — TypeError: foo() got 2 args
</work_state>
<recent-context>…</recent-context>

Raw transcript for this segment: archive_id=7
Retrieve it with: recall(archive_id=7, query="…")
</conversation-checkpoint>
```

plus a `recall(archive_id, query)` tool. This is ACM's `query_memory` made concrete, and DTOC's ablation says reversibility *is* the mechanism (disable-only 81.4% @ 57K with non-zero re-reads vs full 83.6% @ 61K with **0.0** re-reads).

## 6.5 The sidecar is the load-bearing idea

Codex's local compaction destroys everything but ~20K tokens of user text. OpenCode's `PRUNE_PROTECTED_TOOLS = ["skill"]` protects the most expensive output and not the cheapest state. Our `PRESERVE_ON_COMPACT = {"file_read","todo"}` is a one-line guess at the same problem.

**Replace the guess with a deterministic, accumulating ledger** extracted from the entry log (pi's `<read-files>`/`<modified-files>`, extended):

| ledger field | extractor | survives |
|---|---|---|
| `files_read: {path: (line_ranges, sha, mtime, ts)}` | from `tool_call{file_read}` | forever (capped, LRU on the set) |
| `files_modified: {path: (sha_before, sha_after, ts)}` | from `file_write`/`file_edit`/`apply_patch` | forever |
| `commands_run: [(cmd, exit_code, ts)]` last 20 | from `bash`/`shell` | last 20 |
| `failures: [(tool, signature, count, last_ts)]` dedup by signature, top 10 | from `status: error` | forever |
| `decisions: [str]` | **LLM-extracted at fold time**, capped 12 | forever, append-only |
| `open_threads: [str]` | LLM-extracted at fold time, capped 8 | rolling |
| `blocked_on: str \| null` | LLM-extracted at fold time | rolling |

Extraction is deterministic for the first four (no LLM, no cost, no failure mode). The last three come from the fold call itself, which means the summarizer returns **structured JSON, not prose** — and the structured parts are merged into the ledger, while the prose goes into the summary. This is a strict improvement on the "do not mention compaction" instruction we currently give the summarizer.

**The ledger is a slot (Region 1c), not a message.** It is never compacted. It is the answer to "where did the plan go," "which files did I touch," and "what was that error" — the three questions our current system answers worst.

## 6.6 What is never compacted (hard list)

1. The current user prompt and the current turn's tool exchanges.
2. Anything in Region 1 (all slots) — by construction.
3. The sidecar ledger.
4. All user messages in the retained tail.
5. Every tool **call** (the call is what makes the result meaningful); only the *result payload* degrades.
6. Error text within the retained tail — TACO's Critical-observation rule.
7. Any `file_read` whose ranges are still referenced by the read-receipt mechanism.

## 6.7 Migration shape

The proposal is additive in four seams:

| Seam | Today | Proposed | Risk |
|---|---|---|---|
| S1 | `build_messages` returns `list[dict]` | returns `RenderedContext` with `.to_wire(provider, model)` | low — internal |
| S2 | `role="user"` + `[Tool:` prefix for tool results | first-class `toolResult` with `tool_call_id` | **medium** — provider-dependent |
| S3 | `compact_history` rewrites the JSONL | appends a `compaction` entry | **medium** — storage migration |
| S4 | thresholds hard-coded in `simple_loop.py` | `ContextGovernor` with a model profile | low |

**S2 is the one to be careful about.** Some OpenAI-compatible providers are strict about `role="tool"`; some small/local models are not. Phase 1 should introduce the typed role in our canonical model and lower it to `role="user"` + `[Tool:` only for providers in an explicit capability list. That is pi's `compat` matrix, and it is reversible.

---

# 7. Recommended data structures

## 7.1 Selection rationale

| Candidate | Verdict | Reason |
|---|---|---|
| **Append-only entry log** | **adopt** | Only structure that makes compaction a view, resume O(1), and rewind possible. pi, OpenCode, Codex all converged here. |
| **Slot registry** | **adopt** | Only structure that makes per-region budget, staleness, and role policy expressible. Cortex + Codex. |
| **Message graph / DAG** | **partial** | Needed for *rewind*, not the main path. A parent pointer on each entry gives the essential edge for 1% of the complexity. |
| **Key-value state** | **adopt, scoped** | Exactly right for the sidecar and slot values. Wrong for the transcript (no ordering). |
| **Embeddings / vector retrieval** | **defer** | LongCodeArena: best embedding retriever 0.33 MAP vs GPT-4 0.39 — retrieval is the bottleneck and better embeddings help little. Aider's PageRank beats every embedding result in the literature. LongCodeArena project-completion: **tree-adjacent composition gives CodeLlama-7B +53% in-project EM.** |
| **File-backed context** | **adopt for archives only** | Raw tool output and compacted prefixes. Not for the hot path. |
| **Hierarchical memory** | **adopt as the ledger** | The four surveys agree episodic→semantic is the unsolved transition; a deterministic ledger is a defensible, cheap approximation. |
| **Full message tree** | **avoid** | pi's `SessionTreeEntry` union is right for a multi-branch TUI. We need rewind, not branching. A parent pointer is enough. |

## 7.2 Canonical types

```python
# ─── the entry log ────────────────────────────────────────────────────────────

class EntryKind(StrEnum):
    USER          = "user"
    ASSISTANT     = "assistant"
    TOOL_RESULT   = "tool_result"
    TOOL_OUTPUT   = "tool_output"    # raw blob; not in context
    STATE         = "state"          # durable slot / ledger backing
    COMPACTION    = "compaction"
    BRANCH        = "branch"
    LABEL         = "label"


@dataclass(frozen=True, slots=True)
class EntryRef:
    """Position in the log. Ordered, cheap, immutable."""
    seq: int
    session_id: str


@dataclass(frozen=True, slots=True)
class Entry:
    seq: int
    session_id: str
    kind: EntryKind
    parent_seq: int                  # gives the rewind graph
    ts: float
    payload: dict                    # kind-specific; entry is immutable once written
    # ─── the fields that make lifecycle cheap ───
    tokens: int                      # estimated tokens, cached at write time
    tool_call_id: str | None = None  # pairs to ASSISTANT.tool_calls
    tool_name: str | None = None
    status: Literal["ok", "error"] = "ok"
    category: ToolCategory | None = None
    content_ref: str | None = None   # → archives/<session>/<id>.jsonl
    digest: str | None = None        # ≤300-char structured replacement
    error_signature: str | None = None
    superseded_by: int | None = None # set when a later entry replaces this one
    generation: int = 0              # bumped on any context-policy change
```

**Why `tokens` is cached on the entry.** Every downstream decision needs per-entry token counts, and recomputing tiktoken over the whole log on every turn is O(n) tokenizer calls. Caching at write time makes the backwards cut-walk O(kept) integer comparisons. This is what OpenCode's `select` (`compaction.ts:128-159`) does.

**Why `parent_seq` rather than a full graph.** Rewind is the only graph operation we need. A `LABEL` entry plus a parent pointer gives a session tree; branching/forking is out of scope.

## 7.3 The tool-result record

```python
class ToolCategory(StrEnum):
    REREADABLE       = "rereadable"        # file_read, glob, grep, list_dir  → re-run is cheap
    COMPUTATIONAL    = "computational"     # explore, websearch, delegation    → expensive to re-run
    NON_REPRODUCIBLE = "non_reproducible"  # webfetch, one-shot jobs           → may be gone
    EPHEMERAL        = "ephemeral"         # job_output tail, notifications   → re-run is trivial
    MUTATING         = "mutating"          # write/edit/delete/apply_patch     → result is a receipt


@dataclass(frozen=True, slots=True)
class ToolResultEntry:
    tool_call_id: str
    tool_name: str
    category: ToolCategory
    status: Literal["ok", "error"]
    tokens_full: int
    digest: str
    archive_id: str | None            # None for REREADABLE/EPHEMERAL
    error_signature: str | None
    ts: float
```

The category is decided **at the tool boundary** by a registry keyed on tool name, overridable per tool. Cortex's `DEFAULT_TOOL_THRESHOLDS = { Bash: 7_500 }` because bash output is verbose with low signal density is the model: **per-tool budgets keyed on signal density, not a global constant.**

## 7.4 The slot registry

```python
class SlotRole(StrEnum):
    SYSTEM   = "system"      # high-authority policy → top-level system field
    DEV      = "developer"   # high-authority context → merged into a system/developer message
    USER     = "user"        # low-authority context → user message
    EXTERNAL = "external"    # UNTRUSTED → user message wrapped in <external_*>


class RefreshPolicy(StrEnum):
    IMMUTABLE     = "immutable"      # recomputed only on session create
    PER_TURN      = "per_turn"       # recomputed once per turn
    PER_STEP      = "per_step"       # recomputed before every provider call
    ON_MUTATION   = "on_mutation"    # recomputed when a write/edit/delete lands
    ON_WAKE       = "on_wake"        # recomputed on an explicit agent/user action
    ON_DEMAND     = "on_demand"      # only when the agent calls the loader tool


@dataclass(frozen=True, slots=True)
class SlotSpec:
    name: str
    order: int                      # == position in the assembled array; lower == more stable
    role: SlotRole
    policy: RefreshPolicy
    budget_tokens: int | None       # None → share of the volatile tail
    loader: str                     # dotted path to the loader callable
    fingerprint_keys: tuple[str,...]  # what to hash to decide "changed"
    compaction: Literal["forbidden", "allowed", "target"] = "forbidden"
    required: bool = False          # a loader failure blocks rather than degrades
```

Frozen + slotted: a slot spec is read on the hot path and never mutated, and `slots=True` removes the per-instance `__dict__` — 14 slots × ~40 specs is measurable at turn boundaries.

### Proposed slot table for Zenith

| # | name | role | policy | budget | loader | compaction |
|---|---|---|---|---|---|---|
| 1 | `agent_identity` | SYSTEM | IMMUTABLE | — | `prompts.base_instruction(mode)` | forbidden |
| 2 | `project_rules` | USER | ON_MUTATION | 8 192 | `slots.discover_project_rules` | forbidden |
| 3 | `memory_ledger` | USER | ON_MUTATION | 2 048 | `slots.render_ledger` | forbidden |
| 4 | `environment` | USER | ON_WAKE | 512 | `slots.render_environment` | forbidden |
| 5 | `workspace_map` | USER | ON_MUTATION | `min(W//8, 4096)` | `workspace.repo_map` | forbidden |
| 6 | `tool_policy` | DEV | PER_TURN | 1 536 | `slots.render_tool_policy(live_toolset)` | forbidden |
| 7 | `skill_buffer` | USER | ON_DEMAND | 8 192 | `skills.loaded` | forbidden |
| 8 | `task_board` | USER | PER_STEP | 1 024 | `slots.render_task_board` | **target-but-reinjected** |
| 9 | `live_state` | USER | PER_STEP | 1 024 | `slots.render_live_state` | **target-but-reinjected** |
| 10 | `budget_notice` | USER | PER_STEP | 256 | `slots.render_budget_notice` | forbidden |
| 11 | `user_prompt` | USER | PER_TURN | — | caller | forbidden |

Slot 1 is the *base instruction*; slots 2–11 are the fragment region. Slots 8 and 9 are marked `target-but-reinjected` because they change every step — they cannot be a stable prefix, but they also must not be the thing compaction destroys, because they are re-injected verbatim into Region 4 anyway.

**On budget ratios:** Aider allocates **1/8 of the context window** to the repo map. Our current cap is `min(1024, max(100, 0.05·W))` (`context.py:151-156`) — at a 128k window that is 1024, versus Aider's 16 384. Given LongCodeArena's **+53% in-project EM** from tree-adjacent context, and that a coding agent's dominant failure is reading the wrong file, this is the single highest-leverage budget change available. **Recommendation: `min(W // 8, 4096)`.**

## 7.5 The model profile

```python
@dataclass(frozen=True, slots=True)
class ModelProfile:
    model_id: str
    provider: str

    # ── limits (all with provenance) ──
    context_window: int
    context_window_source: Literal["catalog", "provider_api", "user", "default"]
    max_output_tokens: int
    tokenizer: str                    # cl100k_base | o200k_base | heuristic

    # ── effective budgets, derived ──
    effective_window: int             # window * effective_context_window_percent / 100
    reserve_tokens: int               # max(max_output, 16_384)
    hot_zone_tokens: int
    fold_threshold_tokens: int
    fail_threshold_tokens: int
    keep_recent_tokens: int

    # ── capability flags (regex/table-derived, never string equality) ──
    supports_tools: bool
    supports_images_in_tool_result: bool
    supports_mid_conversation_system: bool
    supports_reasoning_replay: bool
    tool_result_role: Literal["tool", "user"]
    degraded_reasoning_to_text: bool

    tier: Literal["frontier", "balanced", "efficient", "unknown"]
    prompt_cache: CachePolicy
```

**`context_window_source` is not decoration.** Cline shipped two documented bugs from window misdetection: stacked thresholds amplifying a wrong window (issue #9181) and an alias failing a version regex so compaction silently never fired (#8315). We already compute `_window_estimated` and surface it; the fix is to **act on it** (§13.3).

**Capability flags must be table/regex-derived, never string equality.** OpenCode's `String(model.id) === "claude-opus-4-8"` (`anthropic-messages.ts:356`) fails for `claude-opus-4-8-20260101`, a Bedrock ARN, or a Vertex alias. pi's regex (`anthropic-messages.ts:193-200`) handles the first; we should handle the rest by making unknown → conservative, never → optimistic.

## 7.6 The assembled context

```python
@dataclass(frozen=True, slots=True)
class RenderedContext:
    """The model-agnostic result of assembly. `.to_wire()` is the only provider-aware step."""
    slots: tuple[SlotInstance, ...]     # ordered, includes empty ones (stable indices)
    checkpoint: Checkpoint | None
    working_set: tuple[Entry, ...]      # ordered by seq
    tail: tuple[TailBlock, ...]         # volatile, never cached

    def fingerprint(self) -> str: ...   # hash of everything above; drives cache policy
    def estimate_tokens(self, model) -> int: ...
    def to_wire(self, adapter: ProviderAdapter) -> list[WireMessage]: ...
```

**Always include empty slot positions.** Cortex pushes `N` empty `{role:'user', content:''}` at construction so indices are stable for the life of the session. A slot that is empty still occupies its index. Without this, a slot that transiently fails to load shifts every subsequent block — a cache invalidation on every transient error.

---

# 8. Context priority hierarchy

## 8.1 The hierarchy

Priority is a property of a *slot/block*, not of a message. Ranked by `(authority, permanence, attention_weight)`.

| Tier | Rank | Content | Authority | Compactible | Placement |
|---|---|---|---|---|---|
| **T0 — Policy** | 1 | Base instructions, operating invariants, tool policy | Highest. Never contradicted. | Never | System head (Region 0) |
| **T1 — Identity & rules** | 2 | `agent_identity`, `project_rules`, `skill_buffer` | High, but *context* not *policy* → user/developer role | Never | Region 1, earliest slots |
| **T2 — Durable state** | 3 | `memory_ledger` (files touched, errors, decisions) | High. The only record of cross-turn state. | Never | Region 1 |
| **T3 — Orientation** | 4 | `workspace_map`, `environment` | Medium. High value, high volatility. | Never (recomputed instead) | Region 1 |
| **T4 — Volatile state** | 5 | `task_board`, `live_state` | Medium. Re-injected verbatim every step. | Never (re-injected) | Region 4 |
| **T5 — Checkpoint** | 6 | Compaction summary + work_state + recent-context + archive handle | **Lowest model-authored content we keep.** Explicitly marked as history, not instruction. | Replaced, never re-summarized verbatim | Region 2 |
| **T6 — Working set** | 7 | Recent user turns, assistant text, tool calls | Medium. Assistant *text* is the agent's own distillation and must survive. | Target, with per-part rules | Region 3 |
| **T7 — Tool payloads** | 8 | Tool result *bodies* | Lowest. Reconstructible in most cases. | Target, first and hardest | Region 3 |
| **T8 — Volatile tail** | 9 | `budget_notice`, background state, current prompt | High *recency*, low *durability*. | Never | Region 4 (last) |

**The rule that generates the hierarchy:** *authority* is orthogonal to *compactibility*. T0–T4 are never compacted but vary in how often they refresh; T5–T7 are compacted but must be marked as history; T8 is never compacted but is never cached. Collapsing these two axes — as our current single `role="system"` array does — is why nothing works well.

## 8.2 Priority within the working set (what survives a fold)

When the fold threshold is hit, the prefix is selected **not** by recency alone. Per-entry retention weight:

```
w(entry) = base_weight(category) × recency_factor(seq) × reference_factor(state) × error_bonus
```

| Component | Value |
|---|---|
| `base_weight(user)` | 4.0 |
| `base_weight(assistant_text)` | 3.5 — the agent's own distillation; Cortex: *"never touched by microcompaction"* |
| `base_weight(tool_call)` | 3.0 — the call is what makes the result meaningful |
| `base_weight(tool_result: REREADABLE)` | 1.0 |
| `base_weight(tool_result: COMPUTATIONAL)` | 1.4 |
| `base_weight(tool_result: NON_REPRODUCIBLE)` | 1.8 |
| `base_weight(tool_result: MUTATING)` | 2.6 — the receipt is the only record of what changed |
| `base_weight(state/internal)` | 0.0 — never selected, it is a slot |
| `recency_factor(seq)` | `1.0` for the newest quarter, linear to `0.5` at the cut point |
| `reference_factor` | `2.0` if referenced by an unfulfilled read-receipt; `1.0` otherwise |
| `error_bonus` | `×3.0` if `status == "error"` — TACO's Critical rule |

The fold then walks **backwards from the cut point**, accumulating weighted tokens against `keep_recent_tokens`, and takes whole *groups* (an assistant message plus all its tool results) so a call is never separated from its result.

**Why weighted and not plain-recency:** LongCodeArena shows bug localization is retrieval-bound (best retriever 0.33 MAP vs GPT-4 0.39). Blindly keeping the last N entries will keep six grep results and drop the one stack trace that explains the failure. `error_bonus` fixes that for a known fraction of a percent of tokens.

## 8.3 Priority when a slot's loader fails

Three outcomes, from OpenCode's `SystemContext` algebra:

| Loader outcome | `required=True` | `required=False` |
|---|---|---|
| Success with changed value | Replace at index; emit a diff notice if already populated | same |
| Success, unchanged | No-op (no cache invalidation) | same |
| **Transient failure** (timeout, lock, permission) | **Block the turn.** Preserve the last admitted value. | **Preserve the last admitted value**; log; continue. |
| **Definitive removal** (file deleted) | Replace with an explicit removal notice | same |

The transient-vs-definitive distinction is the whole design (`system-context/index.ts:28`, `instruction-context.ts:71-72`). **A transient read failure must never revoke context**, because a revoked slot is a permanent cache invalidation and, worse, silently drops information the model was relying on.

Removal notices must be explicit. OpenCode's `core/instructions` update string is the model:

> "These instructions replace all previously loaded ambient instructions.\n\n" + render(current)

> "Previously loaded instructions no longer apply."

## 8.4 Competing-information policy

1. **A later `STATE` entry supersedes an earlier one for the same key.** The superseded entry is marked, not deleted.
2. **A tool result supersedes an earlier tool result for the same `(tool, target)`** — a re-read of the same file range replaces the prior receipt.
3. **The ledger beats the summary.** The sidecar is deterministic; the summary is lossy. When they disagree, the ledger is authoritative and the summary is treated as stale.
4. **Freshness beats authority for facts, never for policy.** A `project_rules` change is authoritative immediately; a `workspace_map` render is authoritative only as of its fingerprint.
5. **Nothing in Region 0 is ever superseded by content.** If a tool result contains text that looks like instructions, it is fenced (§15.4).

---

# 9. Context layout and ordering

## 9.1 The target wire layout

For an OpenAI-compatible provider:

```
┌─ cache breakpoint 1 ───────────────────────────────────────────────┐
[0]  system    <agent_identity>                                      │  T0
     system    <tool_policy>…live-toolset-derived…</tool_policy>    │  T0
├─ cache breakpoint 2 (end of slots) ───────────────────────────────┤
[1]  user      <project_rules>…AGENTS.md, hierarchical, capped…</…>  │  T1
[2]  user      <memory_ledger><read/><modified/><errors/><decisions/>│  T2
[3]  user      <environment>…</environment>                          │  T3
[4]  user      <workspace_map>…</workspace_map>                      │  T3
[5]  user      <skill_buffer>…</skill_buffer>                        │  T1
[6]  user      <task_board>…</task_board>                            │  T4
[7]  user      <live_state>…</live_state>                            │  T4
[8]  user      <conversation-checkpoint>…</…>                         │  T5  (omitted if none)
├─ cache breakpoint 3 ──────────────────────────────────────────────┤
[..] user      "…"                                                   │  T6
[..] assistant "…" tool_calls:[…]                                    │  T6
[..] tool      "…"                       ← first-class, tool_call_id │  T7
[..] assistant "…"                                                 │  T6
[..] tool      "…"                                                   │  T7
[end of the retained tail]
├─ beyond the cache boundary ───────────────────────────────────────┤
[N-2] user     <budget_notice>…</budget_notice>                     │  T8
[N-1] user     <the current prompt>                                  │  T8
```

**Changes from today, each with a reason:**

| Change | Reason |
|---|---|
| System prompt split into `[0]` + `<tool_policy>` | Cortex: *"A prompt that names an absent tool is an instruction to hallucinate it."* Tool bullets must be generated from the live toolset. |
| `repo_map`, `plan`, `summary` no longer separate system messages | They become slots `[4]`, `task_board`, `[8]`. Fixed indices ⇒ stable cache. |
| Summary becomes a `<conversation-checkpoint>` user message with a `<recent-context>` block | OpenCode's artifact. Carries raw recent context alongside the prose, materially reducing prose-only summary loss. |
| `repo_map` injected even on the first turn | P11: orientation matters *most* on turn 1, which is exactly when we omit it. |
| `plan` folded into `task_board` | It is state, not policy, and it needs a fresh re-injection every turn. |
| `budget_notice` last, before the prompt | A tight constraint stated last, adjacent to what it constrains. Hard-capped at 256 tokens per Cortex's reasoning. |
| Tool results as first-class `toolResult` entries with `tool_call_id` | P2. pi's `role:"toolResult"`. Enables the four normalization passes. |

## 9.2 Within-slot ordering rules

1. **Slots: most stable first.** Cortex's rule, and the reason Anthropic's end-of-slots breakpoint can walk back ~20 content blocks to an earlier stable boundary.
2. **Keep the slot region under ~20 content blocks.** Beyond that, add an explicit breakpoint or merge slots — Anthropic's automatic lookback won't reach further.
3. **Ledger before workspace map.** The ledger is a few hundred tokens and uniquely answers "what happened"; the map is up to 4k and answers "where could it be." Lead with the cheap certain answer.
4. **Project rules before environment.** Codex's registration order does exactly this (`world_state.rs:147` before `:224`), and its snapshot confirms AGENTS.md precedes `<environment_context>`.
5. **In the ledger: decisions → files touched → errors → commands.** Decisions are highest-value, lowest-volume. Error strings must be verbatim (TACO: 96.0% critical-info preservation).

## 9.3 Why this layout, given the positional literature

- **Start = stable + high value.** Liu et al.: rerank to push relevant toward the start. LongLLMLingua: reordering helps *every* baseline. DPP bias: front-loading is +6pp and lowest volatility for small models; **LLAMA-3-3B's improved-prediction rate falls 42.0% → 11% when a block moves from prompt-start to message-end.** Qwen-1.5B strongly prefers early positions.
- **End = fresh.** Veseli et al.: past 50% window utilization the ranking becomes **last > middle > first.** CRE at 64K: 96% with the target at the end, 8% in the middle.
- **The middle is the cheapest real estate to waste.** P6 (duplicated tool catalogue) and P11 (a repo map nobody asked for) both land in the middle. Deleting them is free.
- **Audit the regime.** Veseli et al. make primacy conditional on staying below 50% of the window. §13.3 is the mechanism that keeps us there.

## 9.4 The positional probe — a cheap acceptance criterion

**Run this once, before shipping, then stop running it.** Take a fixed task. Relocate the single most important fact to (a) the start, (b) the middle, (c) the end of the assembled context. Measure pass/fail.

- Large spread → position is a live variable for your model and the §9.1 layout is load-bearing.
- Small spread → you have moved from "position tuning" to "structural discipline"; further ordering work is wasted.

A well-functioning policy should *narrow* that spread over time. That is a model-agnostic acceptance criterion for the whole system.

---

---

# 10. Context lifecycle

## 10.1 Operations

| Op | Trigger (automatic) | Trigger (explicit) | Effect |
|---|---|---|---|
| **Add** | new user message; tool result; background job completion; compaction entry; slot source change | `context.push(...)`; agent calls a loader tool | Append to the log; project into the right region |
| **Update** | slot fingerprint change; ledger delta | `context.update_slot(...)` | Replace at fixed index; emit a diff notice if previously populated |
| **Promote** | a folded summary contains a decision or an unclosed error | agent calls `context.promote(ref)` | Copy the entry's distilled form into `memory_ledger`; never into the transcript |
| **Demote** | a hot-zone tool result ages past the hot zone | — | Step down the degradation ladder (full → bookend → placeholder) |
| **Refresh** | per the slot's `RefreshPolicy` | `context.refresh(slot_name)` | Re-run the loader; replace if changed, no-op if not |
| **Invalidate** | definitive removal (file deleted, rule revoked) | `context.invalidate(slot_name)` | Replace with an explicit removal notice |
| **Summarize / Fold** | working-set tokens > `fold_threshold` | `context.fold(focus=…)` | Write a `compaction` entry; archive the raw prefix; emit a checkpoint |
| **Compact** (payload-level) | tool result past the degradation span | — | Bookend or placeholder; **never** delete the archive |
| **Evict** | ledger set exceeds cap (LRU on untouched paths) | — | Drop the least-recently-touched path, with a note |
| **Re-retrieve** | agent calls `recall(archive_id, query)` | `context.recall(...)` | Load archived raw content, append as a new entry with `recovered: True` |
| **Delete** | session deleted | `context.clear()` | The only true deletion |

## 10.2 The trigger table (event → operation)

| Event | Ops fired |
|---|---|
| **New user message** | Add(entry); Refresh(`project_rules`), Refresh(`environment`), Refresh(`task_board`); fold-check; fail-check |
| **Tool call emitted** | — (no context change; the call is a plan) |
| **Tool result received** | Add(entry) **already projected**; ledger-extract (read/modified/commands/errors); Refresh(`memory_ledger`); Refresh(`task_board`); demote-pass on the aging tail; ladder-step for out-of-zone results; fold-check; fail-check |
| **File mutation** | Add(`tool_result`, category=MUTATING); ledger-extract; Refresh(`workspace_map`) — **debounced**, this is the hot path; Refresh(`project_rules`) if the path is a rules file; `session_workspace.evict_file_cache(path)` (already correct) |
| **Git change observed** | Refresh(`environment`) with a branch/dirty diff notice; Refresh(`workspace_map`) debounced |
| **Task / state transition** | Refresh(`task_board`); when a todo leaves `pending` for `completed`, the ledger records the closure |
| **Error** | Add(entry, `status="error"`, `error_signature=…`); ledger-extract; Refresh(`memory_ledger`); ladder-step: **never bookend an error-bearing result**; fold-check |
| **Model response** | Add(assistant entry with `signature`); fold-check; fail-check; Refresh(`budget_notice`) |
| **Token threshold** (soft) | fold-check |
| **Context-window threshold** (hard) | fail-pass (emergency truncate) |
| **Provider context-overflow error** | overflow-recovery ladder (§11.5) |
| **Explicit agent action** | `context.fold(focus)`; `context.promote(ref)`; `context.recall(...)`; `context.refresh(slot)`; `context.reset()` |
| **Time / staleness** | per-slot `RefreshPolicy`; plus a **staleness sweep**: any slot whose fingerprint is older than `slot_ttl` is recomputed even if no event fired |

## 10.3 The staleness sweep — the piece we do not have

Today, staleness is four unrelated mechanisms and no epoch. The sweep is the unification:

```
on every turn boundary:
    for slot in registry:
        if slot.policy == IMMUTABLE: continue
        if slot.policy == ON_MUTATION and not mutations_this_turn: continue
        if slot.policy == ON_WAKE and not woken_this_turn: continue
        recompute_fingerprint(slot)
        if fingerprint != admitted_fingerprint(slot):
            reload(slot)  → replace at index, emit diff notice
        if age(admitted_at) > slot_ttl: reload(slot)   # catch missed events
```

Two properties this buys:

1. **Fingerprint-first, reload-second.** A reload that produces identical content is a no-op and costs **zero cache**. Cortex is explicit that slot updates are the only cheap cache lever: *"splitting them means only the changed slot forces a cache miss while the others remain cached."*
2. **TTL backstop.** Event-driven invalidation always has a miss case. A TTL guarantees eventual consistency with the filesystem even if a write notification is lost. Codex's `AgentsMdManager` has exactly this bug — it keys on two things and **editing `AGENTS.md` mid-session does not invalidate the cache** — which is a documented failure users hit.

**The `(mtime_ns, size)` fingerprint we already use in `session_workspace.py` is the right primitive.** Reuse it. It is the one genuinely good staleness mechanism we have.

## 10.4 The lifecycle state machine (per slot)

```
                  ┌──────────┐
                  │ ABSENT   │ slot declared, never populated
                  └────┬─────┘
                       │ first successful load
                       ▼
                  ┌──────────┐
      ┌───────────│  ADMITTED│◄──────┐ same fingerprint
      │           └────┬─────┘       │ (no cache cost)
      │                │             │
      │  changed value │             │ no-op reload
      │                ▼             │
      │           ┌──────────┐       │
      │  ┌────────► REPLACED ├───────┘
      │  │        └────┬─────┘
      │  │             │ definitive removal
      │  │             ▼
      │  │        ┌──────────┐
      │  └────────┤ REVOKED  │ re-loadable, renders a removal notice
      │           └──────────┘
      │
      │  transient failure
      ▼
 ┌────────────┐
 │ STALE      │ keeps the last admitted value; a warning rides in the
 │ (admitted  │ next turn's <budget_notice> so the model knows
 │  retained) │ something may be out of date
 └────────────┘
```

**`STALE` is the state that OpenCode gets right and that most systems get wrong.** A transient failure must not revoke. And it should be *visible to the model* — a silent stale value is worse than an honest one.

## 10.5 The working-set entry state machine

```
     ┌──────────┐
     │   NEW    │  appended to the log, full fidelity
     └────┬─────┘
          │ age / distance from tail
          ▼
     ┌──────────┐   user / assistant_text / tool_call  → stays here forever
     │   HOT    │
     └────┬─────┘
          │ crosses hot_zone boundary
          ▼
     ┌──────────┐
     │ DEGRADED │  tool_result bodies: head+tail bookend,
     │          │  shrinking linearly across the degradation span
     └────┬─────┘
          │ crosses degradation span
          ▼
     ┌──────────┐   REREADABLE  → placeholder (re-run is cheap)
     │ PLACEHLD │   COMPUTATIONAL→ placeholder + archive path
     │          │   NON_REPROD. → placeholder + archive path (required)
     │          │   EPHEMERAL   → cleared
     │          │   MUTATING    → receipt retained (never cleared)
     │          │   error       → NEVER leaves this state
     └────┬─────┘
          │ fold threshold crossed
          ▼
     ┌──────────┐  summary + work_state + recent-context + archive_id
     │  FOLDED  │  raw prefix archived; entry marked superseded_by
     └────┬─────┘
          │ recall(archive_id, query)
          ▼
     ┌──────────┐  new entry with recovered=True, full fidelity, region 3 tail
     │ RECOVERED│
     └──────────┘
```

---

# 11. Smart-compaction architecture

## 11.1 Tiering — the most important structural decision

Every serious system converges on graduated degradation rather than a single cliff, because a single cliff destroys exactly the information the summarizer needs to make a good decision. Cortex's rationale is the sharpest statement:

> **"The agent's own text responses are never touched by microcompaction. Only `tool_result` content blocks are candidates. This means that research findings, analysis, and conclusions the agent has already articulated in its own words survive regardless of what happens to the raw tool output."**

Our five tiers:

| Tier | Cost | When | Target |
|---|---|---|---|
| **T0 — Ladder** (payload degradation) | Zero LLM, zero cache impact | Every call, zone-based | Tool result *bodies* |
| **T1 — Dedupe** | Zero LLM | Every call | Duplicate re-reads, duplicate command runs |
| **T2 — Fold** (prefix summarization) | 1 LLM call, blocking | Soft threshold | Working-set prefix |
| **T3 — Degrade** (whole-turn drop) | Zero LLM | Hard threshold | Oldest whole turns |
| **T4 — Recover** | 1 LLM call, on demand | Model asks | Archived raw content |

**T0 before T2, always.** JetBrains (NeurIPS 2025) measured that simple observation masking matches LLM summarization at zero cost for SE agents, cutting cost ~50% with no performance degradation — **provided the masking is graduated, not all-or-nothing.**

## 11.2 T0 — The tool-result ladder

Zones by **token distance from the end of the working set**, not by percentage thresholds (Cortex; better because it scales to any window):

```
hot_zone_tokens      = max(16_000, W * 0.05)
degradation_span     = W * 0.40
bookend_max_chars    = 2_000     # at the hot-zone boundary
bookend_min_chars    = 256       # at the far end
```

| Distance from end | REREADABLE | COMPUTATIONAL | NON_REPRODUCIBLE | EPHEMERAL | MUTATING | any `status="error"` |
|---|---|---|---|---|---|---|
| ≤ hot zone | full | full | full | full | full | full + **no trim marker** |
| ≤ hot + span | bookend (shrinking) | bookend + archive | bookend + archive | bookend | receipt only | **full** |
| > hot + span | placeholder | placeholder + archive | placeholder + archive | cleared | receipt | **full** |

Cortex's coverage table, which we adopt:

| Window | Hot zone | Degradation span | Still bookended | % of window |
|---|---|---|---|---|
| 32k | 16 000 | 12 800 | 28 800 | 90% |
| 200k | 16 000 | 80 000 | 96 000 | 48% |
| 1M | 50 000 | 400 000 | 450 000 | 45% |

Beyond-span placeholder preserves a breadcrumb so the agent doesn't redo work:

```
[Tool result trimmed -- WebFetch: "context compaction techniques 2026" -- see assistant response below for findings]
```

**Three rules that are not in Cortex but are in the evidence:**

1. **Errors never degrade.** TACO: observations with explicit error/failure signals are Critical and pass through unmodified. trimout: errors ≤500 lines pass through entirely; >500 lines → head/tail + up to 30 extracted error lines. Our current P5 does the opposite.
2. **Deterministic error-signal detection**, not model judgement: non-zero exit code, `Traceback`, `FAILED`, `Error:`, `error TS\d+`, `AssertionError`, `Exception`, `^\s*E\s{3}\d+`, `✗`, `npm ERR!`. When detected → error lane, extract up to 30 error lines into the retained portion.
3. **Per-tool budgets on the ladder** keyed on signal density. `bash` gets 1 875 tokens (7 500/4); `grep`/`file_read` get the full 6 250 (25 000/4); `webfetch` gets 4 000. Cortex: *"bash output is verbose with low signal density, so it's capped tighter."*

**T0 is where the tokens are.** Our current worst case in the dispatched array is 6 × 10 000 chars for the newest tools plus 1 000 chars for everything older. Cortex's ladder keeps roughly the same total but distributes it by value.

## 11.3 T1 — Deduplication (highest ROI per token, currently absent)

Cline's `contextHistoryUpdates` replaces a re-read file with a **`[DUPLICATE FILE READ]` notice** at send time. We already short-circuit the `file_read` *tool* via `session_workspace.py`, but the **digest/receipt still enters context** and the model still pays for it.

| Duplicate type | Detection | Replacement |
|---|---|---|
| Same file, overlapping ranges | `(sha256, line_range)` | `[Re-read of {path} lines {a}-{b}; unchanged since the earlier read at {ts}]` — ~24 tokens |
| Same command, same cwd | `(normalized_cmd, cwd)` | `[Re-ran {cmd}; identical result at {ts}]` |
| Same tool + same args | `(tool_name, canonical_args)` | `[Repeated {tool} call; see earlier result]` |
| Superseded file state | `(path, sha_before != sha_after)` | Replace every earlier receipt for that path |

The last row is the one that matters most and is the most commonly missed: **after a `file_edit`, every earlier `file_read` of that file is stale.** Today nothing tells the model. A stale read in context is worse than no read — the model will quote it.

## 11.4 T2 — The fold

### Trigger

```
fold if  working_set_tokens + fixed_prefix_tokens + cache_read_tokens > W - reserve
```

where `reserve = max(max_output_tokens, 16_384)` and `cache_read` **counts** (pi's `isContextOverflow` uses `input + cacheRead`; cache reads occupy the window).

Plus a **hard cap independent of the fold budget**, per Codex:

```
fail_threshold = W * effective_context_window_percent / 100     # the model's real wall
fold if (working_set_tokens + fixed) > min(fold_threshold, fail_threshold)
```

This is Codex's two-limit `min()`. It guarantees we never aim at 70% of a window that is actually 20% of the model's real window.

### Cut-point selection

pi's `findCutPoint`, verbatim in behaviour:

1. **Valid cut points** are `user` and `assistant` entries only. **Never a `tool_result`** — you cannot split an assistant's tool batch.
2. Walk backwards from the end accumulating §8.2 weighted tokens until `>= keep_recent_tokens`.
3. **Snap forward** to the nearest valid cut point ≥ that index.
4. If the cut lands mid-turn, `is_split_turn = True` and a **second summary** is generated for the turn prefix, with `max_tokens = min(0.5 * reserve, model.maxTokens)`.
5. Never cut immediately after a `compaction` entry.

`keep_recent_tokens` should be `min(20_000, W // 8)` — pi's 20 000 default, scaled down for small windows. For a 32k window that is 4 000, which is right: keeping 20 000 of 32 000 is not a tail, it's the whole budget.

### What the fold produces

**A structured response, not prose.** The summarizer returns JSON; the structured fields merge into the ledger, the prose becomes the summary.

```jsonc
{
  "objective":   "…",                                  // ≤2 sentences
  "constraints": ["…"],
  "completed":   ["…"],
  "active":      ["…"],
  "blocked":     ["…"],
  "next_move":   ["…"],                                 // ≤2 items
  "decisions":   ["…"],                                 // → ledger.decisions (capped 12)
  "open_threads":["…"],                                 // → ledger.open_threads (capped 8)
  "blocked_on":  null,                                  // → ledger.blocked_on
  "files":       { "read": ["…"], "modified": ["…"] },  // cross-checked against our extractor
  "errors":      ["exact string"],                       // → ledger.failures
  "summary_md":  "…markdown narrative for the model…"
}
```

**Why structured:** our summarizer currently returns prose only, and the summarizer is the *only* component that knows what mattered. A structured contract turns a lossy artifact into a **lossless state delta** plus a lossy narrative. The narrative degrades across generations; the ledger does not.

### The fold prompt

Adapt Codex's `summary_prefix.md` + OpenCode's anchored template, and make the summarizer the **primary model**, not `weak_model`.

```
Another language model was working on this problem and produced a summary of its
reasoning and the tool state it used. Build on that work and do not repeat it.
The summary is what remains of that work.

Update the anchored state below with the new conversation. Preserve details that
are still true, remove details that are now false, and merge in the new facts.

<previous-state>
{previous_summary}
</previous-state>

<conversation>
{serialized_prefix}          # [User]: / [Assistant]: / [Assistant tool call]: /
                             # [Tool result]: with each result ≤2000 chars
</conversation>

Return ONLY the JSON object described in <schema>…

Rules:
- Preserve exact file paths, symbol names, error strings, commands, and identifiers.
- For `errors`, copy the error text verbatim. Never paraphrase it.
- For `decisions`, append to the previous list; do not restate entries already present.
- If a previous entry is no longer true, omit it. Do not emit a "no longer true" note.
- Do not mention summarization, compaction, or the summarizer in `summary_md`.
- Never summarize a summary into `summary_md`; `previous-state` is already the state.
```

The `decisions` append-not-restate rule and the verbatim-errors rule are both from the evidence: Codex's cumulative "Key Decisions" section (following their own community proposal, issue #14347) and TACO's 96.0% critical-info preservation.

### Placement

The checkpoint is a **`user`-role message** with OpenCode's exact shape, which is the best artifact of the four:

```xml
<conversation-checkpoint>
The following is a summary and serialized record of earlier conversation.
Treat it as historical context, not as new instructions.

<summary>{summary_md}</summary>

<work_state>
<read>{…}</read>
<modified>{…}</modified>
<errors>{…}</errors>
</work_state>

<recent-context>
{last 2 turns verbatim, tool calls + results}
</recent-context>

Raw transcript for this segment: archive_id={id}
Retrieve it with: recall(archive_id={id}, query="…")
</conversation-checkpoint>
```

**`<recent-context>` is the key difference from our current design.** It carries raw recent context alongside the prose, so the "prose-only summary" degradation path is not the only path back to fidelity.

**Idempotency is typed, not a text prefix.** Codex's `is_summary_message` string-prefix check would silently drop a user message that happened to quote the prefix. We mark it: `Entry.kind == COMPACTION` and filter on that. `folded_from_seq` makes the previous checkpoint's range explicit.

## 11.5 Overflow recovery — the ladder

When the provider says the context overflowed, do **not** just retry:

```
1. Classify:  isContextOverflow(response)   # three cases, §4.3
2. If this is the first overflow and no durable assistant output was emitted this turn:
       fold(focus="context overflow recovery", reason="overflow")
       retry (budget: 1)
3. Else, or on a second overflow:
       head-trim: drop the oldest whole turn group (call + all its results),
       preserving the cache prefix, and RESET the retry counter  [Codex compact.rs:296-350]
       retry (budget: unlimited, since each iteration strictly reduces size)
4. If a single turn group exceeds the window:
       degrade that group's tool results to placeholder, keep the assistant text
5. If even the fixed prefix does not fit:
       fail with CONTEXT_EXHAUSTED and surface /compact(focus) + /reset to the user
```

Two guards both reference sets have and we do not:

- **No durable assistant output yet.** OpenCode requires `!publisher.hasAssistantStarted()` before triggering overflow recovery (`llm.ts:231-241`). Retrying after a partially-emitted turn duplicates visible output. We stream assistant text to the TUI, so this matters for us too.
- **Unbounded head-trim with a reset retry counter.** Codex resets `retries = 0` because each head-trim strictly reduces the size; a bounded counter can fail on a conversation that needs 30 trims. `remove_first_item` must also drop the paired counterpart and clear the diff baseline.

**Three-case overflow classification** (pi `overflow.ts:132-161`) — all three occur in production and only the first is well-known:

1. Error-string patterns (`context_length_exceeded`, `maximum context length`, `too many tokens`, `prompt is too long`, `input length exceeds`, `context window` …), with **exclusions** for `ThrottlingException: Too many tokens, please wait`.
2. **Silent overflow** — `stopReason == "stop"` but `input + cacheRead > window`. z.ai and others.
3. **Length-stop overflow** — `stopReason == "length"` and `output == 0` and `input + cacheRead >= 0.99·window`. The server truncated the input to make room for output and left nothing.

## 11.6 Lossless vs lossy — where each belongs

| Content | Approach | Why |
|---|---|---|
| Tool result bodies | **Lossless up to a token cap, then lossy-but-reversible** | DTOC: reversibility is the whole mechanism (0.0 re-reads vs 4.2) |
| Assistant text | **Never lossy** | Cortex: it is the agent's own distillation |
| User messages | **Never lossy in the retained tail; verbatim in the summary** | Intent is the highest-value, lowest-recoverability content |
| Tool calls | **Never lossy** | A result without its call is meaningless |
| Tool-call arguments | **Never lossy for mutating tools** | The argument *is* the change record |
| Working-set prefix | **Lossy + reversible** | ACM: `summary_{id}.json` + `query_memory` |
| The ledger | **Never lossy** | Deterministic extraction, not summarization |
| `AGENTS.md` / rules | **Never lossy** | Slot; Claude Code documents that `paths:`-scoped rules are lost on compaction, a known user complaint |
| Repo map | **Lossy by design** | It is a ranking; re-derivable |
| Reasoning blocks | **Opaque replay, never summarized** | pi: `thinkingSignature`; Codex: `encrypted_content`; Anthropic: `signature` |

**The general rule: the lossy path is a *cache*, and the lossless path is the *truth*.** Every lossy artifact must have a lossless fallback reachable in one tool call, and the model must be told it exists.

## 11.7 Repeated-compaction degradation

Four independent mitigations, in order of importance:

1. **The ledger does not degrade.** It is deterministic and cumulative. Decisions, files touched, and error signatures survive arbitrarily many folds. This is the primary answer, and it is why the ledger is a slot.
2. **Anchor the fold, do not chain it.** Feed `<previous-state>` (already the distilled state) rather than re-reading the whole prior summary chain. OpenCode's anchored variant and Codex's iterative `UPDATE` prompt both do this. Feeding raw prose is what produces "summarizing summaries."
3. **Append, don't restate, for decisions.** A "Key Decisions (Cumulative)" section carried forward across compactions creates a rolling log that compounds rather than decays.
4. **Make a fresh session a first-class escape hatch.** Anthropic: *"the model is at its least intelligent point when compacting"*; **"new task → new session"**; **"`/clear` beats `/compact` when you can write the brief yourself, because the resulting context is what you decided was relevant."** After N folds, offer `/reset` and pre-fill it from the ledger. Track `fold_generation` and surface the warning:

> "This conversation has been compacted N times. Longer threads and repeated compaction reduce accuracy. Consider starting a new task — your decisions and file state are already saved."

## 11.8 Non-blocking digestion

A fold costs one LLM call and a full turn of latency. Cortex's answer: run the observer/fold **asynchronously** whenever the trigger is soft, and only force a synchronous fold when the *hard* threshold is crossed. `digestIdle()` runs deferred work **outside** a prompt, serialized through the loop gate so it can never race a running turn, with a **bounded timeout** (60s): on timeout, release the gate and leave the request in flight. `nonBlocking: true` disables every synchronous LLM call in the transform hook; emergency truncation remains the only blocking path.

We implement this as: **fold requests are enqueued during the current turn and awaited at the next turn boundary.** If the next boundary arrives before the fold completes, we proceed with the ladder-only context (T0 + T3) and the fold lands for the turn after. This removes the compaction latency spike from the critical path without weakening the guarantees, because T0/T3 are always available as a fallback.

---

# 12. Refresh and invalidation strategy

## 12.1 Automatic vs agent-triggered

| Refresh | Automatic | Agent-triggered | Why |
|---|---|---|---|
| `agent_identity` | on mode change | — | Must be authoritative |
| `project_rules` | **on mutation + TTL sweep** | `refresh("project_rules")` | Editing AGENTS.md mid-session must land. Codex's `AgentsMdManager` does not — a documented bug. |
| `memory_ledger` | **on every mutation and error** | `context.promote(ref)` | The ledger is durable state; it must never lag |
| `environment` | on wake, on git change | `refresh("environment")` | Cwd and date are cheap; churn matters for cache |
| `workspace_map` | **on mutation, debounced 2s, and on TTL 120s** | `refresh("workspace_map")` | Writes happen constantly; a full tree-sitter pass cannot. A 120s TTL bounds staleness without per-write cost. |
| `tool_policy` | on toolset change | — | Must be authoritative; Cortex's hallucinated-tool lesson |
| `task_board` | **per step** | — | Volatile by definition; cheap because it is small |
| `live_state` | **per step** | — | Same |
| `budget_notice` | per step, **only if the number changed by ≥5% of the window** | — | Injecting a nearly-identical block every step wastes ~64 tokens and breaks the cached tail. **Emit on threshold crossings, not continuously.** |
| `skill_buffer` | on load/unload | `load_skill(name)` | Claude Code: skill bodies cap at 5 000/skill, 25 000 total, **oldest dropped first, truncation keeps the head** |

## 12.2 The invalidation matrix

| Event | Evicts / invalidates | Not invalidated |
|---|---|---|
| `file_write`/`edit`/`apply_patch`/`delete` on path P | read cache for P (already correct), all receipts for P in the working set, the ledger's `sha` for P | the repo map (debounced), other paths' receipts |
| `file_write` on a rules file | `project_rules` | everything else |
| Git branch switch / merge | `environment`, `workspace_map` | the ledger, the working set |
| Toolset change | `tool_policy`, all cached prefixes, the whole prompt cache | the ledger |
| Model switch | reasoning signatures (dropped by the `isSameModel` gate), `tool_policy` if provider-specific, `budget_notice` | everything else |
| Fold | the folded prefix (marked `superseded_by`), all ladder state | **all slots** |
| `reset` | the entire working set and checkpoint | **all slots**, the ledger, archives |

The row that matters most: **a fold invalidates the working set and nothing else.** That is the structural property we do not have today, where compaction rewrites the file that holds `summary` and the history together.

## 12.3 Fingerprints

| Slot | Fingerprint over | Cost |
|---|---|---|
| `project_rules` | `(path, mtime_ns, size)` for each discovered rules file | ~5 `stat` calls |
| `environment` | `(cwd, branch, HEAD[:8], dirty_count, date)` | 1 subprocess + 1 stat |
| `workspace_map` | `md5(rel|mtime_ns|size for all tracked files) + HEAD` — **this is our existing `RepoMap._snapshot()`, currently dead code** | N stats, debounced |
| `memory_ledger` | hash of the last appended delta | free |
| `tool_policy` | hash of the sorted tool names + their schema hashes | free |
| `task_board` | hash of `(todo_state.snapshot(), run_state.status)` | free |
| `budget_notice` | `(percent // 5)` bucketed | free |

`RepoMap._snapshot()` existing-but-unwired is the clearest evidence of an interrupted design. **Wire it.**

---

# 13. Model-aware context strategy

## 13.1 The decision

**Universal canonical representation; model-specific renderers; model-aware budgets and policies; no model-aware data structures.**

| Concern | Universal? | Rationale |
|---|---|---|
| The entry log | **Universal** | Truth. Never model-dependent. |
| Slot registry and specs | **Universal** | The *set* of slots is the same for every model. |
| Slot *role* | **Universal** | `SYSTEM`/`DEV`/`USER`/`EXTERNAL` is a policy statement, not a wire format. |
| Slot *order* | **Universal** | Stability ordering is a cache property, not a model property. |
| Budgets, thresholds, ladder parameters | **Per model** | §13.3 |
| Fragment *rendering* (tags, escaping, merging) | **Per model** | Small models need more explicit structure; §13.4 |
| Wire shape | **Per model** | `ProviderAdapter.to_wire()` |
| Tool-result role | **Per model** | `role:"tool"` vs `role:"user"` + prefix |
| Reasoning replay | **Per model** | `isSameModel` gate |
| Instruction verbosity | **Per model** | But table-driven, not substring-matched |

**Rationale for universal order:** mixing per-model ordering would mean the cache prefix changes whenever the user switches models mid-session, destroying the one lever that makes long context affordable. Order is cheap to keep universal; budgets are not.

## 13.2 The tier table

Derived from cost and capability in our own `zenith_catalog.json`, plus release recency — OpenCode's `SMALL_MODEL_RE = /\b(nano|flash|lite|mini|haiku|small|fast)\b/` (`catalog.ts:294`) is a reasonable floor, not the whole rule.

| | `frontier` | `balanced` | `efficient` | `unknown` |
|---|---|---|---|---|
| Examples | Opus/Sonnet 4.5+, GPT-5, Gemini 3 Pro | Sonnet 4, GPT-4.1, Qwen 235B | Flash/Haiku/Mini/nano, Qwen 7–14B, Llama 8B | catalog miss |
| `tool_policy` verbosity | normal | normal | **expanded** | normal |
| Instruction budget | 12% of W | 14% | **18%** | 14% |
| Repo map budget | `min(W//8, 4096)` | `min(W//8, 4096)` | `min(W//8, 2048)` | `min(W//8, 2048)` |
| `fold_threshold` | `0.55·W` | `0.50·W` | **`0.35·W`** | `0.45·W` |
| `fail_threshold` | `0.90·W` | `0.90·W` | **`0.80·W`** | `0.85·W` |
| `keep_recent` | `min(20_000, W//8)` | `min(16_000, W//8)` | `min(8_000, W//10)` | `min(16_000, W//8)` |
| Hot zone | `max(16k, 0.05W)` | `max(12k, 0.05W)` | `max(6k, 0.06W)` | `max(12k, 0.05W)` |
| Ledger verbosity | full | full | **full + expanded `work_state`** | full |
| Fold summarizer model | primary | primary | primary | primary |

**Why the fold threshold drops to 0.35 for efficient models.** Two independent sources. First, the scaling law: `acc(n) = a − b·log₂n` with `b ∈ [0.018, 0.031]`, giving `n* = 2^((a−α)/b)` — a representative model hits an 80% floor at **≈67K tokens.** 0.35 × 128k = 44 800. Second, NoLiMa: **at 32K, 11 of 13 models drop below 50% of their short-context baseline**, and GPT-4o falls 99.3% → 69.7%. Vulnerability scales with how much you fill.

**Why the instruction budget *rises* for efficient models** (counter-intuitive, so justify it): the budget is the share of the window for T0/T1, and its purpose is to make the fixed contract explicit rather than implicit. Small models follow *more* explicit contracts. AgentFloor's 18-constraint finding is the counterweight: *"no model reached 100% on any format"* at 18 simultaneous constraints — but that is a *comprehensiveness* failure, not a *format* failure, and increasing the budget past a point makes it worse. 18% is a modest increase from ~14%, not a doubling.

**And the opposite change we should also make:** for efficient models, *expand the ledger and reduce the transcript.* LongCodeArena: tree-adjacent context gives CodeLlama-7B **+53% in-project EM**. ACM's 4B ablation: 4B had consumed only 23K of 131K when it gave up — it was not context-starved. A model that lacks capacity is helped more by **structure** than by **volume**.

## 13.3 Window resolution and the two-limit rule

```
resolved_window       = min(catalog_window, config.max_context_tokens)
effective_window      = resolved_window * effective_context_window_percent / 100
reserve               = max(max_output_tokens, 16_384)
fold_threshold        = min(tier_fold_ratio * resolved_window, effective_window)
fail_threshold        = min(tier_fail_ratio   * resolved_window, effective_window)
```

Two rules:

1. **Exactly one clamp, with provenance logged.** Cline's bug (#9181) came from `max(window − 40_000, window × 0.8)` then `min(..., threshold × window)` — stacked thresholds amplify a misdetected window. Log `context_window_source` on every request.
2. **If the source is `default` or `user`, be conservative.** On a misdetected window the safe direction is to compact *early*, because early compaction costs tokens while late compaction costs a failed turn. When `window_source == "default"`, multiply `fold_threshold` by 0.7. When it is `user`, honour the user's value — they told us.

**Never `context == 0` → "compaction disabled."** OpenCode does this (`compaction.ts:173, 228`), and a model missing from the catalog silently loses auto-compaction. Our fallback must be a *conservative estimate*, not a disable.

## 13.4 Model-specific rendering, minimally

**Do** adopt a small capability-driven variation set. **Do not** adopt OpenCode's 9 hand-written provider prompts selected by `api.id.includes(...)` — that couples behaviour to a naming convention we do not control, and two of the nine files (`copilot-gpt-5.txt` at 14 KB, `plan-reminder-anthropic.txt` at 4 KB) are dead in their own repo.

| Variation | Gate | Rationale |
|---|---|---|
| `tool_policy` expanded for `efficient` | tier | Explicit, enumerated contracts |
| Tool result role | `tool_result_role` capability | Some OpenAI-compatible providers reject `role:"tool"`; some small local models mishandle it |
| Reasoning replay | `supports_reasoning_replay` + `isSameModel` | pi's gate; encrypted payloads are model-specific |
| Instruction max tokens | hard cap | §5.2 token elasticity — a too-small cap is *worse than none* |
| `tool_call_id` sanitization | per-adapter | OpenAI Responses ids can be 450+ chars with `|`; Anthropic needs `^[a-zA-Z0-9_-]{1,64}$` |
| Images in tool results | `supports_images_in_tool_result` | OpenCode's allowlist; move media to a trailing user message when unsupported |
| Extra synthetic assistant bridge | `requires_assistant_after_tool_result` | Some models reject a tool result not followed by an assistant turn |

**On XML tags:** use them for parseability and injection resistance, not reasoning quality. The Delimiter Hypothesis found **no meaningful difference** between XML/Markdown/JSON on 3 of 4 models, and a **reproducible 20% prompt-injection failure rate for MiniMax on Markdown** that XML and JSON both blocked. So: **XML by default, JSON for the fold response, and always fence untrusted content in `<external_*>`.** Never add tags "to help the model think."

## 13.5 The highest-value small-model change is not a prompt

**PA-Tool: renaming tool schemas to match pretraining priors gives Llama3.1-8B +9.6pp on multi-tool selection, beating Claude Sonnet 4.5, at zero token cost.** The mechanism: use **logprob peakedness** of the tool name under the model as a familiarity signal; rename where peakedness is low.

Our names are already conventional (`file_read`, `file_write`, `glob`, `grep`, `bash`), which is most of the battle. Two cheap additions:

1. **Aliases.** A tool may declare `aliases: ["read_file", "fs_read"]`; the adapter exposes the alias the model's logprobs prefer. Zero cost, additive, reversible.
2. **A one-time peakedness probe** per `(model, tool_name)` at provider-validation time: send a 1-token completion per tool name and measure the peak. Cache the result per model. ~30 calls once per model, and it tells us which names the model does not know.

**8B multi-agent with a thinking orchestrator matches 32B single-agent, using 476 tool calls vs 698 (−32%).** The transferable rule from that paper is specific: **thinking belongs at the orchestrator, not the sub-agents** — with thinking on, sub-agent size is irrelevant (23.0/23.0/23.6 for 1.7B/8B/32B); with thinking off, sub-agent size matters, and **32B-orchestrator + 8B-sub-agents (21.2) lost to both 1.7B (22.4) and 32B (23.6).** Check what our specialists do.

## 13.6 Multi-agent: isolation vs shared context

The evidence is model-dependent (arXiv 2606.29718):

- **Strong-agentic backbone** (Qwen3.5-397B): sub-agent context **isolation** wins.
- **Weak backbone** (GLM-4.7): plain **keep-latest + summary** wins; FoldAgent is near-worst.

Our `CrewmateLoop` creates a child session with a **fresh `ContextManager` and `history=[]`**, and `scout.run_crewmate` applies `min(config.max_context_tokens, task.max_context_tokens)` with `CREWMATE_CONTEXT_BUDGET_TOKENS = 64_000`. That is already full isolation. The missing piece is that the child returns only a summary, and that summary should be a **structured result** (`delegation/agent_result.py`) whose key fields merge into the parent's ledger, not prose appended to the parent's transcript.

---

---

# 14. Token optimization strategy

## 14.1 Where the tokens actually go

Estimated for a typical BUILD turn at a 128k window, today vs. proposed:

| Region | Today | Proposed | Δ |
|---|---|---|---|
| System prompt (with duplicated tool catalogue) | ~1 700 | ~1 200 (tool bullets from live toolset, no duplication) | **−500** |
| Repo map | 1 024 | up to 4 096 | **+3 072** |
| Plan | ~800 | folded into `task_board` (~400) | **−400** |
| Summary | ~1 200 | checkpoint incl. `<work_state>` ~900 + `<recent-context>` 1 500 | +300 |
| Working set (transcript) | ~48 000 | ~34 000 (ladder + dedupe) | **−14 000** |
| Tool schemas (currently **0**) | 0 (uncounted) | ~4 000 | +4 000 (honest) |
| Tail | ~1 500 | ~1 300 | −200 |
| **Total** | **~54 224** | **~47 396** | **−6 828 counted, −10 828 real** |

The point of the table: **after fixing P1, our real occupancy is ~10 800 tokens higher than we think, and the ladder plus dedupe gives back ~14 000.** The repo map increase is a *deliberate spend* against LongCodeArena's +53%.

## 14.2 The token-counting fix (P1 + the estimator)

Adopt pi's hybrid, verbatim in structure:

```python
@dataclass(frozen=True, slots=True)
class ContextUsage:
    tokens: int
    source: Literal["provider", "estimated"]
    anchor_seq: int | None      # which assistant entry's usage we used
    breakdown: TokenBreakdown


def measure(ctx: RenderedContext, profile: ModelProfile) -> ContextUsage:
    # 1. find the newest assistant entry whose usage describes the current prefix
    anchor = None
    latest_prefix_ts = -inf
    for i, e in enumerate(ctx.working_set):
        if (e.kind is ASSISTANT and e.usage_total > 0 and e.ts >= latest_prefix_ts
                and e.status not in ("aborted", "error")):
            anchor = (e.usage, i)
        latest_prefix_ts = max(latest_prefix_ts, e.ts)

    # 2. no anchor → estimate everything
    if anchor is None:
        return ContextUsage(estimate_all(ctx, profile), "estimated", None, breakdown(ctx, profile))

    # 3. anchor → provider-reported for the prefix, heuristic for the tail,
    #    PLUS any tool definitions added after the anchor
    usage, idx = anchor
    tail_tokens = sum(entry_tokens(ctx.working_set[j], profile)
                      for j in range(idx + 1, len(ctx.working_set)))
    added_tool_names = {e.tool_name for e in ctx.working_set[idx+1:]
                        if e.kind is TOOL_RESULT and e.adds_tool}
    added_tool_tokens = sum(estimate_text_tokens(json.dumps(profile.tool_schema(n)))
                            for n in added_tool_names)
    return ContextUsage(usage.input + usage.output + usage.cache_read + usage.cache_write
                        + tail_tokens + added_tool_tokens, "provider", idx, ...)
```

The `e.ts >= latest_prefix_ts` guard is the load-bearing detail: **a checkpoint inserted after a response carries a newer timestamp, so that response's usage cannot describe the current prefix.** Without it, folding and then measuring reuses a stale number.

**Keep our real tokenizer** (`token_counter.py` already resolves `cl100k_base` / tiktoken correctly). pi's chars/4 is *worse* than what we have. Adopt the *architecture* of the hybrid estimator, not its heuristic.

## 14.3 Cache strategy

Three breakpoints. Anthropic's prefix order is `tools → system → messages`:

| BP | Anchor | Rationale |
|---|---|---|
| 1 | End of the system head (after `tool_policy`) | Stable for the life of the session unless the toolset changes |
| 2 | End of the slot region | Cortex; the walk-back target when a late slot changes |
| 3 | End of the stable working set (before the volatile tail) | The tail never enters the cached prefix |

Rules:

- **Cap the slot region at ~20 content blocks.** Past that, Anthropic's ~20-block automatic lookback can't reach a stable boundary.
- **Order slots by stability.** The repo map is the most volatile slot; `agent_identity` the least.
- **Summarization calls set `cache_retention="none"` and a throwaway session id.** pi does exactly this (`compaction.ts:118-138`): *"Summaries are standalone requests, so isolate routing and avoid cache writes that cannot be reused."* Our `_cache_prefix_for` currently returns `[]` because nothing ever sets `cache_control`; at minimum we should isolate the summarizer.
- **T0 is cache-aware.** Cortex gates the ladder on whether the cache has actually expired:

| Provider | Short TTL | Long TTL |
|---|---|---|
| Anthropic / Bedrock | 5 min | 1 h |
| OpenAI | 10 min | 24 h |
| Google / Mistral / Azure | no caching — ladder runs freely | no caching |

  Cortex's own cost model (200k window, 34 ticks) is the honest bit: **with 90% cache discount, microcompaction is ~19% *more* expensive** due to invalidation at threshold crossings; with no caching it is ~18% cheaper. They chose uniformity, buying ~12 extra ticks of headroom. **Make this an explicit config flag (`ladder.cache_aware: bool`, default `true`) and log the resulting trade-off.**

## 14.4 Per-tool budgets by signal density

```python
TOOL_BUDGET_TOKENS: dict[ToolCategory, int] = {
    EPHEMERAL:          1_000,
    REREADABLE:         6_250,   # 25_000/4 — dense, keep more
    MUTATING:             512,   # receipts only
    COMPUTATIONAL:      6_250,
    NON_REPRODUCIBLE:   4_000,   # archive always
}
TOOL_BUDGET_OVERRIDE: dict[str, int] = {
    "bash":        1_875,   # 7_500/4 — verbose, low signal density (Cortex)
    "job_output":  1_000,
    "webfetch":    4_000,
    "websearch":   5_000,
    "file_read":  10_000,   # dense code, and ranges are referenceable
    "grep":        6_250,
    "glob":        1_500,
    "file_write":    400, "file_edit": 400, "apply_patch": 1_200, "file_delete": 300,
    "explore":     8_000,   # high value
    "todo":          512,
}
```

Cortex's skip set is a good default for what bypasses the ladder entirely: `Read` (already on disk, re-readable with offset/limit), `Edit`/`Write` (short receipt), `Glob` (capped at 100 paths).

## 14.5 Error-aware retention (TACO's Critical rule)

```python
ERROR_SIGNALS = re.compile(
    r"(Traceback \(most recent call last\)|"
    r"\b(?:AssertionError|Exception|Error)\b|"
    r"error TS\d{4}|"
    r"^\s*E\s{3}\d+|"
    r"npm ERR!|"
    r"\bFAILED\b|\bfailed\b|"
    r"✗|✘|❌|"
    r"\bexit(?:ed with (?:code|status))?\s*[:=]?\s*[1-9])",
    re.MULTILINE,
)


def extract_error_lines(text: str, limit: int = 30) -> list[str]:
    lines = text.splitlines()
    hits = [ln for ln in lines if ERROR_SIGNALS.search(ln)]
    if len(hits) <= limit:
        return hits
    # keep the first 10 and last 20 — errors cluster at the start (command)
    # and the end (the actual traceback)
    return (hits[:10] + ["… %d error lines omitted …" % (len(hits) - 30)] + hits[-20:])
```

Behaviour, from the evidence:

- Result contains error signals → **never bookended.** Extracted error lines are *appended* to the hot-zone content, not substituted for it.
- Error result > 500 lines → head 5 + tail 5 + up to 30 extracted error lines (trimout).
- Clean result > 500 lines → head 5 + tail 5 + log pointer.
- Result ≤ 500 lines → pass through.

The recall floor of the error signal itself matters: on 59 negative examples Squeez returned empty output 80% of the time vs 7% for the 35B — **"nothing here" is a learned tool-specific policy.** Our regex must be allowed to return nothing.

## 14.6 Instruction-level savings, ranked by measured evidence

| Change | Evidence | Saving |
|---|---|---|
| Delete the duplicated tool catalogue from the prompt | P6; Cortex's hallucinated-tool incident | ~800 |
| Delete the todo contract's 2nd and 3rd statements | P6 | ~150 |
| Put `budget_notice` on threshold crossings only | §12.1 | ~64/step |
| `workspace_map` **increase** (spend) | LongCodeArena +53% in-project EM | **+3 072** |
| Reuse the OpenAI prompt cache | 90% read discount on Anthropic | dominant on cost, not on tokens |
| Drop `<tool_reference>`-style prose now that schemas are live-derived | P6 | ~200 |

---

# 15. Recommended metadata schema

## 15.1 Session-level context metadata

```jsonc
{
  "context_version": 3,
  "generation": 17,                       // bumped on ANY policy change
  "model_profile": {
    "model_id": "claude-sonnet-4-5-20250929",
    "provider": "anthropic",
    "context_window": 200000,
    "context_window_source": "catalog",   // catalog|provider_api|user|default
    "effective_context_window_percent": 100,
    "max_output_tokens": 64000,
    "tokenizer": "cl100k_base",
    "tier": "balanced",
    "tool_result_role": "tool",
    "supports_reasoning_replay": true
  },
  "fold_generation": 2,
  "last_fold_at": 1768000000.0,
  "last_fold_reason": "threshold",       // threshold|overflow|manual|explicit
  "checkpoint_seq": 412,
  "checkpoints": [
    { "archive_id": "arc_7", "seq": 412, "folded_from": 118, "folded_to": 411,
      "tokens_before": 168000, "tokens_after": 31000, "archive_bytes": 412338,
      "recall_count": 3, "generation": 2 }
  ],
  "slots": {
    "workspace_map": { "fingerprint": "9c1f…", "tokens": 3812, "stale": false, "loaded_at": 1767999000.0 },
    "project_rules": { "fingerprint": "aa42…", "tokens": 1180, "stale": true,  "loaded_at": 1767900000.0 }
  },
  "usage": { "source": "provider", "anchor_seq": 398, "tokens": 47396 },
  "diagnostics": {
    "tool_reinvocation_rate": 0.031,     // the TRACER metric
    "dedup_saved_tokens": 8940,
    "ladder_saved_tokens": 5120,
    "fold_count": 2,
    "unresolved_referral": false
  }
}
```

`tool_reinvocation_rate` is the single most important new metric (§20.2).

## 15.2 Entry-level metadata

```jsonc
// user
{ "kind": "user", "text": "…", "attachments": [], "intent": "implement|debug|explain|refactor" }

// assistant
{ "kind": "assistant",
  "content": [ {"type":"text","text":"…"},
               {"type":"reasoning","text":"…"},
               {"type":"tool_call","id":"call_abc","name":"file_read","arguments":{}} ],
  "model": "…", "provider": "…",
  "signature": "opaque-provider-replay-payload",   // pi thinkingSignature
  "usage": { "input": 31200, "output": 480, "cache_read": 28000,
             "cache_write": 1200, "total": 30880, "cost_usd": 0.0431 },
  "stop_reason": "tool_use" }

// tool_result
{ "kind": "tool_result",
  "tool_call_id": "call_abc",
  "tool_name": "file_read",
  "category": "rereadable",
  "status": "ok",
  "tokens_full": 2410, "tokens_in_context": 2410,
  "digest": "file_read a.py lines 1-250 (3812 bytes, 82 symbols)",
  "archive_id": null,                 // REREADABLE/EPHEMERAL → null
  "error_signature": null,
  "critical": false,                  // error/failure signal detected
  "recovered": false,                 // came from recall()
  "superseded_by": null,
  "mutation": { "path": "a.py", "sha_before": "…", "sha_after": "…" } }  // MUTATING only

// compaction
{ "kind": "compaction",
  "summary_md": "…",
  "state": { "objective":"…", "completed":[], "active":[], "blocked":[],
             "next_move":[], "decisions":[], "open_threads":[], "blocked_on":null },
  "work_state": { "read":[], "modified":[], "errors":[] },   // deterministic, not LLM
  "recent_context": [],                                        // verbatim tail entries
  "archive_id": "arc_7",
  "first_kept_seq": 412,
  "folded_from_seq": 118,
  "generation": 2,
  "reason": "threshold",
  "tokens_before": 168000, "tokens_after": 31000 }

// state (durable slot/ledger backing)
{ "kind": "state", "key": "ledger", "delta": { "read":[], "modified":[], "errors":[] } }
```

## 15.3 The sidecar schema

```jsonc
{
  "version": 1,
  "files_read": {
    "server/agents/context.py": {
      "ranges": [[1, 371]], "sha": "9c1f…", "bytes": 14902,
      "read_at": 1767999100.0, "reads": 2, "ts": 0
    }
  },
  "files_modified": {
    "server/agents/context.py": {
      "sha_before": "aa42…", "sha_after": "9c1f…", "ts": 0, "edits": 1
    }
  },
  "commands": [ {"cmd": "pytest -q tests/test_context.py", "exit": 0, "ts": 0} ],
  "failures": [
    { "signature": "TypeError:build_messages() got 2", "tool": "bash",
      "count": 3, "first_ts": 0, "last_ts": 0, "sample": "TypeError: …" }
  ],
  "decisions": [ {"text": "…", "ts": 0, "source": "fold:1"} ],
  "open_threads": [ {"text": "…", "ts": 0} ],
  "blocked_on": null,
  "unresolved_referral": false
}
```

Bounds: `files_read`/`files_modified` LRU-capped at 40 paths; `commands` last 20; `failures` top 10 by count; `decisions` 12; `open_threads` 8. On eviction, append a `<evicted>` note rather than dropping silently — a file that leaves the ledger should be *said to have left*.

## 15.4 The fencing grammar

Copy Codex's `Untrusted`/`Application` split and its rule that untrusted content **cannot** close its own wrapper:

| Origin | Role | Wrapping |
|---|---|---|
| System / operator | `SYSTEM` | unwrapped |
| Host-trusted application state | `DEV` | `<{key}>…</{key}>` |
| Project rules on disk | `USER` | `<project_rules>…</project_rules>` |
| **Anything from a tool, a file read, the web, a sub-agent, or a user paste** | `EXTERNAL` | `<external_{key}>…</external_{key}>` **with all `<`/`>`/`&` escaped** |
| The current user prompt | `USER` | unwrapped (the one genuine user channel) |

```python
def fence(key: str, value: str) -> str:
    escaped = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"<external_{key}>\n{escaped}\n</external_{key}>"
```

OpenCode's `wrapSystemUpdate` (`shared.ts:111-121`) does the same escaping for system-update wrappers. **This is not theoretical:** the Delimiter Hypothesis found a reproducible 20% injection failure rate on Markdown-fenced untrusted content in MiniMax M2.5, and 0% for XML-fenced. A fenced `<external_*>` block on a user-role message cannot override developer policy, and the escaping stops the payload closing the wrapper.

---

# 16. Recommended state machine

## 16.1 Session-level

```
                    ┌──────────┐
                    │   IDLE   │◀─────────────────────────────┐
                    └────┬─────┘                              │
                    user prompt                               │
                         ▼                                    │
                    ┌──────────┐                              │
                    │ BUILDING │──── tool call ────┐          │
                    └────┬─────┘                    │          │
                         │ assistant text w/o tools│          │
                         ▼                           ▼          │
                    ┌──────────┐            ┌──────────┐      │
                    │ FINALIZE │            │ EXECUTING│      │
                    └──────────┘            └────┬─────┘      │
                                                  │            │
      every step: ladder → dedupe → measure → fold-check        │
                             │                    │            │
                    ┌────────┴────────┐           │            │
                    │                 │           │            │
              fold< threshold    fail> threshold│            │
                    │                 │           │            │
                    ▼                 ▼           ▼            │
              ┌──────────┐      ┌──────────┐  ┌──────────┐      │
              │  FOLDING │      │  FAILING │  │ MEASURING│      │
              └────┬─────┘      └────┬─────┘  └────┬─────┘      │
                   │ success         │ still >    │            │
                   ▼                 ▼  threshold  │            │
              ┌──────────┐      ┌──────────┐      │            │
              │ REBUILD  │──────│ CONTEXT_ │      │            │
              │          │      │ EXHAUSTED│      │            │
              └────┬─────┘      └──────────┘      │            │
                   │                                │            │
                   └────────────────────────────────┴────────────┘
```

## 16.2 Compaction sub-machine

```
   working_set_tokens + fixed + cache_read
                  │
      ┌───────────┴───────────┐
      │  ≤ fold_threshold     │  →  no fold
      └───────────┬───────────┘
                  │
      ┌───────────┴───────────┐
      │  fold_threshold < x   │
      │      ≤ fail_threshold │
      └───────────┬───────────┘
                  │  enqueue async fold; continue with ladder-only context
                  ▼
            ┌──────────┐
            │  FOLDING │  (may straddle a turn boundary — §11.8)
            └────┬─────┘
                 │
    ┌────────────┼─────────────┬──────────────┐
    ▼            ▼             ▼              ▼
  archive    cut-point     summarize     assemble
  prefix     (findCutPoint) (primary     checkpoint +
  to disk    never a         model,       recent-context,
             tool_result     structured)  ledger diff
                 │            │              │
                 └────────────┴──────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    ▼                           ▼
              fold_ok                     fold_failed
          append compaction entry        ladder is still in effect;
          + ledger delta                 publish DEGRADED;
          + fold_generation += 1        retry once, then hold
```

## 16.3 Overflow sub-machine

```
        provider response
               │
      ┌────────┴────────┐
      │ is_context_     │──no──▶ normal handling
      │ overflow?       │
      └────────┬────────┘
               │ yes
      ┌────────┴─────────┐
      │ durable assistant│──yes──▶ T3 degrade: drop oldest whole turn group
      │ output emitted?  │            retry (unbounded)
      └────────┬─────────┘
               │ no
      ┌────────┴─────────┐
      │ overflow_recovery│
      │ attempted?       │──no──▶ fold(focus, reason="overflow"); retry (1)
      └────────┬─────────┘
               │ yes
               ▼
          fail_threshold exceeded?
               │
      ┌────────┴─────────┐
      │ no               │──yes──▶ fixed prefix doesn't fit
      ▼                  │            → CONTEXT_EXHAUSTED + /compact(focus), /reset
   head-trim oldest
   turn group; retry
   (unbounded)
```

---

# 17. Detailed implementation architecture

## 17.1 Module layout

```
server/context/
  __init__.py
  types.py              # Entry, SlotSpec, SlotInstance, RenderedContext, ModelProfile, ContextUsage
  log.py                # EntryLog: append, read_path_to_root_or_compaction, index
  registry.py           # SlotRegistry: ordered specs, stable indices, render dispatch
  slots/
    __init__.py         # SLOT_SPECS table
    project_rules.py    # hierarchical AGENTS.md / zenith.md discovery
    memory_ledger.py    # deterministic extractors + render
    environment.py      # cwd, git, date
    workspace_map.py    # wraps server/workspace/repo_map.py
    tool_policy.py      # rendered from the LIVE toolset
    task_board.py       # todo + run_state + plan
    live_state.py       # jobs, in-flight, receipts
    budget_notice.py    # threshold-crossing only
  assembler.py          # RenderedContext.build(entries, slots, profile)
  adapters.py           # ProviderAdapter.to_wire(rendered, model_profile) + normalize()
  governor.py           # thresholds, windows, reserve, tier policy
  measuring.py          # hybrid usage estimator (provider anchor + heuristic tail)
  lifecycle.py          # the staleness sweep + slot refresh orchestration
  ladder.py             # T0 zone-based tool-result degradation
  dedupe.py             # T1 duplicate elimination + staleness of receipts
  fold.py               # T2 the fold
  fail.py               # T3 emergency truncate
  recall.py             # T4 archive query
  diagnostics.py        # re-invocation rate, savings counters
  wire.py               # per-provider fragment renderers
```

## 17.2 The render pipeline

```
assembler.build(entries, profile) ->
  1. resolve_checkpoint(entries)          # last COMPACTION entry
  2. resolve_working_set(entries)         # walk leaf→root, stop at checkpoint
  3. collect slots                        # fixed indices, empty placeholders included
  4. ladder.apply(working_set, profile)   # T0, in-memory, does not mutate entries
  5. dedupe.apply(working_set)            # T1
  6. RenderedContext(slots, checkpoint, working_set, tail=())

governor.evaluate(rendered, profile) ->
  usage = measuring.measure(rendered, profile)
  if usage.tokens > profile.fail_threshold: fail
  elif usage.tokens > profile.fold_threshold: schedule fold
  elif not profile.cache_prompt_cached: ladder already applied; check tail budget

adapters.to_wire(rendered, profile) ->
  1. adapters.normalize(rendered)         # 4 passes (§17.3)
  2. wire.render(rendered, profile)       # slots → messages, per profile
  3. attach cache breakpoints
  4. return list[WireMessage]
```

**Steps 4 and 5 are in-memory and never mutate entries.** This is Cortex's rule and OpenCode's `prune` behaviour. A re-render with a bigger budget must see the full-fidelity content, or the degradation is irreversible — which is exactly the bug in DTOC's "disable-only" configuration (81.4% @ 57K, non-zero re-reads).

## 17.3 The four normalization passes

Adopt Codex's `normalize_history` (`history.rs:487-505`) and pi's `transform-messages.ts`, merged:

```python
def normalize(ctx: RenderedContext, profile: ModelProfile) -> RenderedContext:
    items = list(ctx.working_set)

    # pass 1 — synthesize missing outputs for unpaired calls
    #   deterministic ids: uuid5(FIXED_NS, f"{prefix}:{source_id}")  ← cache-stable
    items = ensure_call_outputs_present(items)

    # pass 2 — drop orphan outputs
    #   EXCEPT: outputs with no call_id (named external tool events)
    #   EXCEPT: server-executed outputs
    items = remove_orphan_outputs(items)

    # pass 3 — capability-based media stripping
    #   "<image content omitted because you do not support image input>"
    if not profile.supports_images_in_tool_result:
        items = strip_images(items)

    # pass 4 — cross-model reasoning demotion
    #   same provider+model → keep signature; else → demote to text or drop
    items = demote_cross_model_reasoning(items, profile)

    return replace(ctx, working_set=tuple(items))
```

**Why pass 1 is non-negotiable for us.** Our T0 ladder and T1 dedupe both can break call/result pairing, and OpenAI/Codex will reject a transcript with a `tool_calls` entry and no matching `tool` result. Codex panics in debug (`error_or_panic`) precisely because this is a class invariant, not an edge case. **We must not add any pruning rule that can orphan a call without adding this pass in the same change.**

## 17.4 The turn integration

Today `build_messages` is called once at `simple_loop.py:379`. The proposal:

```python
# once per PromptExecutor lifetime
self.context = ContextSession(session_id, config, tool_registry, profile_provider)
self.context.restore(entries)               # read_path_to_root_or_compaction

# per turn
self.context.begin_turn(model=model)        # resolves the profile, refreshes slots
#   → runs the staleness sweep, emits diff notices, updates budget_notice

for step in range(MAX_STEPS_DEFAULT):
    rendered = self.context.render()        # assemble + ladder + dedupe
    decision = governor.evaluate(rendered, profile)
    if decision.fail:  yield error(CONTEXT_EXHAUSTED); return
    if decision.fold:  self.context.schedule_fold()          # async, §11.8
    wire = adapters.to_wire(rendered, profile)

    for event in stream_completion(provider, wire, tools, ...):
        if event.tool_call:
            result = await execute(event.tool_call)
            self.context.record(result)      # → entry + ledger delta + slot refresh
        yield event

# end of turn
self.context.flush()                        # awaits any in-flight fold
self.context.end_turn()
```

## 17.5 What must not change

- `ContextManager.should_summarize` / `is_context_exhausted` keep their signatures as thin wrappers over the governor, so `test_context.py` keeps passing.
- `CompactionService.compact`'s event contract (phases `["preserving","compacting","verifying"]`, `context_compaction_ended` with the `tokens`/`tokensBefore`/`tokensAfter` key set) is asserted by `test_compaction_ui_events.py` and must survive.
- `test_token_usage_occupancy.py`'s invariant — **`context_occupancy` and `total_tokens` are separate columns and `percent` is occupancy ÷ window** — is a good invariant and must survive. The hybrid estimator makes it *more* true, not less.
- `test_inflight_compaction.py`'s load-bearing contract — **`file_read` and `todo` results retain actual content and must not reduce to a one-line digest** — becomes a *special case* of the general rule (§8.2 assigns `MUTATING` and `REREADABLE` high weight) rather than a hard-coded set.
- `test_context_files.py` currently **asserts we do NOT read project context files.** That test must be inverted as part of this work. It was a deliberate scope decision at the time; the proposal changes it.

---

---

# 18. Trade-offs and alternatives considered

| Decision | Rejected alternative | Why rejected | Cost of our choice |
|---|---|---|---|
| **Append-only log + view** | Continue rewriting the JSONL on compaction | Rewriting destroys the archive, makes resume O(transcript), and makes rewind impossible. Every reference system converged on append-only. | Storage grows; needs log compaction later |
| **Slots + registry** | Keep composing one system prompt from lambdas | No per-region budget, staleness, or role policy. Every problem in §3 traces to this. | One more abstraction between the loop and the provider |
| **Codex fragments** | pi's byte-stable system-prompt rebuild | Fragments give per-section diffing, which is what makes refresh cheap. pi's approach is simpler but a changed tool set invalidates the whole prompt. We use **both**: fragments for the slot region, a byte-stable template for the head. | Two composition idioms |
| **Weighted cut selection** | Plain recency (Codex, OpenCode) | Recency keeps six grep results and drops the one stack trace. `error_bonus` is cheap and materially better. | Slightly more complex cut walk |
| **Structured fold (JSON)** | Prose summary (all four references) | A prose summary is the *only* record; a structured one is a lossless state delta plus lossy prose. The ledger cannot degrade. | A summarizer that must produce valid JSON (use schema-constrained decode where supported) |
| **Reversible archives** | Delete on fold | ACM + DTOC's ablation: reversibility *is* the mechanism (0.0 vs 4.2 re-reads). Codex's local compaction shows what the alternative costs. | Disk growth; an extra tool; a `recall` path to test |
| **Primary model as summarizer** | `weak_model` (today) | Cortex: *"Conversation history summaries are the only record of what happened."* All four references use the primary model. | More expensive folds |
| **Cache-aware ladder** | Always run the ladder | Cortex's own model: with 90% cache discount the ladder is ~19% *more* expensive. | A flag, plus logging |
| **Incremental / async fold** | Blocking fold in the transform hook | Removes the latency spike from the critical path; T0/T3 are always available as a fallback. | More state; a generation guard on apply |
| **Eventual not strict consistency** | Recompute everything every turn | Recomputing the tree-sitter repo map per turn is unaffordable. Fingerprint-first makes the common case a no-op. | A TTL backstop is required; Codex's `AgentsMdManager` shows what omitting it costs |
| **Deterministic ledger, no embeddings** | Vector memory over tool outputs | LongCodeArena: best embedding retriever 0.33 MAP vs GPT-4 0.39. Squeez: BM25 gets 0.22 recall on tool output; Last-N 0.05. | Loses semantic recall across sessions (see §18.1) |
| **Per-tool budgets** | One global cap | Cortex's `Bash: 7_500` vs `Grep: 25_000`. Signal density varies 10× across tools. | A registry to maintain |
| **Tiered policy** | One policy for all models | The whole point of the brief. The scaling law, NoLiMa, and AgentFloor all say small models need different treatment. | A tuning surface; needs a per-tier regression harness |
| **`role:"toolResult"` canonical** | Keep `role="user"` + `[Tool:` | pi's model. Fixes P2 and is a precondition for the four normalization passes. | Provider adapters; a storage migration |
| **No vector/graph memory now** | Build a code graph like `danielblomma/cortex` | Real value, but a separate project with its own index-maintenance cost, and LongCodeArena's numbers say symbol+tree adjacency beats embeddings for the dominant task. | Revisit after the core is in place |

## 18.1 Known gaps we are choosing not to close now

| Gap | Consequence | Revisit when |
|---|---|---|
| **Cross-session memory** | Each session starts cold. No recall of "this broke in commit X" from last week. | After the core; ACM's `summary_{id}.json` pattern extends naturally to a session-level archive |
| **Semantic repo retrieval** | File selection is PageRank + the model. On a large monorepo the model still has to `grep`. | Aider's conversation-identifier boosting (×10) is a 20-line addition and should be done early — §18.2 |
| **Branch/fork** | Rewind is a truncate, not a fork. | If the TUI ever needs "try another approach from turn 12" |
| **Multi-agent ledger merge** | Sub-agent results are prose, not ledger deltas | With §13.6 |
| **Log compaction** | The entry log grows forever | When sessions exceed a few hundred MB |
| **Learned compression** | TACO/ACE/Squeez show rules can be learned from over-compression complaints | Only with training data we do not have |

## 18.2 One cheap addition worth pulling forward

Aider personalizes the repo map with **identifiers mentioned in the conversation (×10)** and **named symbols ≥8 chars (×10)**, on top of **chat files (×50)**. Our `repo_map.py:302-319` implements only the chat-files boost (`×3.0`).

```python
# in the scoring loop
mentioned = _identifiers_in_recent_assistant_text(session, window=8)   # ≥8 chars, \b-delimited
score += len(names_defined & mentioned) * 10.0
```

This is roughly 20 lines, no index change, no schema change, and it directly attacks LongCodeArena's finding that retrieval is the dominant bottleneck. **It should be in phase 1, not deferred.**

---

# 19. Failure modes and safeguards

## 19.1 Hazards specific to this design

| # | Failure | Detection | Safeguard |
|---|---|---|---|
| F1 | **A pruning rule orphans a tool call** | `normalize` pass 1 count > 0 in production logs | Codex's `error_or_panic` equivalent: a dev-mode assertion plus a production warning counter. **Never deploy a pruning rule without the matching normalize pass.** |
| F2 | **Fold output is not valid JSON** | Parse failure rate | Retry once with a stricter instruction; on a second failure fall back to prose-only summary and emit `FOLD_DEGRADED`. The ledger is unaffected (it is deterministic), so this is a *narrative* degradation, not a *state* one. |
| F3 | **Fold generation race** (fold A finishes after fold B) | Generation mismatch at apply time | Already solved: `_generations[session_id]` re-checked before commit and before in-memory apply (`compaction_service.py:510, 540`). Preserve this exactly. **Add the same guard to the async path.** |
| F4 | **Slot loader fails transiently and we revoke** | `slots_stale > 0` | The §10.4 state machine: `STALE` retains the last admitted value. OpenCode's `unavailable` sentinel exists for exactly this. |
| F5 | **Wrong context window** | `context_window_source == "default"` | Conservative threshold (§13.3); log the source on every request (Cline #9181). |
| F6 | **`budget_notice` thrashes the cache** | Cache hit rate drop after a step | Emit on 5%-bucketed threshold crossings only, not per step. |
| F7 | **Ladder makes a needed re-read** | `tool_reinvocation_rate` | TRACER: static truncation *increases* total tokens 3–24% by triggering re-reads. **Alert if the rate exceeds ~0.07.** Mitigation: REREADABLE placeholders keep `path` + `line_range` so a re-read is one cheap call, not a rediscovery. |
| F8 | **Ledger grows without bound** | `ledger_tokens > budget` | LRU eviction on `files_read`/`files_modified` (40 paths), with an `<evicted>` note. Never evict `decisions` or `failures` silently. |
| F9 | **The `<external_*>` fence is escaped wrong** | Unit test with a payload containing `</external_x>` | `fence()` must escape before wrapping, and the test must include a payload that tries to close the tag. **This is the Delimiter Hypothesis's one reproducible vulnerability.** |
| F10 | **A fold's `<recent-context>` is larger than the keep budget** | Assembly-time budget check | Compute the tail budget as `keep_recent_tokens` **minus** the summary budget, and hard-cap `<recent-context>`. OpenCode's `recent` field has no such cap. |
| F11 | **Provider rejects `role="tool"`** | 400 on first use | `tool_result_role` capability; automatic fallback to `user` + prefix, remembered per provider. |
| F12 | **`recall` returns content that no longer exists** | Archive missing | `recall` returns an explicit `{"error":"archive_not_found"}` — never empty content, which the model would read as "there is nothing here." |
| F13 | **A user's text is mistaken for a checkpoint** | Entry-kind filter | Typed markers, never string prefixes (Codex's `is_summary_message` is exactly the bug to avoid). |
| F14 | **Async fold lands after the session ends** | Task tracking | `flush()` at turn end; `destroy()` awaits in-flight folds or marks them orphaned. |
| F15 | **The checkpoint grows across generations** | `checkpoint_tokens` | The checkpoint is a *single* entry, replaced each fold. The ledger accumulates; the checkpoint does not. |
| F16 | **Model switch mid-session** | `model_changed` event | Drop reasoning signatures (`isSameModel` gate), re-derive `tool_policy` if provider-specific, re-render `budget_notice`. Do **not** re-fold. |
| F17 | **Cache-aware ladder gates on a clock** | `last_llm_call_ts` drift | Gate on the *provider-reported* response timestamp where available; wall clock only as a fallback. Clock skew should not enable trimming. |
| F18 | **Repeated `recall` of the same archive** | `recall_count` per archive | Cap at ~5 per archive per session; return the digest after that and suggest a targeted `file_read` instead. |

## 19.2 Circuit breakers

| Breaker | Condition | Action |
|---|---|---|
| **Fold breaker** | 3 consecutive fold failures in a session | Disable folding; fall back to T0+T3; emit a UI banner suggesting `/reset` |
| **Cache breaker** | Cache hit rate < 30% over 20 requests | Log the fingerprint churn source; disable the ladder; re-evaluate the slot order |
| **Re-invocation breaker** | `tool_reinvocation_rate > 0.10` over 20 results | Raise `hot_zone_tokens`; disable the far-zone placeholder (keep bookends) |
| **Fold-generation breaker** | Generation advanced twice during one fold | Discard the result; re-schedule |
| **Budget breaker** | Fixed prefix (head + slots) > 40% of the window | Emit `SLOT_BUDGET_EXCEEDED`; suggest disabling the largest optional slot. This is a *configuration* problem, not a runtime one, and hiding it is how Cline's #9181 shipped. |

---

# 20. Benchmarking and evaluation methodology

## 20.1 The metric stack

| Metric | Why |
|---|---|
| **Task success (pass@1, ≥3 seeds, ±CI)** | The only metric that matters |
| **Total input tokens** | Cost driver |
| **Peak context length** | ACM measures this; it is the causal variable |
| **Agent steps / tool calls** | CAT; and the confound detector — context management *increases* tool calls (arXiv 2606.29718) |
| **Tool re-invocation rate** | **TRACER's contribution. The metric that reveals whether compaction is actually saving anything.** |
| **Cost per solved task** | Terminal-Bench reports accuracy ± CI *and* cost |
| **Unfinished / premature-termination rate** | arXiv 2606.29718; distinguishes "test-time scaling" from "degradation" |
| **Solution consistency across trials** | ACM; only meaningful with ≥3 seeds |
| **Positional spread** | §9.4; a model-agnostic acceptance criterion |
| **Cache hit rate** | Ours; the lever that dominates cost on Anthropic |
| **Ledger completeness** (ours) | Fraction of fold generations where a later `recall` was needed. Should trend to zero. |

## 20.2 The single most important new metric

```
tool_reinvocation_rate = (# of tool calls in turn N whose (tool, canonical_args)
                          matches a call in turns 1..N-1) / (# of tool calls in turn N)
```

TRACER's finding is that aggressive static truncation **increases total tokens 3–24%** because it triggers re-invocations. Pass@1 alone hides this completely. **Instrument this from day one, before any compaction change, so there is a baseline.**

We already emit per-tool-call events with arguments (`EventAdapter` → `EventKind`). This is a query, not a new pipeline.

## 20.3 A/B protocol

**Rule 0: freeze the scaffold and the model; vary only the policy.** Every number in §5 that isolates context management does this. A scaffold swap is worth more than most policies (ReAct 48.8% vs SWE-Compressor 57.6% on the *same* OpenHands scaffold).

1. **Freeze** model, system prompt body, tools, and the loop. Only the context policy changes.
2. **≥3 seeds**, report CIs, and **pre-register the margin.** AgentFloor used TOST at ±10pp and then explicitly *declined* to claim equivalence where n=45 gave 24–35pp CIs. That restraint is the point.
3. **Instrument the diagnostic, not just the score.** Add the terminal-state taxonomy: success / premature-stop / wrong-path / budget-exhausted / provider-error. arXiv 2606.29718 could only show context management is test-time scaling *because* they measured premature termination.
4. **Report the matched-token-budget comparison** alongside the standard one. TACO: +1–4% standard vs **+2–3% under matched budgets.** The matched number isolates quality from quantity.
5. **Ablate reversibility separately.** DTOC: tracking-only 77.8% @ 87K; disable-only 81.4% @ 57K; full 83.6% @ 61K with **0.0 re-reads.** If you ship disable-only, you are running the 81.4% config and should know it.
6. **Expect model-dependence and budget for it.** DTOC: Opus and Gemini Flash got *worse* in tokens. arXiv 2606.29718: strong backbone wants isolation, weak backbone wants keep-latest. "Works on our current model" is untested on every other model.
7. **Watch for scorer artifacts.** Jagtap's naive scorer manufactured a catastrophic instruction-adherence collapse that resolved to 1.000 under document-level refusal detection. Add document-level refusal filtering before concluding compaction broke instruction-following.

## 20.4 Test suite additions

| Test | Asserts |
|---|---|
| `test_normalization.py` | Unpaired call → synthetic output with a **stable** uuid5 id (re-render twice, compare); orphan output dropped; named external output kept; cross-model reasoning demoted |
| `test_ladder.py` | Zone boundaries; error lane never degrades; `MUTATING` never cleared; `EPHEMERAL` cleared past the span; archive path present for `NON_REPRODUCIBLE` |
| `test_ladder_idempotent.py` | Render at budget B, then at 2B — full-fidelity content is recoverable (T0 is in-memory) |
| `test_dedupe.py` | Overlapping re-read collapses; identical command collapses; **after `file_edit`, every earlier receipt for that path is marked stale** |
| `test_fold_cutpoint.py` | Cut never lands on a `tool_result`; snaps forward to a user/assistant boundary; split-turn produces two summaries; never cuts immediately after a checkpoint |
| `test_fold_idempotent.py` | Two folds; the first checkpoint's entries are excluded from the second's input; `fold_generation` increments; `decisions` append rather than restate |
| `test_fold_reversible.py` | After a fold, `recall(archive_id, q)` returns the raw prefix; `archive_id` is present in the rendered checkpoint |
| `test_ledger.py` | Deterministic extractors; LRU eviction emits an `<evicted>` note; `decisions`/`failures` never silently dropped |
| `test_slots.py` | Fixed indices; empty slots occupy a position; **transient loader failure retains the last admitted value**; definitive removal emits a notice; unchanged fingerprint is a no-op |
| `test_fencing.py` | A payload containing `</external_x>` cannot close the fence; untrusted content cannot reach `SYSTEM`/`DEV` role |
| `test_estimator.py` | Provider anchor + heuristic tail; a checkpoint inserted after a response invalidates that response's usage; tool definitions added after the anchor are counted |
| `test_governor.py` | Two-limit `min()`; `window_source == "default"` → conservative threshold; **exactly one clamp** (regression test for Cline #9181) |
| `test_overflow.py` | All three detection cases; the three exclusion regexes; no retry after durable assistant output |
| `test_reinvocation.py` | The metric is computed and matches a hand-built fixture — this is the baseline |

## 20.5 Benchmarks

- **SWE-bench Verified**, using the **"Bash Only" view** (`swebench.com/`) which fixes the model in one mini-swe-agent environment. This is the only apples-to-apples comparison, since scaffold choice moves scores by >15pp.
- **Terminal-Bench 4.0** [arXiv] 2601.11868 — where TACO, DTOC and DeepSWE are evaluated. The leaderboard reports accuracy ± CI **and cost**; Artificial Analysis breaks cost into input / cache-hit / cache-write / reasoning / answer, which is a good model for us.
- **Long Code Arena** for the repo-map work specifically (project-level completion, bug localization).
- **LongMemEval** if we adopt observational memory later; Cortex's 84–95% is the reference point.
- **The positional probe** (§9.4). Run it once. Then stop.

---

# 21. Concrete recommendations for our codebase

Ordered by evidence strength ÷ implementation cost. **Each is independently shippable.**

## R1 — Fix the tool-schema accounting *(P1; hours)*

`context.py:135-136` `set_aux_tokens` has no callers, so every occupancy figure omits tool schemas. `SchemaResolver.schema_tokens` (`toolkit/resolver.py:112`) already computes it.

**Wire `set_aux_tokens` from the tool registry at turn start, or — better — implement §14.2's hybrid estimator and delete `_aux_tokens` entirely.** Surface `usage.source` in the `tokenInfo` event so the TUI can show `estimated` vs `provider` honestly.

## R2 — Use the primary model for compaction summarization *(minutes; free)*

`summarizer.py:41-45` uses `config.weak_model`. All four reference systems use the primary model, and Cortex argues for it explicitly. Switch to the primary with a reduced `max_tokens` (respecting TALE's elasticity floor — do not go below ~1 024 output tokens).

## R3 — Isolate the summarization request from the cache *(hours)*

`_cache_prefix_for` (`compaction_service.py:221-237`) always returns `[]` because nothing sets `cache_control`. Either set it, or (pi's approach) explicitly set `cache_retention="none"` and a throwaway session id on the summarizer request so it does not pollute the session's cache prefix. **The second is simpler and strictly correct.**

## R4 — Error-aware tool retention *(1–2 days; high value)*

Implement §14.5. The single-line change with the largest effect: **in `prune_inflight_messages` (`compaction.py:154-219`) and `prune_tool_outputs` (`compaction_service.py:144-201`), never bookend a result whose content matches `ERROR_SIGNALS`.** Today a failing test run's stack trace is trimmed to 1000 chars from the middle, which is close to guaranteed to remove the failure.

## R5 — Wire `RepoMap._snapshot()`, add conversation-identifier boosting, raise the budget *(1 day)*

`repo_map.py:149-172` computes `(rel, mtime_ns, size)` + HEAD and is never called. Use it as the `workspace_map` slot fingerprint with a 120s TTL. Add Aider's `identifiers mentioned in conversation ×10` boost on top of the existing `chat_files ×3` (`repo_map.py:302-319`). Raise the budget from `min(1024, 0.05·W)` to `min(W//8, 4096)`.

## R6 — Invert `test_context_files.py` *(half a day)*

That test currently **asserts we do not read project context files.** Add `project_rules` as slot 2 with hierarchical `AGENTS.md` / `zenith.md` discovery (Codex's algorithm: root-most first, `AGENTS.override.md` shadows `AGENTS.md`, 32 KiB budget). The test was a deliberate scope decision; this proposal changes it. **Do not ship the slot without also adding a removal notice and the transient-failure `STALE` state** — Claude Code's documented user complaint is exactly "my `paths:`-scoped rule was lost on compaction."

## R7 — Make compaction a view *(1 week; the structural change)*

Replace `FileMessageRepository.compact_history` (`session_store.py:289-334`) with an appended `compaction` entry carrying `{summary, first_kept_seq, work_state, archive_id}`. `read_path_to_root_or_compaction` replaces the full read. Archive the raw prefix to `archives/<session>/<archive_id>.jsonl`. This change makes R8, R9 and the whole §11 design possible, so it gates the rest.

## R8 — First-class tool results *(3–5 days)*

Introduce a `ToolResult` variant with `tool_call_id` in the canonical model, with a `tool_result_role` capability per adapter that lowers to the current `user` + `[Tool:` form for providers that need it. Ship **in the same change** as the four normalization passes (§17.3) — Codex's `ensure_call_outputs_present` is not optional once history can be rewritten.

## R9 — The slot registry *(1–2 weeks; the core refactor)*

`SlotSpec` + `SlotRegistry` + the staleness sweep. Start with the slots that already exist: `repo_map` → slot 5, `plan` → folded into `task_board` (slot 8), the dead `SESSION_STATE_MARKER` → revived as the `memory_ledger` (slot 3). Move the system prompt to Region 0 with `tool_policy` generated from the live toolset. Delete the duplicated tool catalogue from `BUILD_MODE_PROMPT` (P6).

## R10 — The deterministic ledger *(2–3 days)*

Four extractors, no LLM, from the entry log: `files_read`, `files_modified`, `commands_run`, `failures`. Plus LLM-extracted `decisions`/`open_threads`/`blocked_on` from the fold. This is the load-bearing anti-degradation mechanism and the cheapest high-value item in the plan.

## R11 — The tool-result ladder *(3–5 days)*

§11.2. Zones by token distance; per-tool budgets by signal density; four categories; the error lane. Replaces the single `keep_latest_tools=6` / 1000-char rule.

## R12 — Deduplication and receipt staleness *(2–3 days)*

§11.3. The row that matters most: **after a `file_edit`, mark every earlier `file_read` receipt for that path stale.** Today a stale read sits in context and the model quotes it.

## R13 — `recall(archive_id, query)` *(2 days)*

One tool. Returns query-matched lines from the archive. This is what makes lossy compaction safe (DTOC's ablation) and is the concrete form of ACM's `query_memory`.

## R14 — The overflow ladder *(1 day)*

§11.5. Three-case classification; the "no durable assistant output yet" guard; unbounded head-trim with a reset retry counter; whole-turn-group atomicity.

## R15 — Tiered policy *(3–5 days)*

`ModelProfile` with the tier table (§13.2), driven by cost and capability from `zenith_catalog.json`. Plus `context_window_source` provenance and the conservative-on-unknown rule. Plus the one-clamp regression test.

## R16 — Tool-name familiarity probe *(1 day)*

§13.5. A one-time logprob-peakedness probe per `(model, tool_name)` at provider-validation time; aliases where peakedness is low. PA-Tool measured +9.6pp on 8B for this, at zero token cost. Our names are already conventional, so expect a small effect — but it is cheap and measurable.

## R17 — Fold the summarizer to structured output *(2–3 days)*

§11.4. JSON contract; `decisions` append-not-restate; verbatim errors; `is_split_turn` second summary. Depends on R7 and R10.

## R18 — Cache breakpoints *(1–2 days)*

Three breakpoints, ≤20 slot blocks, per-provider `cache_control`, and the cache-aware ladder gate. Depends on R9.

## R19 — Async fold *(2–3 days)*

§11.8. Enqueue during the turn, await at the boundary, T0/T3 always available as a fallback. Depends on R7 and R17.

## R20 — New metrics *(1 day, but do it FIRST)*

`tool_reinvocation_rate`, `ledger_completeness`, `positional_spread`, `cache_hit_rate`, `dedup_saved_tokens`, `ladder_saved_tokens`. **Ship before any compaction change**, so there is a baseline.

## R21 — Fix `default_max_tokens_for_context` *(30 min)*

`constants/context.py:64-65`: `max(DEFAULT_LLM_MAX_TOKENS, min(window // 2, 32_768))`. On a small window, `window // 2` can fall below TALE's elasticity floor. Clamp from below too.

## R22 — Unify the two compaction triggers *(1 hour)*

`should_summarize` (`context.py:298-303`, two clauses) and the loop's per-iteration percent check (`simple_loop.py:522-537`, one clause) are not equivalent. Route both through the governor.

## R23 — Inspect what the specialists do *(1 hour)*

The 8B-orchestrator finding: thinking at the orchestrator, not the sub-agents. Check `delegation/scout.py` and `crewmate_loop.py`, and return structured results whose key fields merge into the parent's ledger.

## R24 — Deduplicate the system prompt *(half a day)*

P6. The tool catalogue is stated three ways; the todo contract four. Delete the prose; keep the JSON schemas and the in-band nudge.

## R25 — `model_name` / `provider_name` are accepted and ignored *(1 hour)*

`prompts.py:126-138`, asserted by `test_prompts_template.py:108-112`. Either use them (tier-driven) or remove the parameters. Dead parameters that look configured are how Cline's alias bug shipped.

---

# 22. Phased implementation plan

## Phase 0 — Measurement baseline *(1 week; no behaviour change)*

**R20, R3, R21, R1 (partial)**

Add the metrics and fix the two accounting bugs so every later phase is measurable.

- [ ] `usage.source` on `tokenInfo`; hybrid estimator (§14.2) behind a flag
- [ ] `tool_reinvocation_rate` + `cache_hit_rate` + a positional-spread harness
- [ ] `cache_retention="none"` + throwaway session id on the summarizer request
- [ ] `default_max_tokens_for_context` floor fix
- [ ] Baseline capture: 3 seeds × 3 representative tasks, all metrics recorded

**Exit criteria:** baseline numbers exist; the estimator agrees with provider usage within 5% on ≥90% of steps.

## Phase 1 — Safe, high-value, no structural change *(1 week)*

**R2, R4, R5, R12, R22, R24, R25**

Everything here is a bug fix or a local improvement. No migration.

- [ ] Primary model for summarization
- [ ] Error lane: never bookend an error-bearing tool result
- [ ] `RepoMap._snapshot()` wired; conversation-identifier boosting; budget → `min(W//8, 4096)`
- [ ] Dedupe + receipt staleness after a mutation
- [ ] Both triggers through one predicate
- [ ] System-prompt deduplication
- [ ] Clean up `model_name`/`provider_name`
- [ ] `test_normalization.py` — the four passes, **shipped before any pruning change**

**Exit criteria:** `tool_reinvocation_rate` does not increase; error-bearing results retain full content; repo map is present on turn 1 and refreshes.

**This phase alone should be a measurable win. Do not proceed to Phase 2 without measuring it.**

## Phase 2 — The ledger *(1 week)*

**R10, R6 (partially)**

The cheapest high-value structural change, and it is independent of the slot registry.

- [ ] `context/types.py`: `Entry`, `Sidecar`, `ToolCategory`
- [ ] Four deterministic extractors
- [ ] `memory_ledger` rendered as a message at a fixed index (Region 1 position 2, ahead of the repo map)
- [ ] Fold extracts `decisions`/`open_threads`/`blocked_on` into the ledger
- [ ] `test_ledger.py`

**Exit criteria:** after 3 folds, the ledger still contains every file touched and every distinct error signature; the summarizer can be replaced with a stub and the agent still knows what it did.

## Phase 3 — Compaction as a view *(1.5 weeks)*

**R7, R13, R17**

The structural change. R8, R9, R18, R19 all depend on it.

- [ ] Entry log with `append` + `read_path_to_root_or_compaction`
- [ ] `compaction` entry kind; storage migration with a one-way upgrade
- [ ] Archive writer: `archives/<session>/<arc_id>.jsonl`
- [ ] `recall(archive_id, query)` tool
- [ ] `findCutPoint` with valid-cut-point snapping; never a `tool_result`
- [ ] Structured fold (JSON) with a prose fallback
- [ ] `<conversation-checkpoint>` rendering incl. `<recent-context>` and the archive handle
- [ ] Overflow ladder (R14) with the "no durable assistant output" guard
- [ ] `test_fold_*.py`, `test_overflow.py`, `test_fold_reversible.py`
- [ ] `test_context_commands.py` and `test_compaction_service.py` updated to the new storage semantics

**Exit criteria:** `ledger_completeness` → 100%; zero `recall`s needed for task success on the phase-0 benchmark; 3 folds deep with no state loss.

## Phase 4 — First-class tool results + the ladder *(1.5 weeks)*

**R8, R11**

- [ ] `ToolResult` variant in the canonical model with `tool_call_id`
- [ ] `tool_result_role` capability; `user`+prefix fallback, remembered per provider
- [ ] Category registry per tool; per-tool budgets
- [ ] Zone-based ladder; error lane; archive paths
- [ ] **In-memory only** — a re-render at a larger budget must recover full fidelity
- [ ] `test_ladder.py`, `test_ladder_idempotent.py`

**Exit criteria:** ladder is idempotent; `test_normalization.py` shows zero orphan calls across a 200-step fuzz; per-tool budgets appear in the diagnostic breakdown.

## Phase 5 — The slot registry *(2 weeks; the largest phase)*

**R9, R6 (finish), R18**

- [ ] `SlotSpec` / `SlotRegistry` / fixed indices / empty placeholders
- [ ] Staleness sweep: fingerprint-first, TTL backstop, `STALE` state, removal notices
- [ ] Region 0 head: `agent_identity` + `tool_policy` generated from the live toolset
- [ ] Slot table: `project_rules` (hierarchical AGENTS.md), `memory_ledger`, `environment`, `workspace_map`, `skill_buffer`, `task_board`, `live_state`, `budget_notice`
- [ ] `test_slots.py` including the transient-failure case
- [ ] Three cache breakpoints; ≤20 slot blocks; cache-aware ladder gate
- [ ] Invert `test_context_files.py`

**Exit criteria:** slot refresh is a no-op when unchanged (measured as a stable cache fingerprint); a transient loader failure does not change the rendered bytes; the cache hit rate is higher than phase 4.

## Phase 6 — Model-aware policy *(1 week)*

**R15, R16, R23**

- [ ] `ModelProfile` + tier table + `context_window_source` provenance
- [ ] Two-limit `min()` governor; conservative-on-unknown
- [ ] Tier-driven `tool_policy` verbosity; tier-driven instruction budget
- [ ] Capability flags: regex/table-derived, never string equality
- [ ] Tool-name familiarity probe + aliases
- [ ] Specialist-return → ledger merge

**Exit criteria:** the same task set is measured on at least one `frontier` and one `efficient` model; the tier policy beats a single flat policy on at least one; `test_governor.py` guards the one-clamp rule.

## Phase 7 — Async fold + observability *(1 week)*

**R19 + dashboards**

- [ ] Fold enqueued during the turn, awaited at the boundary, T0/T3 fallback
- [ ] `fold_generation` guard on the async apply path
- [ ] `digestIdle()` scheduled in idle windows with a 60s bounded timeout
- [ ] TUI: fold-generation indicator, ledger panel, `tool_reinvocation_rate` in session stats
- [ ] `/compact <focus>` and `/reset` (pre-filled from the ledger) exposed as first-class commands

**Exit criteria:** p95 turn latency during a fold is within 10% of a non-fold turn; `/reset` produces a usable brief from the ledger alone.

## Total: ~11.5 weeks of focused work

Phases 0–2 (3 weeks) deliver the majority of the measured value and contain **zero** structural risk. Phases 3 and 5 are the ones that need a careful migration and are where the design lives.

---

# Appendix A — reference-system constant tables

## A.1 OpenCode (`ref_repo/opencode`)

| Constant | Value | Location |
|---|---|---|
| `CHARS_PER_TOKEN` | 4 | `packages/core/src/util/token.ts:3` |
| `DEFAULT_BUFFER` | 20 000 | `packages/core/src/session/compaction.ts:12` |
| `DEFAULT_KEEP_TOKENS` | 8 000 | `:13` |
| `TOOL_OUTPUT_MAX_CHARS` | 2 000 | `:14` |
| `SUMMARY_OUTPUT_TOKENS` | 4 096 | `:15` |
| `MAX_LINES` / `MAX_BYTES` / `RETENTION` | 2 000 / 50 KiB / 7 d | `packages/core/src/tool-output-store.ts:13-15` |
| `PRUNE_MINIMUM` / `PRUNE_PROTECT` | 20 000 / 40 000 | `packages/opencode/src/session/compaction.ts:28-29` |
| `PRUNE_PROTECTED_TOOLS` | `["skill"]` | `:31` |
| `DEFAULT_TAIL_TURNS` | 2 | `:32` |
| `COMPACTION_BUFFER` | 20 000 | `packages/opencode/src/session/overflow.ts:8` |
| `OUTPUT_TOKEN_MAX` | 32 000 | `packages/opencode/src/provider/transform.ts:18` |
| `SMALL_MODEL_RE` | `/\b(nano\|flash\|lite\|mini\|haiku\|small\|fast)\b/` | `packages/core/src/catalog.ts:294` |
| Provider prompts | 9 variants, 1.9k–3.9k tokens | `packages/opencode/src/session/prompt/*.txt` |
| `supportsNativeSystemUpdates` | `=== "claude-opus-4-8"` | `packages/llm/src/protocols/anthropic-messages.ts:356` |
| `CachePolicy.AUTO` | `{tools:true, system:true, messages:"latest-user-message"}` | `packages/llm/src/cache-policy.ts:18-22` |

## A.2 Codex (`ref_repo/codex`)

| Constant | Value | Location |
|---|---|---|
| `APPROX_BYTES_PER_TOKEN` | 4 | `codex-rs/utils/string/src/truncate.rs:4` |
| `auto_compact_token_limit` | `min(config, 0.9 × window)` | `codex-rs/protocol/src/openai_models.rs:499-510` |
| `COMPACT_USER_MESSAGE_MAX_TOKENS` | 20 000 | `codex-rs/core/src/compact.rs:62` |
| `project_doc_max_bytes` | 32 KiB | `codex-rs/config/src/config_toml.rs:73` |
| Unknown-model truncation fallback | `bytes(10_000)` | `codex-rs/models-manager/src/model_info.rs:170` |
| `SYNTHETIC_OUTPUT_ID_NAMESPACE` | uuid5 `0x90d38d3e_6a5b_4d52_bfe2_2f1e634bfac4` | `codex-rs/core/src/context_manager/normalize.rs:18-19` |
| Serialization allowance | `policy * 1.2`, `ceil` | `codex-rs/protocol/src/protocol.rs:3270-3283` |
| Remote v2 retained budget | 64 000 | `codex-rs/core/src/compact_remote_v2.rs:77-78` |
| Remote v2 per-`AgentMessage` cap | 10 000 | `:78` |
| `MAX_RENDERED_FRAGMENT_BYTES` (tools) | 4 KiB | `codex-rs/core/src/context/world_state/tools.rs:112` |
| `MAX_NAMESPACE_DESCRIPTION_CHARS` | 250 | `:113` |
| `MAX_CONCURRENT_ANCESTOR_PROBES` | 256 | `codex-rs/core/src/agents_md.rs:51` |
| `MAX_ADDITIONAL_CONTEXT_VALUE_TOKENS` | 1 000 | `codex-rs/context-fragments/src/additional_context.rs:6` |
| `MAX_REMOTE_COMPACTION_V2_STREAM_RETRIES` | 2 | `codex-rs/core/src/compact_remote_v2.rs:81` |
| `auto_compact_token_limit` scope | `Total` (default) \| `BodyAfterPrefix` | `codex-rs/protocol/src/config_types.rs:49-55` |

## A.3 pi (`ref_repo/pi`)

| Constant | Value | Location |
|---|---|---|
| `CHARS_PER_TOKEN` | 4 | `packages/ai/src/utils/estimate.ts:14` |
| `ESTIMATED_IMAGE_CHARS` | 4 800 | `:15` |
| `DEFAULT_MAX_LINES` | 2 000 | `packages/agent/src/harness/utils/truncate.ts:11` |
| `DEFAULT_MAX_BYTES` | 50 KiB | `:12` |
| `DEFAULT_COMPACTION_SETTINGS.reserveTokens` | 16 384 | `packages/agent/src/harness/compaction/compaction.ts:169` |
| `DEFAULT_COMPACTION_SETTINGS.keepRecentTokens` | 20 000 | `:170` |
| `TOOL_RESULT_MAX_CHARS` (summary serialization) | 2 000 | `packages/agent/src/harness/compaction/utils.ts:74` |
| `COMPACTION_SUMMARY_PREFIX` | `"…compacted into the following summary:\n\n<summary>\n"` | `packages/agent/src/harness/messages.ts:4-10` |
| `OPENAI_PROMPT_CACHE_KEY_MAX_LENGTH` | 64 | `packages/ai/src/api/openai-prompt-cache.ts:1` |
| Summary request isolation | `cacheRetention:"none"`, `sessionId: uuidv7()` | `packages/agent/src/harness/compaction/compaction.ts:118-138` |
| Assistant bridge string | `"I have processed the tool results."` | `packages/ai/src/api/openai-completions.ts:1046-1051` |
| `requiresAssistantAfterToolResult` | capability flag | `packages/ai/src/types.ts:519-574` |

## A.4 Cortex (`@animus-labs/cortex`, docs)

| Constant | Value | Source |
|---|---|---|
| `MAX_RESULT_TOKENS` (per-tool interceptor) | 25 000 | `tool-result-persistence.md` |
| `BOOKEND_CHARS` | 1 500 head + 1 500 tail | `:—` |
| `maxAggregateTurnTokens` | 150 000/turn | `:—` |
| `capToolResult` insertion ceiling | 50 000 | `:—` |
| `DEFAULT_TOOL_THRESHOLDS.Bash` | 7 500 | `:—` |
| `hotZoneMinTokens` | 16 000 | `compaction-strategy.md` |
| `hotZoneRatio` | 0.05 | `:—` |
| `degradationSpanRatio` | 0.40 | `:—` |
| `bookendMaxChars` / `bookendMinChars` | 2 000 / 256 | `:—` |
| `trimFloorRatio` | 0.25 | `:—` |
| `compaction.threshold` | 0.70 | `:—` |
| `preserveRecentTurns` | 6 | `:—` |
| `failsafe.threshold` | 0.90 | `:—` |
| `adaptive.minThreshold` / `idleMinutes` | 0.50 / 30 | `:—` |
| `activationThreshold` (observational) | 0.9 | `observational-memory-architecture.md` |
| `bufferTokenCap` / `bufferMinTokens` / `bufferTargetCycles` | 30 000 / 5 000 / 4 | `:—` |
| `reflectionThreshold` / `reflectionBufferActivation` | 0.20 / 0.5 | `:—` |
| `previousObserverTokens` | 2 000 | `:—` |
| `observerTimeoutMs` | 60 s | `:—` |
| Anthropic cache TTLs | 5 min / 1 h | `context-manager.md` |
| OpenAI cache TTLs | 10 min / 24 h | `:—` |
| Anthropic breakpoints | 4 max; ~20-block automatic lookback | `:—` |
| Slot content blocks | ≤ 20 | `:—` |
| Headline block cap | 2 000 | `:—` |
| Skill caps (Claude Code) | 5 000/skill, 25 000 total, oldest dropped, head preserved | Claude Code docs |

---

# Appendix B — dead / unwired context machinery in our codebase

| Symbol | Location | Status |
|---|---|---|
| `set_aux_tokens` / `_aux_tokens` | `context.py:130, 135-136` | Never called in production → tool-schema tokens counted as 0 |
| `SchemaResolver.schema_tokens` | `toolkit/resolver.py:112-121` | Zero production call sites |
| `estimate_tool_schema_tokens` | `toolkit/schema_metrics.py:19` | Only the startup banner and tests |
| `required_prefix_length` | `context.py:295-296` | Never called |
| `RunningSummaryScheduler.schedule` | `running_summary.py:55` | Never called → **no async running summary exists** |
| `_cache_prefix_for` / `cache_control` | `compaction_service.py:221-237` | No `cache_control` marker is ever set → always returns `[]` |
| `_find_compaction_cut` (fixed-tail) | `compaction.py:120-127` | Superseded by `_find_compaction_cut_budgeted`; tests only |
| `SimpleLoop._rebuild_messages` | `simple_loop.py:1506-1537` | Tests only |
| `_maybe_summarize_heavy_output` | `simple_loop.py:287-290` | Stub returning `None` |
| `RepoMap._snapshot` | `workspace/repo_map.py:149-172` | Never called → repo map never self-invalidates |
| `_dynamic_max_output` | `toolkit/executor.py:97-103` | Never called; `MAX_TOOL_OUTPUT_TIERS` is inert |
| `summary_threshold` (0.8) | `settings.py:161` | Config surface with no consumer |
| `CONTEXT_SUMMARY_THRESHOLD` (0.85) | `constants/context.py:12` | Re-exported only |
| `SKIP_WARNING_CAP`, `DUP_RESULT_PREVIEW_CHARS`, `STALL_FINALIZE_AFTER_ITERATIONS` | `constants/context.py:33, 41, 38` | Zero consumers |
| `SESSION_STATE_MARKER` | `constants/agent.py` | Defined, never produced |
| `Session.update_context` / `CONTEXT_UPDATED` | `domain/session.py:77`, `sessions/service.py:392` | Only reachable from the client `session.update` RPC |
| `Message.token_count`, `Message.parent_message_id` | `domain/message.py:25, 29` | Never written |
| `get_workspace_stats` / `WorkspaceStats` | `workspace/index.py` | Used only by the `bash` recursion guard; never in context |
| `Session.model_dump_for_db` | `domain/session.py:106-134` | SQLite-shaped; the store is JSONL now |
| `format_tool_digest` branches for non-glob/grep | `toolkit/digest.py:39-78` | Unreachable in production |
| `head_tail_trim` non-digest path at 1000 chars | `compaction.py:198-203` | Live, but applies to every non-glob/grep result older than 6 tool results |
| `default_max_tokens_for_context` | `constants/context.py:64` | Only `providers/registry.py` and `providers/validation.py` |
| `model_name` / `provider_name` params | `prompts.py:126-138` | Accepted and ignored; asserted by `test_prompts_template.py:108-112` |
| `PROMPT_TEMPLATE` dead variants in OpenCode | `ref_repo/opencode/.../copilot-gpt-5.txt` (14 KB), `plan-reminder-anthropic.txt` (4 KB) | Imported nowhere in their own repo |

**The pattern:** 21 unwired symbols, concentrated in exactly the areas the proposal replaces. This is an interrupted migration, not a set of independent oversights — and it is the reason there is currently **no single owner of context policy**.

---

*End of document.*
