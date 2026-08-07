# Persistent Sessions — Overview

## Objective

Reopen any saved session as if it never ended: complete conversation, tool/execution history, context state, pending workflows, and accurate statistics must be restored together.

## Current state

- Sessions and messages are persisted through repositories and a session service.
- Checkpoints, sync events, status history, drafts, token usage, and session metadata already exist in partial form.
- `session.resume` returns messages and replayable events, but the TUI resume path does not fully hydrate those messages into `useConversation`.
- Message events and tool calls are embedded in message/event payloads rather than normalized execution records.
- Session summaries expose only a subset of statistics.

## Scope and success

- Versioned full-session snapshot and restoration protocol.
- Durable execution, context, clarification, and compaction state.
- Migration/export of existing SQLite sessions.
- Server-authoritative statistics and frontend session detail model.
- Reconnect-safe event replay and idempotent commands.

Success means restart, reconnect, archive/restore, and resume preserve visible conversation and executable workflow state with no duplicate side effects.
