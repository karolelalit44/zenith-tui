# Context and Token Optimization — Implementation Plan

## Stage 1: Measurement and budget model

- Define canonical model capabilities: context window, max output, tokenizer, tool overhead, cache support, and reasoning usage.
- Capture the existing context composition and provider usage for benchmark sessions.
- Replace cumulative-provider usage as a proxy for current request size with request-scoped accounting.

## Stage 2: Context plan

- Extract context construction from the agent loop into a pure, testable assembler.
- Persist the context plan metadata for every provider request.
- Preserve complete user/assistant/tool groups when selecting history.
- Add explicit omission/truncation reasons.

## Stage 3: Structured memory and retrieval

- Define memory kinds: goal, constraint, decision, preference, file, command, test result, failure, pending action, and environment fact.
- Build extraction after completed turns and compaction, with provenance and supersession.
- Implement FTS retrieval over messages, summaries, and memory items.
- Add pin/unpin and forget controls before enabling cross-session memory injection.

## Stage 4: Summary hierarchy

- Persist turn summaries, rolling session summaries, and optional project-level memory separately.
- Track exactly which message range each summary covers.
- Update summaries incrementally and prevent summaries from recursively drifting without source checks.

## Stage 5: Cost and latency optimization

- Cache stable prompt prefixes when supported.
- Deduplicate unchanged repo maps/context files by content hash.
- Load file excerpts and large tool results by reference.
- Add budget policies per model, session, and workload type.

## Stage 6: Evaluation

- Build long-conversation fixtures containing delayed references, changed decisions, repeated errors, and large tool outputs.
- Compare full-history, recent-tail, summary-only, FTS, and hybrid approaches for factual retention, task success, tokens, cost, and latency.
