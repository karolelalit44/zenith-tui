/**
 * The live-transcript scroll must be ONE coordinate system.
 *
 * `useScrollState` counts lines; the renderer windows events. These tests pin the
 * conversion in both directions, because the previous design mapped a line offset
 * through a ratio computed over a *different* array than the one being sliced.
 */
import { describe, expect, it } from 'vitest';
import { EVENT_LINE_COST, estimateEventStreamHeight, lineOffsetToEventStart } from '../src/utils/scrollWindow';

describe('estimateEventStreamHeight', () => {
  it('charges the nominal line cost per non-message event', () => {
    expect(estimateEventStreamHeight({ messageLineCount: 0, nonMessageEventCount: 4 })).toBe(1 + 4 * EVENT_LINE_COST);
  });

  it('never reports an empty stream as zero lines', () => {
    expect(estimateEventStreamHeight({ messageLineCount: 0, nonMessageEventCount: 0 })).toBe(1);
  });

  it('takes the longer of the message height and one line', () => {
    expect(estimateEventStreamHeight({ messageLineCount: 9, nonMessageEventCount: 0 })).toBe(9);
  });
});

describe('lineOffsetToEventStart', () => {
  const totalHeight = 1 + 20 * EVENT_LINE_COST;
  const viewportHeight = 2 * EVENT_LINE_COST;

  it('pins to the newest events when there is no scroll offset', () => {
    expect(lineOffsetToEventStart(undefined, totalHeight, viewportHeight, 20)).toBeUndefined();
  });

  it('distinguishes scrolled-to-top from not-scrolled', () => {
    expect(lineOffsetToEventStart(0, totalHeight, viewportHeight, 20)).toBe(0);
  });

  it('pins to the newest events when scrolled to the bottom', () => {
    const maxLineOffset = totalHeight - viewportHeight;
    const start = lineOffsetToEventStart(maxLineOffset, totalHeight, viewportHeight, 20);
    expect(start).toBe(20 - viewportHeight / EVENT_LINE_COST);
  });

  it('moves the window monotonically as the offset grows', () => {
    const maxLineOffset = totalHeight - viewportHeight;
    const quarter = lineOffsetToEventStart(Math.floor(maxLineOffset / 4), totalHeight, viewportHeight, 20)!;
    const half = lineOffsetToEventStart(Math.floor(maxLineOffset / 2), totalHeight, viewportHeight, 20)!;
    const threeQuarter = lineOffsetToEventStart(Math.floor((maxLineOffset * 3) / 4), totalHeight, viewportHeight, 20)!;
    expect(quarter).toBeLessThan(half);
    expect(half).toBeLessThan(threeQuarter);
  });

  it('never returns a negative or out-of-range index', () => {
    for (const offset of [-50, 0, 1, 17, 1000]) {
      const start = lineOffsetToEventStart(offset, totalHeight, viewportHeight, 20)!;
      expect(start).toBeGreaterThanOrEqual(0);
      expect(start).toBeLessThan(20);
    }
  });

  it('returns 0 when nothing overflows', () => {
    const shortHeight = 3;
    expect(lineOffsetToEventStart(1, shortHeight, viewportHeight, 2)).toBe(0);
  });
});
