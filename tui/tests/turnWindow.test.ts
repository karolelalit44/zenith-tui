import { describe, expect, it } from 'vitest';
import type { ConversationTurn } from '../src/hooks/useConversation';
import { computeVisibleTurns, TURN_LINE_HEIGHT } from '../src/utils/turnWindow';

function makeTurn(id: string): ConversationTurn {
  return {
    id,
    prompt: `prompt ${id}`,
    mode: 'build',
    events: [],
    isComplete: true,
    timestamp: '00:00',
    startedAt: 0,
  };
}

const turns = Array.from({ length: 10 }, (_, i) => makeTurn(`t${i}`));
const viewportHeight = TURN_LINE_HEIGHT * 3; // 3 turns fit

describe('computeVisibleTurns — scroll is maintained during generation', () => {
  it('shows everything at the bottom when idle', () => {
    const visible = computeVisibleTurns({
      completedTurns: turns,
      isUserScrolled: false,
      isRunning: false,
      scrollOffset: 0,
      viewportHeight,
    });
    expect(visible).toHaveLength(10);
  });

  it('bounds the window to the latest turns while running at the bottom (no jitter)', () => {
    const visible = computeVisibleTurns({
      completedTurns: turns,
      isUserScrolled: false,
      isRunning: true,
      scrollOffset: 0,
      viewportHeight,
    });
    expect(visible.map((t) => t.id)).toEqual(['t7', 't8', 't9']);
  });

  it('respects a user scroll up DURING generation', () => {
    // Scrolled 5 turns up.
    const visible = computeVisibleTurns({
      completedTurns: turns,
      isUserScrolled: true,
      isRunning: true,
      scrollOffset: TURN_LINE_HEIGHT * 2, // window starts at turn 2
      viewportHeight,
    });
    expect(visible[0].id).toBe('t2');
    expect(visible.length).toBeGreaterThan(0);
  });

  it('clamps the window to the available turns when scrolled past the end', () => {
    const visible = computeVisibleTurns({
      completedTurns: turns,
      isUserScrolled: true,
      isRunning: true,
      scrollOffset: TURN_LINE_HEIGHT * 100,
      viewportHeight,
    });
    expect(visible).toHaveLength(0);
  });

  it('handles an empty conversation', () => {
    const visible = computeVisibleTurns({
      completedTurns: [],
      isUserScrolled: false,
      isRunning: true,
      scrollOffset: 0,
      viewportHeight,
    });
    expect(visible).toHaveLength(0);
  });
});
