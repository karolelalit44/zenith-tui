import { render } from 'ink-testing-library';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ScenarioRenderer } from '../src/components/Display/Scenario/ScenarioRenderer';
import { collectTodoBoardEvents, emitTodoBoardFixture } from '../src/services/transport/todoBoardFixtureEmitter';
import { ThemeProvider } from '../src/theme/ThemeContext';
import type { ScenarioEvent } from '../src/types/scenario';
import { upsertEvent } from '../src/utils/eventUpsert';
import { consolidateTodoBoardEvents } from '../src/utils/todoBoard';

/**
 * The todo board data pipeline (fixture → typed events → consolidation) stays
 * intact, and the rendered todo window is the minimal board table: SN | todo
 * title | status (max 10 rows). These tests guard both the data pipeline and
 * the "no assertion report" contract.
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

describe('E2E: todo board data pipeline', () => {
  it('emits the lifecycle through the shared pipeline and renders the minimal board', async () => {
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

    // Minimal board rows: SN | title | status, top-level only.
    expect(frame).toMatch(/T1\s+Add todo board simulation pipeline\s+success/);
    expect(frame).toMatch(/T4\s+Flaky test suite quarantine\s+failure/);
    expect(frame).toMatch(/T5\s+Add CI pipeline to the repo\s+success/);
    // Subtasks never render as rows.
    expect(frame).not.toContain('T1-S1');

    // The internal assertion report is not rendered.
    expect(frame).not.toContain('✓ ALL SCENARIOS PASSED');
    expect(frame).not.toContain('☑ TODO BOARD');
  });

  it('renders the minimal board window mid-simulation too', async () => {
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

    expect(frame).not.toContain('✓ ALL SCENARIOS PASSED');
    expect(frame).not.toContain('☑ TODO BOARD');
  });
});
