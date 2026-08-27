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
  it('emits the realistic lifecycle and renders the minimal todo board', () => {
    const emitted = collectTodoLifecycleEvents({ outputDir: tempDir });
    const state = buildState(emitted);

    const { lastFrame } = render(
      <ThemeProvider>
        <ScenarioRenderer events={state} isRunning={false} thinkingCollapsed={false} historyExpanded={true} />
      </ThemeProvider>,
    );
    const frame = lastFrame();

    // Realistic response framing around the todo work.
    // Read rows are content-free by design: path + line count, never a dump
    // of the file's API surface.
    expect(frame).toContain('todoStore.ts');
    expect(frame).toContain('HRMS onboarding module');

    // Minimal board table: SN | todo title | status, no column header.
    expect(frame).not.toContain('TODO TITLE');
    expect(frame).toMatch(/T1\s+Build the HRMS employee onboarding module \(Django\)\s+success/);

    // The internal assertion report is not rendered.
    expect(frame).not.toContain('✓ ALL SCENARIOS PASSED');
    expect(frame).not.toContain('REJECTED EDGE CASES');
    expect(frame).not.toContain('☑ TODO BOARD');

    // Persistence was exercised: file must exist under the temp dir.
    expect(() => readFileSync(path.join(tempDir, 'todo-board.json'), 'utf8')).not.toThrow();
  });

  it('renders the live empty board early in the simulation', () => {
    const emitted = collectTodoLifecycleEvents({ outputDir: tempDir });
    const state = buildState(emitted.slice(0, 9));

    const { lastFrame } = render(
      <ThemeProvider>
        <ScenarioRenderer events={state} isRunning={true} thinkingCollapsed={false} historyExpanded={true} />
      </ThemeProvider>,
    );
    const frame = lastFrame();
    expect(frame).toContain('TODO');
    expect(frame).toContain('(no todos yet)');
    expect(frame).not.toContain('✓ ALL SCENARIOS PASSED');
  });
});
