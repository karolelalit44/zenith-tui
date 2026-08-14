import { render } from 'ink-testing-library';
import { describe, expect, it } from 'vitest';
import { ScenarioRenderer } from '../src/components/Display/Scenario/ScenarioRenderer';
import { collectHrmsBuildEvents } from '../src/services/transport/hrmsBuildEmitter';
import { ThemeProvider } from '../src/theme/ThemeContext';
import type { ScenarioEvent } from '../src/types/scenario';
import { upsertEvent } from '../src/utils/eventUpsert';

const buildState = (events: ScenarioEvent[]): ScenarioEvent[] => {
  let state: ScenarioEvent[] = [];
  events.forEach((event, index) => {
    state = upsertEvent(state, event, index);
  });
  return state;
};

describe('E2E: HRMS build pipeline', () => {
  it('renders the full HRMS build: captain center, todo board, tool steps, compaction and success', () => {
    const emitted = collectHrmsBuildEvents();
    expect(emitted.length).toBeGreaterThanOrEqual(60);
    const state = buildState(emitted);

    const { lastFrame } = render(
      <ThemeProvider>
        <ScenarioRenderer events={state} isRunning={false} thinkingCollapsed={false} />
      </ThemeProvider>,
    );
    const frame = lastFrame();

    // Orchestration card
    expect(frame).toContain('⚡ CAPTAIN ZENITH COMMAND CENTER');
    expect(frame).toContain('Orchestration Complete');
    expect(frame).toContain('Model Architect');
    expect(frame).toContain('Backend Agent');

    // Todo board card
    expect(frame).toContain('☑ TODO BOARD');
    expect(frame).toContain('SIMULATION COMPLETE');
    expect(frame).toContain('Django HRMS');

    // Tool steps: the failed payroll run and its recovery
    expect(frame).toContain('payroll pro-rating');
    expect(frame).toContain('✗');

    // Compaction card
    expect(frame).toContain('context');

    // Plan + manifest + success
    expect(frame).toContain('HRMS Build Plan');
    expect(frame).toContain('Django HRMS shipped');
    expect(frame).toContain('12 iters');
  });

  it('renders the live mid-build state with running sub-agents', () => {
    const emitted = collectHrmsBuildEvents();
    const state = buildState(emitted.slice(0, 40));

    const { lastFrame } = render(
      <ThemeProvider>
        <ScenarioRenderer events={state} isRunning={true} thinkingCollapsed={false} />
      </ThemeProvider>,
    );
    const frame = lastFrame();
    expect(frame).toContain('⚡ CAPTAIN ZENITH COMMAND CENTER');
    expect(frame).toContain('☑ TODO BOARD');
    // The build is still in progress — the final success card has not rendered.
    expect(frame).not.toContain('12 iters');
  });
});
