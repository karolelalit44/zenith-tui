import { render } from 'ink-testing-library';
import { describe, expect, it } from 'vitest';
import { ScenarioRenderer } from '../src/components/Display/Scenario/ScenarioRenderer';
import { collectTodoBoardEvents } from '../src/services/transport/todoBoardFixtureEmitter';
import { ThemeProvider } from '../src/theme/ThemeContext';
import type { ScenarioEvent } from '../src/types/scenario';
import { upsertEvent } from '../src/utils/eventUpsert';

function replaySlice(count: number): ScenarioEvent[] {
  const raw = collectTodoBoardEvents();
  let state: ScenarioEvent[] = [];
  raw.slice(0, count).forEach((event, index) => {
    state = upsertEvent(state, event, index);
  });
  return state;
}

function renderBoard(state: ScenarioEvent[]) {
  return render(
    <ThemeProvider>
      <ScenarioRenderer events={state} isRunning={false} thinkingCollapsed={false} />
    </ThemeProvider>,
  );
}

describe('TodoBoardBlock', () => {
  it('renders the slim window with a header and the newly created task', () => {
    const { lastFrame } = renderBoard(replaySlice(2));
    const frame = lastFrame();

    expect(frame).toContain('☑ TODO BOARD');
    expect(frame).toContain('LIVE SIMULATION');
    expect(frame).toContain('Add CI pipeline to the repo');
  });

  it('shows a distinct checkbox glyph per status', () => {
    const { lastFrame } = renderBoard(replaySlice(1));
    const frame = lastFrame();
    expect(frame).toContain('☑');
    expect(frame).toContain('⊘');
    expect(frame).toContain('☐');
    expect(frame).toContain('Flaky test suite quarantine');
  });

  it('shows only top-level tasks, no subtasks', () => {
    const { lastFrame } = renderBoard(replaySlice(2));
    const frame = lastFrame();
    expect(frame).not.toContain('Wire CI status into App dashboard');
    expect(frame).not.toContain('subtasks');
  });

  it('renders the completed board state', () => {
    const { lastFrame } = renderBoard(replaySlice(11));
    const frame = lastFrame();
    expect(frame).toContain('SIMULATION COMPLETE');
    expect(frame).toContain('Add CI pipeline to the repo');
  });

  it('omits counts, progress bars and the activity log from the slim window', () => {
    const { lastFrame } = renderBoard(replaySlice(11));
    const frame = lastFrame();
    expect(frame).not.toContain('▶ ACTIVITY LOG');
    expect(frame).not.toContain('Unblocked #T4');
    expect(frame).not.toContain('overall');
    expect(frame).not.toContain('last change:');
  });
});
