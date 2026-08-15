# Architectural Analysis, Root Cause Analysis (RCA) & Implementation Strategy

---

## 1. Tool Output Bloat & Token Overrun

### A. `glob` & `grep` Search Output Explosion
- **Issue:**
  Broad searches such as recursive `glob("**/*")`, repository-wide `grep`, or unconstrained pattern matching return thousands of paths or lines in a single tool response. Individual responses exceed 24k–27k characters (~6k–7k tokens), consuming a significant portion of the context window in one operation and causing context exhaustion within 1–2 iterations.
- **Root Cause Analysis (RCA):**
  - Search operations are optimized for completeness rather than LLM context efficiency.
  - No mandatory result-count, byte-size, or token-size budget exists at the tool boundary.
  - Recursive searches do not consistently prioritize high-signal directories or file types.
  - Generated artifacts and dependency directories (`node_modules`, `.git`, `dist`, `__pycache__`) dominate results while providing no diagnostic value.
  - Raw tool output is persisted in conversation history, so oversized results continue consuming context across all subsequent turns.
  - There is no feedback loop that automatically tightens an overly broad query after detecting excessive output.
- **Correct Approach & Expected Behavior:**
  - **Bounded Search by Default:** Enforce an explicit maximum result count and output-size budget on every search (default: 50–100 items).
  - **Progressive Narrowing:** Start with repository structure and high-signal directories, then progressively narrow by subpath, file type, symbol, or pattern.
  - **Structural Summaries First:** For broad queries, return a compact directory tree, file counts, and representative paths rather than thousands of raw paths.
  - **Relevance Ranking & Exclusions:** Exclude `node_modules`, `.git`, `.svn`, `__pycache__`, `.venv`, `dist`, `build`, coverage, binaries, and lockfiles by default unless explicitly requested.
  - **Explicit Truncation Notice:** Report both returned and total matches (e.g., `Showing 50 of 640 matches. Narrow the search with a subpath or file filter.`).
  - **Adaptive Fallback:** If a search exceeds its output budget, return a compact summary with refinement suggestions instead of dumping the oversized raw payload.
  - **Target Guardrails:**
    - Default result limit: 50–100 items.
    - Hard output ceiling: ~8–12 KB per search response.
    - Preferred output: <2–3 KB for exploratory searches.

---

### B. `file_read` Large File Dumps
- **Issue:**
  Reading entire source files injects thousands of tokens into the context even when the model only needs a specific function, class, configuration section, or line range. Multiple full-file reads compound the problem and crowd out actual reasoning context.
- **Root Cause Analysis (RCA):**
  - `file_read` treats the whole file as the unit of retrieval instead of the relevant code region.
  - There is no symbol-aware or intent-aware retrieval layer before full-file reads.
  - Large files are repeatedly re-read even when only a small section has changed.
  - Unchunked tool responses remain in conversation history after useful information has already been extracted.
- **Correct Approach & Expected Behavior:**
  - **Outline / Symbol-First Retrieval:** Begin with file metadata, headings, symbols, exports, classes, functions, and relevant line ranges.
  - **Targeted Reads:** Read only the smallest section required to answer the current question or make the current change.
  - **Line-Based Chunking:** Enforce `start_line` + bounded `limit` semantics for large files (prefer <200–400 lines per request).
  - **Context Expansion on Demand:** Expand the read window only when the selected section lacks required context.
  - **Change-Aware Reads:** When investigating modifications, prioritize changed lines and immediate dependencies instead of rereading the complete file.
  - **Context Trimming:** Convert large retrieved sections into compact working notes in the active reasoning buffer rather than carrying raw full files across later turns.

---

### C. `file_write` / `file_edit` Payload Duplication
- **Issue:**
  File creation and editing duplicate large content in the conversation: the complete file is sent as a tool argument, and then the tool returns a verbose representation of the same content. For documents such as `plan.md`, this injects the same payload twice and preserves both copies across subsequent iterations.
- **Root Cause Analysis (RCA):**
  - Write APIs accept large raw payloads without minimizing the returned response.
  - Tool results echo file contents even though the operation itself already supplied the content.
  - Conversation history retains large write arguments after the operation succeeds.
  - Incremental edits are sometimes implemented as full-file replacements.
- **Correct Approach & Expected Behavior:**
  - **Minimal Write Responses:** Return metadata only after successful writes (e.g., `Successfully updated plan.md — 4.8 KB, 30 lines, hash: <short-hash>`).
  - **Never Echo Written Content by Default:** Tool results must not reproduce the file body.
  - **Patch-Based Editing:** Prefer targeted replacements and structured edits over sending entire files for small changes.
  - **Historical Compaction:** Once a write succeeds, replace large write payloads in working context with compact references.
  - **Verification by Metadata:** Validate existence, size, line count, and checksums without rereading the entire file unless semantic verification is required.
  - **Target Guardrails:**
    - Default write-result size: <1 KB.
    - Zero content echo on successful writes.

---

### D. Cross-Tool Context Accumulation & Retrieval Hierarchy
- **Issue:**
  Even when individual tool responses are reasonable, repeated search → read → edit → reread loops accumulate historical content across the full task, exhausting context at the workflow level.
- **Root Cause Analysis (RCA):**
  - Context usage is measured per tool response rather than across the complete task budget.
  - Old tool outputs remain in active context after information has been superseded.
  - There is no context budget allocated between exploration, reasoning, implementation, and verification.
- **Correct Approach & Expected Behavior:**
  - **Context Budgeting:** Treat context as a finite resource, reserving headroom for reasoning, implementation, and verification.
  - **Recommended Retrieval Hierarchy (Lowest-Cost Path):**
    1. Repository metadata
    2. Compact directory structure
    3. Targeted `glob` (scoped path)
    4. Bounded `grep` (specific symbol/keyword)
    5. File outline / symbols
    6. Targeted line-range read (`start_line`, `limit`)
    7. Relevant dependency inspection
    8. Implementation / patch edit
    9. Focused verification
    10. Final compact summary
  - **Working-Set Model:** Maintain an active working set of relevant files, symbols, findings, and decisions rather than retaining every retrieved raw artifact.

---

### E. Telemetry, Observability & Guardrails
- **Correct Approach & Expected Behavior:**
  - **Instrument Every Retrieval Tool:** Track result count, byte size, estimated tokens, execution time, and truncation status.
  - **Warning & Hard Thresholds:** Warn before an output becomes context-expensive; hard-cap single tool outputs before context exhaustion.
  - **Automated Recovery:** Replace oversized outputs with summaries and actionable narrowing guidance.
  - **Efficiency Metrics:** Track tokens returned per useful match, duplicate-content ratio, and average search-result size.

---

## 2. Quadratic Context Accumulation in Live Agent Loop

- **Issue:**
  The agent loop exhibits quadratic token growth ($O(N^2)$). For every step in a single turn, the complete cumulative history of all previous tool calls and outputs is re-sent to the LLM. In typical multi-step execution, prompt size rapidly grows from 4k characters in Turn 1 to 63k characters / 33.5k prompt tokens by Turn 6, totaling 113.9k tokens across 8 iterations.
- **Root Cause Analysis (RCA):**
  - `server/agents/loop.py` continuously appends raw tool calls and outputs directly to `messages`.
  - Historical tool output is treated as permanent context even after its useful information has been consumed.
  - No distinction exists between durable conversation history, active working state, and ephemeral execution logs.
  - No per-turn token budget or rolling compaction threshold exists.
- **Correct Architecture & Expected Behavior:**
  - **Conversation History:** Retain only durable user/assistant interaction required for high-level continuity.
  - **Rolling Working State:** Store compact facts, discoveries, decisions, errors, relevant files, and pending actions.
  - **Ephemeral Tool Window:** Retain full detail only for the latest 1–2 tool results.
  - **Compacted Tool Digests:** Convert older tool results into short structured digests:
    ```text
    [glob] Found 12 relevant files under server/agents/.
    [grep] `messages.append` used in loop.py:142.
    [read] loop.py confirms raw tool results persist in active history.
    ```
  - **Execution Logs:** Keep detailed execution traces in backend logs, outside the active LLM prompt.
- **Compaction Strategy & Guardrails:**
  - Calculate estimated prompt tokens before every LLM call.
  - If context exceeds the configured threshold, compact older tool messages first.
  - Preserve user requirements, current task state, important discoveries, errors, relevant symbols, and unresolved decisions.
  - Summarize or remove duplicate tool output, obsolete search results, verbose logs, and unchanged file contents.
  - Ensure total context growth approaches $O(N)$ rather than $O(N^2)$.

---

## 3. Ineffective Automatic Compaction (`113.9k → 113.9k`, 0 Tokens Saved)

### A. Compaction Targets the Wrong Data (History vs. Active In-Flight Messages)
- **Issue:**
  Compaction triggers when context exceeds 80–90%, but saves 0 tokens (`113.9k → 113.9k tokens`).
- **Root Cause Analysis (RCA):**
  - `_maybe_summarize` in `server/agents/loop.py` operates on persisted `history` (which had only 1 message in this session).
  - The actual 113.9k token bloat exists in active in-flight tool calls and results inside `messages`, which remain untouched.
- **Correct Approach & Expected Behavior:**
  - Compact the exact `messages` payload that will be sent to the LLM.
  - Treat persisted database history and active-turn in-flight context as distinct compaction domains.
  - Summarize intermediate tool calls/results in active memory while preserving user intent and critical state.

---

### B. `_rebuild_messages` Re-Appends the Uncompressed `live_tail`
- **Issue:**
  After summarization executes, the context size remains unchanged in subsequent iterations.
- **Root Cause Analysis (RCA):**
  - `live_tail = messages[base_len:]` contains the active turn's large tool results.
  - `_rebuild_messages` re-appends `live_tail` in full directly into `rebuilt`, immediately restoring the exact 60k+ characters of uncompressed tool results that caused context pressure.
- **Correct Approach & Expected Behavior:**
  - Compact and prune `live_tail` before attaching it to `rebuilt`.
  - Never re-append raw tool outputs that exceed the configured per-tool token budget.
  - Recalculate token size after rebuilding; if still over budget, apply secondary compaction before sending to the LLM.

---

### C. `_prune_tool_outputs` Ignores the Current Turn
- **Issue:**
  Tool output pruning does not activate during long multi-step single-turn executions.
- **Root Cause Analysis (RCA):**
  - `_prune_tool_outputs` determines age using user-turn boundaries (`turns > keep_turns = 2`).
  - During the first user turn, `turns == 1`, so `boundary == 0`. Current-turn tool outputs are considered too recent and remain completely unpruned regardless of size.
- **Correct Approach & Expected Behavior:**
  - Track message age and character volume within the *current* turn, not only user-turn count.
  - Prune tool results based on age within the iteration sequence, character/token count, and total active-turn context size.

---

### D. Budget-Driven Compaction Flow
```text
Build messages
    ↓
Measure actual prompt tokens
    ↓
Over budget?
    ↓ (yes)
Compact active tool results
    ↓
Prune/summarize live_tail
    ↓
Rebuild messages
    ↓
Measure again
    ↓
Still over budget? → secondary compaction
    ↓
Send only when within budget
```
- **Guardrails:**
  - Measure the final LLM payload, not database history.
  - Never allow `_rebuild_messages` to reintroduce pruned content.
  - Report `before_tokens`, `after_tokens`, `tokens_saved`, and `messages_compacted`.
  - If `tokens_saved == 0`, compaction is marked as failed/retry required.

---

## 4. Automatic Compaction UI vs. `/compact` UI Discrepancy

### A. Duplicate Raw Warning Events
- **Issue:**
  Automatic compaction renders noisy raw warning lines (`↳ Context approaching limit (89%), summarizing...`, `↳ Context summarized`, `↳ Context summarized, continuing`) instead of the unified compaction card.
- **Root Cause Analysis (RCA):**
  - `server/agents/loop.py` emits multiple `r.warning` events alongside structured compaction events.
  - `WarningBlock` renders each warning independently, creating duplicate UI clutter before and after the compaction card.
- **Correct Approach & Expected Behavior:**
  - Remove/suppress raw warning events during automatic compaction.
  - Use only structured compaction lifecycle events so the TUI renders a single, clean `CompactionFlowBlock` card.
  - Keep verbose warning details in backend logs and telemetry rather than user-facing terminal rows.

---

### B. Missing `context_compaction_phase` Events
- **Issue:**
  Automatic compaction lacks the animated stage-by-stage progression checklist (`preserving` -> `compacting` -> `verifying`) displayed by manual `/compact`.
- **Root Cause Analysis (RCA):**
  - `loop.py` omitted `context_compaction_phase` events during automatic compaction, preventing the UI from transitioning through its phases.
- **Correct Approach & Expected Behavior:**
  - Standardize automatic and manual compaction around the exact same event contract:
    1. `context_compaction_started` (initial token count, context capacity, trigger/reason)
    2. `context_compaction_phase` (`preserving` -> `compacting` -> `verifying`)
    3. `context_compacted` (per-tool savings breakdown, tokens before/after, tokens saved)
    4. `context_compaction_ended` (final token count, total savings, final status)

---

### C. Single Source of Truth for Compaction Lifecycle
- **Issue:**
  Automatic and `/compact` paths implement divergent event logic, producing inconsistent UX.
- **Root Cause Analysis (RCA):**
  - Compaction lifecycle logic is duplicated between handler RPC endpoints and agent loop internals.
- **Correct Approach & Expected Behavior:**
  - Use one shared compaction lifecycle helper/emitter for both automatic and manual `/compact`.
  - Only trigger metadata should differ (`reason: "automatic"` vs `reason: "manual"`).
  - Share the same `CompactionFlowBlock`, phase names, payload schema, and completion behavior.

---

## 5. Definition of Done (DoD)

1. **Tool Safety:**
   - No default repository search (`glob`, `grep`) can return an unbounded response (>8–12 KB).
   - No default file read can dump an arbitrarily large file without line limits.
   - Write and edit operations never echo file contents on success.
2. **Context Stability:**
   - Active-turn tool output is retained in full detail only for the latest 1–2 results; older results are automatically digested.
   - Live prompt growth remains near-linear $O(N)$ rather than quadratic $O(N^2)$.
3. **Measurable Compaction:**
   - Active-turn tool bloat inside `live_tail` is pruned and summarized.
   - Compaction produces verifiable token reductions (`before_tokens > after_tokens`, `tokens_saved > 0`).
   - Rebuilt messages never re-inject pruned content.
4. **Unified UX:**
   - Automatic compaction renders the exact same animated card (`CompactionFlowBlock`) as `/compact`.
   - Zero raw warning lines (`↳ Context approaching limit...`) are emitted into the terminal during compaction.
   - All 4 lifecycle events (`started`, `phase`, `compacted`, `ended`) are emitted consistently across automatic and manual compaction.