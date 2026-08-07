# UI/UX Modernization — Overview

## Objective

Make the TUI coherent, trustworthy, fast-feeling, keyboard-first, and aligned with the backend’s actual agent/session state.

## Current state

- The TUI has screens for welcome, setup, settings, usage, context, help, sessions, model/provider selection, and overlays.
- Conversation turns are held in `useConversation`; session resume receives backend messages but does not fully hydrate that store.
- Streaming events exist, but thinking/tool/progress/compaction/confirmation states are not represented with one consistent view model.
- Context and usage surfaces exist, while session statistics and execution history are incomplete.
- The product is a TUI, so graphical IDE features must be explicitly classified as future scope.

## Audit scope

Navigation, information architecture, session lifecycle, conversation rendering, streaming, code/output presentation, tool visibility, clarification, context/cost, keyboard/accessibility, resize behavior, performance, and error recovery.

## Success

Users can understand what Zenith is doing, why it needs input, what changed, how much it cost, and how to resume or recover—without reading logs or guessing hidden state.
