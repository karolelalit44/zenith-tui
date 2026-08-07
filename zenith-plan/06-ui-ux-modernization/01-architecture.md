# UI/UX Modernization — Architecture

## View-model design

Build the TUI from a normalized `SessionSnapshot` plus an event reducer:

```text
SessionViewModel
  session, turns[], execution_timeline[], artifacts[]
  context_usage, token_usage, compaction_state
  clarification_thread?, connection_state, errors[]
```

The reducer must be idempotent by event ID/sequence and preserve a bounded local cache while older artifacts/messages load on demand.

## Primary surfaces

- Conversation: user/assistant messages, code blocks, attachments, edits, retry, and final status.
- Agent timeline: thinking, capability selection, tool calls/results, approvals, retries, tests, and sub-agents.
- Session browser/detail: search, metadata, stats, last activity, pending work, and restore state.
- Context/usage: current window, remaining budget, token/cost breakdown, compaction history.
- Clarification cards: options, free text, validation, edits, cancellation, and session persistence.
- Workspace artifacts: changed files, diffs, test results, logs, and references.

## Interaction rules

- Server events are authoritative; optimistic UI is limited to input acknowledgement.
- Every long action has pending, success, failure, cancellation, and retry states.
- Destructive actions show scope and approval state.
- Keyboard shortcuts, focus order, color-independent status, and terminal resize behavior are specified per component.
