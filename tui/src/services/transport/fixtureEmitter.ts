import compactionOutput from '../../fixtures/compaction-output.json';
import todoBoardFixture from '../../fixtures/todo-board.json';
import type { ScenarioEvent } from '../../types/scenario';
import type { ScenarioListener, ScenarioRunner } from '../scenario/types';
import { mapRawEvent } from './rawEventMapper';

/**
 * Fixture-driven playback.
 *
 * `/compact` and the todo-board simulation do not need a backend: the exact
 * event streams live in `src/fixtures/*.json` and are played back through the
 * SAME `mapRawEvent` formatter used for live backend streams. Edit the JSON,
 * change the turn — tests emit the exact same events the renderer consumes.
 */

interface FixtureEntry {
  kind: string;
  id?: string;
  data?: Record<string, unknown>;
  delay_ms?: number;
}

interface FixtureFile {
  name?: string;
  description?: string;
  events: FixtureEntry[];
}

interface FixtureContract {
  collect: () => ScenarioEvent[];
  emit: (onEvent: ScenarioListener, onComplete: () => void) => ScenarioRunner;
}

function createFixtureEmitter(file: FixtureFile, prefix: string): FixtureContract {
  const entryId = (entry: FixtureEntry, index: number): string => entry.id ?? `${prefix}_${index}`;

  return {
    /** Map the entire fixture to typed ScenarioEvents without timing. */
    collect: () => file.events.map((entry, index) => mapRawEvent(entry.kind, entry.data, entryId(entry, index))),

    /** Replay the fixture through the shared onEvent/onComplete contract. */
    emit: (onEvent, onComplete) => {
      let timer: ReturnType<typeof setTimeout> | null = null;
      let index = 0;
      let aborted = false;

      const emitNext = () => {
        if (aborted) return;
        if (index >= file.events.length) {
          onComplete();
          return;
        }
        const entry = file.events[index];
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
    },
  };
}

const compaction = createFixtureEmitter(compactionOutput as unknown as FixtureFile, 'fixture');
export const collectFixtureEvents = compaction.collect;
export const emitCompactionFixture = compaction.emit;

const todoBoard = createFixtureEmitter(todoBoardFixture as unknown as FixtureFile, 'todo_fixture');
export const collectTodoBoardEvents = todoBoard.collect;
export const emitTodoBoardFixture = todoBoard.emit;
