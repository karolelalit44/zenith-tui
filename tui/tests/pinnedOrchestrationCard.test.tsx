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

    expect(frame).toContain('Captain');
    expect(frame).toContain('Execution Active');
    expect(frame).toContain('0/1 done · 1 active');
    expect(frame).toContain('Reading tools.py');
    expect(frame).toContain('Apogee');
    expect(frame).toContain('Scout');
    expect(frame).toContain('active');
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

    expect(frame).toContain('Signals');
    expect(frame).not.toContain('Captain Zenith ❯');
    expect(frame).not.toContain('Apogee ❯');
    expect(frame).toContain('Reading files in repo');
    expect(frame).toContain('Completed investigation');
    expect(frame).toContain('Complete');
    expect(frame).toContain('result Discrepancies found');
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

    expect(frame).toContain('Failed');
    expect(frame).toContain('1 failed');
    expect(frame).toContain('✗ failed');
    expect(frame).toContain('error Timeout exceeded');
  });
});

describe('PinnedOrchestrationCard crewmate status rows', () => {
  it('renders the per-crewmate status glyph, not just the header word', () => {
    const frame =
      renderCard(
        makeOrch(
          'working',
          [
            makeCrewmate('c1', 'Apogee', 'Scout', 'Audit files', 'working'),
            makeCrewmate('c2', 'Vega', 'Reviewer', 'Check findings', 'completed'),
            makeCrewmate('c3', 'Rigel', 'Reviewer', 'Check tests', 'failed'),
            makeCrewmate('c4', 'Mira', 'Scout', 'Trace imports', 'retired'),
          ],
          [],
        ),
        true,
      ) || '';

    // Distinct per-row statuses. Without these, renderCrewStatus could return the
    // same glyph for every status and the header words would still pass.
    expect(frame).toMatch(/active\s+Apogee/);
    expect(frame).toMatch(/✓ done\s+Vega/);
    expect(frame).toMatch(/✗ failed\s+Rigel/);
    expect(frame).toMatch(/○ retired\s*Mira/);
  });
});

describe('PinnedOrchestrationCard overflow and labels', () => {
  it('caps the crewmate roster and reports the overflow', () => {
    const crew = Array.from({ length: 6 }, (_, i) =>
      makeCrewmate(`c${i}`, `Agent${i}`, 'Scout', `Task ${i}`, 'completed'),
    );
    const frame = renderCard(makeOrch('complete', crew, [], { allComplete: true })) || '';

    expect(frame).toContain('Agent0');
    expect(frame).toContain('Agent3');
    expect(frame).not.toContain('Agent4');
    expect(frame).not.toContain('Agent5');
    expect(frame).toContain('+2 more delegated agents');
  });

  it('singularises the overflow label for exactly one hidden agent', () => {
    const crew = Array.from({ length: 5 }, (_, i) =>
      makeCrewmate(`c${i}`, `Agent${i}`, 'Scout', `Task ${i}`, 'completed'),
    );
    const frame = renderCard(makeOrch('complete', crew, [], { allComplete: true })) || '';
    expect(frame).toContain('+1 more delegated agent');
  });

  it('reports partial completion when some crew succeeded and some failed', () => {
    const frame =
      renderCard(
        makeOrch(
          'complete',
          [
            makeCrewmate('c1', 'Apogee', 'Scout', 'Audit files', 'completed'),
            makeCrewmate('c2', 'Rigel', 'Reviewer', 'Check tests', 'failed'),
          ],
          [],
          { hasFailedCrew: true },
        ),
      ) || '';
    expect(frame).toContain('Partial completion');
  });

  it('drops all but the two most recent timeline entries', () => {
    const timeline: TimelineEntry[] = [
      { timestamp: '11:42:01', message: 'First signal', type: 'info' },
      { timestamp: '11:42:04', message: 'Second signal', type: 'info' },
      { timestamp: '11:42:08', message: 'Third signal', type: 'success' },
    ];
    const frame = renderCard(makeOrch('complete', [], timeline)) || '';
    expect(frame).not.toContain('First signal');
    expect(frame).toContain('Second signal');
    expect(frame).toContain('Third signal');
  });

  it('formats an ISO timestamp to HH:MM', () => {
    const timeline: TimelineEntry[] = [
      { timestamp: '2026-03-04T11:42:09.123Z', message: 'Dated signal', type: 'info' },
    ];
    const frame = renderCard(makeOrch('complete', [], timeline)) || '';
    expect(frame).toContain('11:42');
  });

  it('falls back to the captain message when activeStep repeats the stage token', () => {
    const frame =
      renderCard(
        makeOrch('working', [makeCrewmate('c1', 'Apogee', 'Scout', 'Audit files', 'working')], [], {
          activeStep: 'working',
          captainMessage: 'Map the auth flow',
        }),
        true,
      ) || '';
    expect(frame).toContain('Map the auth flow');
    expect(frame).not.toContain('↳ working');
  });
});
