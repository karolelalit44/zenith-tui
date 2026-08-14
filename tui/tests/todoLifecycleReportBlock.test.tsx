import os from 'node:os';
import path from 'node:path';
import { render } from 'ink-testing-library';
import { describe, expect, it } from 'vitest';
import { ScenarioRenderer } from '../src/components/Display/Scenario/ScenarioRenderer';
import { collectTodoLifecycleEvents } from '../src/services/transport/todoLifecycleEmitter';
import { ThemeProvider } from '../src/theme/ThemeContext';
import type { ScenarioEvent } from '../src/types/scenario';
import { upsertEvent } from '../src/utils/eventUpsert';

const outputDir = path.join(os.tmpdir(), `zenith-todo-report-${process.pid}`);

function replaySlice(count: number): ScenarioEvent[] {
  const raw = collectTodoLifecycleEvents({ outputDir });
  let state: ScenarioEvent[] = [];
  raw.slice(0, count).forEach((event, index) => {
    state = upsertEvent(state, event, index);
  });
  return state;
}

function renderReport(state: ScenarioEvent[]) {
  return render(
    <ThemeProvider>
      <ScenarioRenderer events={state} isRunning={false} thinkingCollapsed={false} />
    </ThemeProvider>,
  );
}

describe('TodoLifecycleReportBlock', () => {
  it('renders the branded report card with the phase stepper', () => {
    const { lastFrame } = renderReport(replaySlice(3));
    const frame = lastFrame();
    expect(frame).toContain('🧪 TODO SIMULATION');
    expect(frame).toContain('Create');
    expect(frame).toContain('Manage');
    expect(frame).toContain('Persist');
  });

  it('renders scenario assertions with pass/fail icons', () => {
    const { lastFrame } = renderReport(replaySlice(3));
    const frame = lastFrame();
    expect(frame).toContain('✔ createTodo accepts a valid TODO with subtasks');
    expect(frame).toContain('✔ createTodo(blank title) rejected');
  });

  it('lists rejected edge-case operations with reasons', () => {
    const { lastFrame } = renderReport(replaySlice(3));
    const frame = lastFrame();
    expect(frame).toContain('⊘ REJECTED EDGE CASES');
    expect(frame).toContain('createTodo(blank title)');
    expect(frame).toContain('title must be a non-empty string');
  });

  it('shows the cumulative assertion pass count', () => {
    const { lastFrame } = renderReport(replaySlice(3));
    const frame = lastFrame();
    expect(frame).toMatch(/\d+✓\/\d+/);
    expect(frame).toContain('assertions');
  });

  it('renders the terminal report with all phases passed', () => {
    const { lastFrame } = renderReport(collectTodoLifecycleEvents());
    const frame = lastFrame();
    expect(frame).toContain('✓ ALL SCENARIOS PASSED');
    expect(frame).toContain('Lifecycle complete');
  });
});
