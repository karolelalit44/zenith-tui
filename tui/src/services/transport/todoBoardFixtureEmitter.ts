import todoBoardFixture from '../../fixtures/todo-board.json';
import type { ScenarioEvent } from '../../types/scenario';
import type { ScenarioListener, ScenarioRunner } from '../scenario/types';
import { mapRawEvent } from './rawEventMapper';

/**
 * Fixture-driven todo & subtask board simulation.
 *
 * The full board lifecycle (creation, subtask progress, status transitions,
 * priority updates, block/unblock, completion, cancellation) lives in
 * `src/fixtures/todo-board.json` and is played back through the SAME
 * `mapRawEvent` formatter used for live backend streams. Every emission
 * carries a full board snapshot, so the UI is a pure function of the latest
 * event — when a real backend emits the same shape later, nothing in the
 * renderer needs to change.
 */

interface FixtureEntry {
  kind: string;
  id?: string;
  data?: Record<string, unknown>;
  delay_ms?: number;
}

interface TodoBoardFixture {
  name?: string;
  description?: string;
  events: FixtureEntry[];
}

const fixture = todoBoardFixture as unknown as TodoBoardFixture;

const entryId = (entry: FixtureEntry, index: number): string => entry.id ?? `todo_fixture_${index}`;

/**
 * Map the entire fixture to typed ScenarioEvents exactly as a live stream
 * would, without timing. Useful for tests and for pre-computing state.
 */
export function collectTodoBoardEvents(): ScenarioEvent[] {
  return fixture.events.map((entry, index) => mapRawEvent(entry.kind, entry.data, entryId(entry, index)));
}

/**
 * Replay the fixture through the shared onEvent/onComplete contract with the
 * same per-event pacing the live backend uses. Returns a ScenarioRunner so the
 * running turn can be aborted like any other.
 */
export function emitTodoBoardFixture(onEvent: ScenarioListener, onComplete: () => void): ScenarioRunner {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let index = 0;
  let aborted = false;

  const emitNext = () => {
    if (aborted) return;
    if (index >= fixture.events.length) {
      onComplete();
      return;
    }
    const entry = fixture.events[index];
    onEvent(mapRawEvent(entry.kind, entry.data, entryId(entry, index)), index);
    index += 1;
    timer = setTimeout(emitNext, entry.delay_ms ?? 0);
  };

  timer = setTimeout(emitNext, 0);

  return {
    abort: () => {
      aborted = true;
      if (timer) clearTimeout(timer);
    },
  };
}
