# Intelligent Clarification — Implementation Plan

1. Define preflight decision and clarification schemas with strict validation.
2. Add clarification tables/repositories and include active state in session snapshots.
3. Implement deterministic checks for missing provider/model/workspace/target files before model-generated questions.
4. Add structured classifier/planner prompts with bounded question count and JSON validation.
5. Gate mutating tools on `READY_TO_EXECUTE`; preserve read-only discovery when explicitly safe.
6. Replace the global question callback with a workflow adapter that emits persisted events and waits on a session-scoped answer future.
7. Implement timeout, cancellation, supersession, restart, and session-switch handling.
8. Build TUI question cards and wire answers to the websocket contract.
9. Add answer reuse from current session memory, with explicit provenance and conflict handling.
