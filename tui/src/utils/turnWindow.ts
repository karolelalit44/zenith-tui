import type { ConversationTurn } from '../hooks/useConversation';

/** Estimated rendered lines per conversation turn (used for scroll mapping). */
export const TURN_LINE_HEIGHT = 15;

export interface TurnWindowInput {
  completedTurns: ConversationTurn[];
  isUserScrolled: boolean;
  isRunning: boolean;
  scrollOffset: number;
  viewportHeight: number;
}

/**
 * Computes which completed turns to render given the scroll state.
 *
 * - At the bottom (auto-follow): show everything when idle so history
 *   accumulates in the terminal; while running, keep the window bounded to the
 *   most recent turns so the live block stays pinned and the layout never
 *   reflows/trims the top (the source of scroll jitter during generation).
 * - Scrolled up: this works during generation too — show the window around the
 *   scroll offset. `contentHeight` tracks completed turns only, so the offset
 *   maps cleanly onto turn indices.
 */
export function computeVisibleTurns({
  completedTurns,
  isUserScrolled,
  isRunning,
  scrollOffset,
  viewportHeight,
}: TurnWindowInput): ConversationTurn[] {
  const viewportTurns = Math.max(1, Math.floor(viewportHeight / TURN_LINE_HEIGHT));

  if (!isUserScrolled) {
    if (isRunning && completedTurns.length > viewportTurns) {
      return completedTurns.slice(-viewportTurns);
    }
    return completedTurns;
  }

  const startIdx = Math.floor(scrollOffset / TURN_LINE_HEIGHT);
  const endIdx = Math.min(completedTurns.length, startIdx + viewportTurns + 2);
  return completedTurns.slice(Math.max(0, startIdx), endIdx);
}
