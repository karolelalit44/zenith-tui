# Intelligent Clarification — Overview

## Objective

Detect incomplete, ambiguous, or risky requests and gather the minimum information required before execution.

## Current state

- A `question` tool exists with an optional process-global callback.
- No durable clarification thread/question/answer state exists.
- No preflight decision contract guarantees that mutating execution is blocked while information is missing.
- The TUI has no first-class question cards or answer-edit workflow.

## Scope and success

Persisted clarification state, structured question generation/validation, cancellation/timeout/session switching, server events, and TUI interaction. A request such as “Build authentication” must ask useful options before changing files; a sufficiently specified request must proceed without unnecessary questions.
