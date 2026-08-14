import compactionOutput from '../../fixtures/compaction-output.json';
import type { ScenarioEvent } from '../../types/scenario';
import type { ScenarioListener, ScenarioRunner } from '../scenario/types';
import { mapRawEvent } from './rawEventMapper';

/**
 * Fixture-driven compaction.
 *
 * `/compact` does not need a backend: the exact AI-model output for a manual
 * compaction turn lives in `src/fixtures/compaction-output.json` and is played
 * back through the SAME `mapRawEvent` formatter used for live backend streams.
 * This makes the frontend fully data-driven — edit the JSON, change the turn —
 * and lets tests emit the exact same events the renderer consumes.
 */

interface FixtureEntry {
  kind: string;
  id?: string;
  data?: Record<string, unknown>;
  delay_ms?: number;
}

interface CompactionFixture {
  name?: string;
  description?: string;
  events: FixtureEntry[];
}

const fixture = compactionOutput as unknown as CompactionFixture;

const entryId = (entry: FixtureEntry, index: number): string => entry.id ?? `fixture_${index}`;

/**
 * Map the entire fixture to typed ScenarioEvents exactly as a live stream
 * would, without timing. Useful for tests and for pre-computing state.
 */
export function collectFixtureEvents(): ScenarioEvent[] {
  return fixture.events.map((entry, index) => mapRawEvent(entry.kind, entry.data, entryId(entry, index)));
}

/**
 * Replay the fixture through the shared onEvent/onComplete contract with the
 * same per-event pacing the live backend uses. Returns a ScenarioRunner so the
 * running turn can be aborted like any other.
 */
export function emitCompactionFixture(onEvent: ScenarioListener, onComplete: () => void): ScenarioRunner {
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
