import { afterEach, describe, expect, it, vi } from 'vitest';
import { collectTodoBoardEvents, emitTodoBoardFixture } from '../src/services/transport/fixtureEmitter';
import type { ScenarioEvent, TodoBoardEvent, TodoItem } from '../src/types/scenario';

/**
 * The todo board pipeline is fully data-driven: a single JSON fixture
 * holds the complete todo & subtask lifecycle (create → update → complete →
 * cancel), a shared emitter replays it, and the renderer consumes the same
 * typed events. These tests run the SAME emitter path that the fixture
 * specifies.
 */

afterEach(() => {
  vi.useRealTimers();
});

const boardOf = (event: ScenarioEvent): TodoBoardEvent['board'] | undefined =>
  event.kind === 'todo_board' ? event.board : undefined;

describe('collectTodoBoardEvents', () => {
  it('maps the fixture to the exact event sequence the UI will receive', () => {
    const events = collectTodoBoardEvents();
    expect(events.map((e) => e.kind)).toEqual([
      'todo_board',
      'todo_board',
      'todo_board',
      'todo_board',
      'todo_board',
      'todo_board',
      'todo_board',
      'todo_board',
      'todo_board',
      'todo_board',
      'todo_board',
    ]);
  });

  it('drives the full create → update → complete lifecycle across actions', () => {
    const events = collectTodoBoardEvents();
    const actions = events.map((e) => (e.kind === 'todo_board' ? e.action : ''));
    expect(actions).toEqual([
      'snapshot',
      'created',
      'updated',
      'updated',
      'updated',
      'updated',
      'updated',
      'updated',
      'updated',
      'updated',
      'completed',
    ]);
  });

  it('carries the full board snapshot on every emission (data-driven UI contract)', () => {
    const events = collectTodoBoardEvents();
    for (const event of events) {
      if (event.kind === 'todo_board') {
        expect(Array.isArray(event.board)).toBe(true);
        expect(event.board.length).toBeGreaterThan(0);
      }
    }
  });

  it('starts from a 4-item board and grows to 5 on creation', () => {
    const [first, second] = collectTodoBoardEvents() as TodoBoardEvent[];
    expect(boardOf(first)).toHaveLength(4);
    expect(boardOf(second)).toHaveLength(5);
  });

  it('terminates with 4 done, 1 cancelled and no blocked/in-progress work', () => {
    const last = collectTodoBoardEvents()
      .filter((e): e is TodoBoardEvent => e.kind === 'todo_board')
      .at(-1);
    const board = last?.board ?? ([] as TodoItem[]);
    const statuses = board.map((i) => i.status);
    expect(statuses.filter((s) => s === 'done')).toHaveLength(4);
    expect(statuses.filter((s) => s === 'cancelled')).toHaveLength(1);
    expect(statuses.filter((s) => s === 'blocked')).toHaveLength(0);
    expect(statuses.filter((s) => s === 'in_progress')).toHaveLength(0);
  });

  it('tracks created/updatedAt timestamps so the UI can show recency', () => {
    const last = collectTodoBoardEvents()
      .filter((e): e is TodoBoardEvent => e.kind === 'todo_board')
      .at(-1);
    for (const item of last?.board ?? []) {
      expect(item.createdAt).toBeGreaterThan(0);
      expect(item.updatedAt).toBeGreaterThanOrEqual(item.createdAt);
    }
  });
});

describe('emitTodoBoardFixture', () => {
  it('replays every fixture event then completes', async () => {
    vi.useFakeTimers();
    const received: ScenarioEvent[] = [];
    let completed = false;
    const runner = emitTodoBoardFixture(
      (event) => {
        received.push(event);
      },
      () => {
        completed = true;
      },
    );

    await vi.advanceTimersByTimeAsync(60_000);
    runner.abort();

    expect(completed).toBe(true);
    expect(received).toHaveLength(collectTodoBoardEvents().length);
    expect(received[0]).toMatchObject({ kind: 'todo_board', action: 'snapshot' });
    expect(received[received.length - 1]).toMatchObject({ kind: 'todo_board', action: 'completed' });
  });

  it('aborts a partially replayed fixture', async () => {
    vi.useFakeTimers();
    const received: ScenarioEvent[] = [];
    const runner = emitTodoBoardFixture((event) => {
      received.push(event);
    }, vi.fn());

    await vi.advanceTimersByTimeAsync(700);
    runner.abort();
    await vi.advanceTimersByTimeAsync(60_000);

    expect(received.length).toBeGreaterThan(0);
    expect(received.length).toBeLessThan(collectTodoBoardEvents().length);
  });

  it('emitted events are identical whether collected or played back', async () => {
    vi.useFakeTimers();
    const collected = collectTodoBoardEvents();
    const played: ScenarioEvent[] = [];
    let completed = false;

    emitTodoBoardFixture(
      (event) => {
        played.push(event);
      },
      () => {
        completed = true;
      },
    );
    await vi.advanceTimersByTimeAsync(60_000);

    expect(completed).toBe(true);
    expect(played.map((e) => e.kind)).toEqual(collected.map((e) => e.kind));
    for (const [i, event] of played.entries()) {
      if (event.kind === 'todo_board' && collected[i].kind === 'todo_board') {
        expect(event.board).toEqual(collected[i].board);
      }
    }
  });
});
