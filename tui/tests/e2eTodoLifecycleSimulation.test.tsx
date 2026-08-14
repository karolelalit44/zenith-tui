import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { render } from 'ink-testing-library';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { ScenarioRenderer } from '../src/components/Display/Scenario/ScenarioRenderer';
import { collectTodoLifecycleEvents } from '../src/services/transport/todoLifecycleEmitter';
import { ThemeProvider } from '../src/theme/ThemeContext';
import type { ScenarioEvent } from '../src/types/scenario';
import { upsertEvent } from '../src/utils/eventUpsert';
import { consolidateTodoTestEvents } from '../src/utils/todoLifecycle';

let tempDir: string;

beforeEach(() => {
  tempDir = mkdtempSync(path.join(tmpdir(), 'todo-e2e-'));
});

afterEach(() => {
  rmSync(tempDir, { recursive: true, force: true });
});

const buildState = (events: ScenarioEvent[]): ScenarioEvent[] => {
  let state: ScenarioEvent[] = [];
  events.forEach((event, index) => {
    state = upsertEvent(state, event, index);
  });
  return state;
};

describe('E2E: todo lifecycle pipeline', () => {
  it('emits the lifecycle and renders board + report together', () => {
    const emitted = collectTodoLifecycleEvents({ outputDir: tempDir });
    const state = buildState(emitted);

    const report = consolidateTodoTestEvents(state);
    expect(report).not.toBeNull();
    expect(report?.passedCount).toBe(report?.totalCount);
    expect(report?.totalCount).toBeGreaterThanOrEqual(40);
    expect(report?.rejectedOps).toBeDefined();

    const { lastFrame } = render(
      <ThemeProvider>
        <ScenarioRenderer events={state} isRunning={false} thinkingCollapsed={false} />
      </ThemeProvider>,
    );
    const frame = lastFrame();

    // Board card: terminal state
    expect(frame).toContain('☑ TODO BOARD');
    expect(frame).toContain('SIMULATION COMPLETE');
    expect(frame).toContain('Build the HRMS employee onboarding module');

    // Report card: terminal state
    expect(frame).toContain('🧪 TODO SIMULATION');
    expect(frame).toContain('✓ ALL SCENARIOS PASSED');
    expect(frame).toContain('⊘ REJECTED EDGE CASES');
    expect(frame).toContain('setStatus(todo → done) direct');

    // Persistence was exercised: file must exist under the temp dir.
    expect(() => readFileSync(path.join(tempDir, 'todo-lifecycle.json'), 'utf8')).not.toThrow();
  });

  it('renders the live in-progress report mid-simulation', () => {
    const emitted = collectTodoLifecycleEvents({ outputDir: tempDir });
    const state = buildState(emitted.slice(0, 6));

    const { lastFrame } = render(
      <ThemeProvider>
        <ScenarioRenderer events={state} isRunning={true} thinkingCollapsed={false} />
      </ThemeProvider>,
    );
    const frame = lastFrame();
    expect(frame).toContain('☑ TODO BOARD');
    expect(frame).toContain('LIVE SIMULATION');
    expect(frame).toContain('🧪 TODO SIMULATION');
    expect(frame).toContain('Create');
    expect(frame).toContain('Persist');
    expect(frame).toContain('✔ createTodo accepts a valid TODO with subtasks');
  });
});
