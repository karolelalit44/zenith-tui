import { render } from 'ink-testing-library';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ScenarioRenderer } from '../src/components/Display/Scenario/ScenarioRenderer';
import { collectTodoBoardEvents, emitTodoBoardFixture } from '../src/services/transport/todoBoardFixtureEmitter';
import { ThemeProvider } from '../src/theme/ThemeContext';
import type { ScenarioEvent } from '../src/types/scenario';
import { upsertEvent } from '../src/utils/eventUpsert';
import { consolidateTodoBoardEvents } from '../src/utils/todoBoard';

/**
 * End-to-end coverage of the todo & subtask board simulation.
 *
 * Runs the fixture emitter path: every lifecycle event replays through the
 * shared upsert/consolidate/render pipeline, and the board card renders the
 * final snapshot.
 */

afterEach(() => {
  vi.useRealTimers();
});

async function replayAllThroughEmitter(): Promise<ScenarioEvent[]> {
  vi.useFakeTimers();
  const received: ScenarioEvent[] = [];
  let done = false;
  emitTodoBoardFixture(
    (event) => {
      received.push(event);
    },
    () => {
      done = true;
    },
  );
  await vi.advanceTimersByTimeAsync(60_000);
  expect(done).toBe(true);
  return received;
}

describe('E2E: todo board full pipeline', () => {
  it('emits the lifecycle through the shared pipeline and renders the completed board', async () => {
    const emitted = await replayAllThroughEmitter();
    expect(emitted.length).toBe(collectTodoBoardEvents().length);

    let state: ScenarioEvent[] = [];
    emitted.forEach((event, index) => {
      state = upsertEvent(state, event, index);
    });

    const consolidated = consolidateTodoBoardEvents(state);
    expect(consolidated?.activity).toHaveLength(6);
    expect(consolidated?.activity.at(-1)?.action).toBe('completed');

    const { lastFrame } = render(
      <ThemeProvider>
        <ScenarioRenderer events={state} isRunning={false} thinkingCollapsed={false} />
      </ThemeProvider>,
    );
    const frame = lastFrame();

    // Completed board state
    expect(frame).toContain('SIMULATION COMPLETE');
    expect(frame).toContain('Add CI pipeline to the repo');
    // Slim window: no activity log, counts, or subtasks
    expect(frame).not.toContain('▶ ACTIVITY LOG');
    expect(frame).not.toContain('Unblocked #T4');
    expect(frame).not.toContain('Wire CI status into App dashboard');
  });

  it('renders the live in-progress board mid-simulation', async () => {
    vi.useFakeTimers();
    const received: ScenarioEvent[] = [];
    emitTodoBoardFixture((event) => {
      received.push(event);
    }, vi.fn());
    await vi.advanceTimersByTimeAsync(700);

    let state: ScenarioEvent[] = [];
    received.forEach((event, index) => {
      state = upsertEvent(state, event, index);
    });

    const { lastFrame } = render(
      <ThemeProvider>
        <ScenarioRenderer events={state} isRunning={true} thinkingCollapsed={false} />
      </ThemeProvider>,
    );
    const frame = lastFrame();

    expect(frame).toContain('TODO BOARD');
    expect(frame).toContain('LIVE SIMULATION');
    expect(frame).toContain('Flaky test suite quarantine');
  });
});
