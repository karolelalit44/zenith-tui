/**
 * One coordinate system for the live transcript scroll.
 *
 * The scroll state counts LINES (an estimate of the rendered transcript); the
 * renderer windows EVENTS. Previously each side converted independently — App
 * mapped a line offset through a ratio computed over `events.filter(...)` while
 * the renderer sliced the post-fold, post-pairing `visibleEvents` — so the two
 * disagreed about what they were counting and the ratio was applied to a
 * different array than the one being sliced.
 *
 * Both now derive from the same nominal per-event line cost and the same total,
 * so a line offset maps to exactly one event index.
 */

/** Nominal rendered height of a single non-message event row (header + padding). */
export const EVENT_LINE_COST = 3;

export interface EventStreamHeightInput {
  /** Lines occupied by the streaming assistant message, if any. */
  messageLineCount: number;
  /** Count of every event that is not a message row. */
  nonMessageEventCount: number;
}

export function estimateEventStreamHeight({ messageLineCount, nonMessageEventCount }: EventStreamHeightInput): number {
  return Math.max(messageLineCount, 1) + nonMessageEventCount * EVENT_LINE_COST;
}

/**
 * The event index the viewport should start at for a given line offset.
 *
 * `undefined` in, `undefined` out: "not user-scrolled" must stay distinguishable
 * from "scrolled to the very top", because the former pins to the newest events
 * and the latter pins to the oldest.
 */
export function lineOffsetToEventStart(
  scrollLines: number | undefined,
  totalHeight: number,
  viewportHeight: number,
  eventCount: number,
): number | undefined {
  if (scrollLines === undefined) return undefined;
  const maxLineOffset = Math.max(0, totalHeight - viewportHeight);
  const linesFromBottom = Math.max(0, totalHeight - (scrollLines + viewportHeight));
  // Both extremes: how many events lie above the viewport's top edge.
  const eventsFromBottom = Math.floor(linesFromBottom / EVENT_LINE_COST);
  const eventStart = eventCount - eventsFromBottom - Math.ceil(viewportHeight / EVENT_LINE_COST);
  if (maxLineOffset <= 0) return 0;
  return Math.max(0, Math.min(Math.max(0, eventCount - 1), eventStart));
}
