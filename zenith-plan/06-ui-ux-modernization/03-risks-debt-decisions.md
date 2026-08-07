# UI/UX Modernization — Risks, Debt, and Decisions

## Risks

- Rendering every raw event or large tool output can freeze the terminal.
- Color-only status cues fail accessibility and monochrome terminals.
- Local optimistic state can disagree with replayed server events.
- Competitor parity can expand scope from TUI to full IDE without a product decision.
- Streaming partial messages can cause flicker, duplicate text, or scroll jumps.

## Decisions

- Use a single typed event reducer and server snapshot as source of truth.
- Virtualize or paginate large timelines and load artifacts by reference.
- Pair color with labels/icons/text and maintain keyboard-only operation.
- Define TUI parity separately from graphical IDE parity.
- Treat “thinking” as a bounded status indicator; never expose hidden chain-of-thought.

## Debt

- Frontend types do not cover the complete backend session/statistics model.
- `useConversation` owns behavior that belongs in a persisted session projection.
- Manual compact rendering is synthetic and must be removed after server compaction is wired.
