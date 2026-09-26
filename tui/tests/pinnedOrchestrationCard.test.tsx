import { render } from 'ink-testing-library';
import { describe, expect, it } from 'vitest';
import { PinnedOrchestrationCard } from '../src/components/Display/Scenario/PinnedOrchestrationCard';
import { ThemeProvider } from '../src/theme/ThemeContext';
import type { CrewmateAgent, TimelineEntry } from '../src/types/scenario';
import type { ConsolidatedOrchestration } from '../src/utils/orchestration';

const makeCrewmate = (
  id: string,
  name: string,
  role: string,
  task: string,
  status: CrewmateAgent['status'],
  activity?: string,
  resultSummary?: string,
  error?: string,
): CrewmateAgent => ({
  id,
  name,
  role,
  task,
  status,
  activity,
  resultSummary,
  error,
});

const makeOrch = (
  stage: ConsolidatedOrchestration['stage'],
  crewmates: CrewmateAgent[] = [],
  timeline: TimelineEntry[] = [],
  opts: {
    captainMessage?: string;
    activeStep?: string;
    hasFailedCrew?: boolean;
    allComplete?: boolean;
  } = {},
): ConsolidatedOrchestration => ({
  kind: 'captain_orchestration',
  id: 'orch_test',
  stage,
  captainMessage: opts.captainMessage || 'Captain directive',
  crewmates,
  timeline,
  activeStep: opts.activeStep,
  hasFailedCrew: opts.hasFailedCrew ?? false,
  allComplete: opts.allComplete ?? false,
  activeCrewmateCount: crewmates.filter((c) => c.status === 'working' || c.status === 'assigned').length,
});

function renderCard(event: ConsolidatedOrchestration, isRunning = false) {
  const { lastFrame } = render(
    <ThemeProvider>
      <PinnedOrchestrationCard event={event} isRunning={isRunning} />
    </ThemeProvider>,
  );
  return lastFrame();
}

describe('PinnedOrchestrationCard', () => {
  it('renders captain command center header and running stage', () => {
    const frame = renderCard(
      makeOrch('working', [makeCrewmate('c1', 'Apogee', 'Scout', 'Investigate codebase', 'working')], [], {
        activeStep: 'Reading tools.py',
      }),
      true,
    );

    expect(frame).toContain('⚡ Captain');
    expect(frame).toContain('Execution Active');
    expect(frame).toContain('Reading tools.py');
    expect(frame).toContain('Apogee');
    expect(frame).toContain('[Scout]');
    expect(frame).toContain('ACTIVE');
  });

  it('renders live activity subline for working crewmate', () => {
    const frame = renderCard(
      makeOrch(
        'working',
        [makeCrewmate('c1', 'Apogee', 'Scout', 'Audit files', 'working', 'Reading server/config/constants/tools.py')],
        [],
      ),
      true,
    );

    expect(frame).toContain('Reading server/config/constants/tools.py');
  });

  it('renders real-time communication timeline stream', () => {
    const timeline: TimelineEntry[] = [
      { timestamp: '11:42:01', message: 'Captain Zenith ❯ Delegating task to Apogee', type: 'info' },
      { timestamp: '11:42:04', message: 'Apogee ❯ Reading files in repo', type: 'info' },
      { timestamp: '11:42:08', message: 'Apogee ✔ Completed investigation', type: 'success' },
    ];

    const frame = renderCard(
      makeOrch(
        'complete',
        [makeCrewmate('c1', 'Apogee', 'Scout', 'Audit files', 'completed', undefined, 'Discrepancies found')],
        timeline,
        { allComplete: true },
      ),
      false,
    );

    expect(frame).toContain('Communication Stream');
    expect(frame).toContain('Captain Zenith ❯ Delegating task to Apogee');
    expect(frame).toContain('Apogee ❯ Reading files in repo');
    expect(frame).toContain('Apogee ✔ Completed investigation');
    expect(frame).toContain('✔ Complete');
    expect(frame).toContain('✔ Result: Discrepancies found');
  });

  it('truthful completion: marks failed when any crewmate failed', () => {
    const frame = renderCard(
      makeOrch(
        'complete',
        [makeCrewmate('c1', 'Apogee', 'Scout', 'Audit files', 'failed', undefined, undefined, 'Timeout exceeded')],
        [],
        { hasFailedCrew: true },
      ),
      false,
    );

    expect(frame).toContain('✗ Failed');
    expect(frame).toContain('FAILED');
    expect(frame).toContain('Error: Timeout exceeded');
  });
});
