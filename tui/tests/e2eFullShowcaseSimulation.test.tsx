import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { render } from 'ink-testing-library';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { ScenarioRenderer } from '../src/components/Display/Scenario/ScenarioRenderer';
import { collectHrmsBuildEvents } from '../src/services/scenario/hrmsBuildDriver';
import { collectTodoLifecycleEvents } from '../src/services/transport/todoLifecycleEmitter';
import { ThemeProvider } from '../src/theme/ThemeContext';
import type { ScenarioEvent } from '../src/types/scenario';
import { upsertEvent } from '../src/utils/eventUpsert';

let tempDir: string;

beforeEach(() => {
  tempDir = mkdtempSync(path.join(tmpdir(), 'showcase-e2e-'));
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

describe('E2E: full showcase pipeline', () => {
  it('renders lifecycle verification followed by the HRMS build in one response', () => {
    // Same concatenation the `full-showcase.json` simulation file is built from:
    // lifecycle first, then the HRMS build.
    const emitted = [...collectTodoLifecycleEvents({ outputDir: tempDir }), ...collectHrmsBuildEvents()];
    expect(emitted.length).toBeGreaterThanOrEqual(90);
    const state = buildState(emitted);

    const { lastFrame } = render(
      <ThemeProvider>
        <ScenarioRenderer events={state} isRunning={false} thinkingCollapsed={false} />
      </ThemeProvider>,
    );
    const frame = lastFrame();

    // Lifecycle half: the board table shows the completed T1 alongside the
    // HRMS stream.
    expect(frame).toMatch(/T1\s+Build the HRMS employee onboarding module \(Django\)\s+success/);
    expect(frame).toContain('TodoStore API');

    // HRMS half: orchestration, compaction, and the shipped build.
    expect(frame).toContain('⚡ CAPTAIN ZENITH COMMAND CENTER');
    expect(frame).toContain('Orchestration Complete');
    expect(frame).toContain('Scenario Runner');
    expect(frame).toContain('Backend Agent');
    expect(frame).toContain('HRMS Build Plan');
    expect(frame).toContain('Django HRMS shipped');
    expect(frame).toContain('12 iters');

    // One minimal board table combining both halves' work.
    expect(frame).toMatch(/H1\s+Scaffold HRMS Django project\s+success/);
    expect(frame).toMatch(/H5\s+Admin \+ seed data\s+failure/);
    expect(frame).not.toContain('☑ TODO BOARD');
    expect(frame).not.toContain('✓ ALL SCENARIOS PASSED');
  });

  it('renders the live in-progress combined stream without clobbering either half', () => {
    const emitted = [...collectTodoLifecycleEvents({ outputDir: tempDir }), ...collectHrmsBuildEvents()];
    const state = buildState(emitted.slice(0, 60));

    const { lastFrame } = render(
      <ThemeProvider>
        <ScenarioRenderer events={state} isRunning={true} thinkingCollapsed={false} />
      </ThemeProvider>,
    );
    const frame = lastFrame();
    // Lifecycle half: the board table with T1 already checked off.
    expect(frame).toMatch(/T1\s+Build the HRMS employee onboarding/);
    expect(frame).toContain('⚡ CAPTAIN ZENITH COMMAND CENTER');
    expect(frame).not.toContain('☑ TODO BOARD');
    expect(frame).not.toContain('✓ ALL SCENARIOS PASSED');
    // Build still in progress — final HRMS success has not rendered.
    expect(frame).not.toContain('12 iters');
  });
});
