import { render } from 'ink-testing-library';
import { describe, expect, it } from 'vitest';
import { FinalSummaryCard } from '../src/components/Display/Scenario/FinalSummaryCard';
import { ThemeProvider } from '../src/theme/ThemeContext';
import type { SessionSummarizedEvent } from '../src/types/scenario';

describe('FinalSummaryCard (QA-9.2)', () => {
  it('renders outcome/discovered/changed/affected/verification/next from run_state', () => {
    const event: SessionSummarizedEvent = {
      kind: 'session_summarized',
      id: 's1',
      summary: 'Fixed the leak',
      findings: ['Root cause was an unclosed cursor'],
      runState: {
        status: 'completed',
        mode: 'build',
        objective: 'Fix the leak',
        findings: ['Root cause was an unclosed cursor'],
        final: { kind: 'success', message: 'done' },
        manifest: {
          created: ['src/fix.py'],
          modified: ['src/leak.py'],
          completed: true,
        },
        todo: [
          { id: 't1', title: 'Write tests', status: 'in_progress', priority: 'high' },
          { id: 't2', title: 'Done item', status: 'done', priority: 'low' },
        ],
      },
    };

    const { lastFrame } = render(
      <ThemeProvider>
        <FinalSummaryCard event={event} />
      </ThemeProvider>,
    );

    const frame = lastFrame() || '';
    expect(frame).toContain('Run summary');
    expect(frame).toContain('Fixed the leak');
    expect(frame).toContain('outcome:');
    expect(frame).toContain('completed');
    expect(frame).toContain('done');
    expect(frame).toContain('discovered:');
    expect(frame).toContain('Root cause was an unclosed cursor');
    expect(frame).toContain('changed:');
    expect(frame).toContain('src/fix.py');
    expect(frame).toContain('affected:');
    expect(frame).toContain('src/leak.py');
    expect(frame).toContain('verification:');
    expect(frame).toContain('verified');
    expect(frame).toContain('next:');
    expect(frame).toContain('Write tests');
    expect(frame).not.toContain('Done item');
  });

  it('shows unresolved only for failed/blocked/error outcomes', () => {
    const event: SessionSummarizedEvent = {
      kind: 'session_summarized',
      id: 's2',
      runState: {
        status: 'failed',
        final: { kind: 'error', message: 'DB locked', code: 'LOCKED' },
        manifest: { created: [], modified: [], completed: false },
      },
    };

    const { lastFrame } = render(
      <ThemeProvider>
        <FinalSummaryCard event={event} />
      </ThemeProvider>,
    );

    const frame = lastFrame() || '';
    expect(frame).toContain('outcome:');
    expect(frame).toContain('failed');
    expect(frame).toContain('LOCKED');
    expect(frame).toContain('unresolved:');
    expect(frame).toContain('DB locked');
    expect(frame).not.toContain('verification:');
  });

  it('omits empty sections entirely', () => {
    const event: SessionSummarizedEvent = {
      kind: 'session_summarized',
      id: 's3',
      runState: {
        status: 'idle',
        manifest: { created: [], modified: [] },
        todo: [],
      },
    };

    const { lastFrame } = render(
      <ThemeProvider>
        <FinalSummaryCard event={event} />
      </ThemeProvider>,
    );

    const frame = lastFrame() || '';
    expect(frame).toContain('outcome:');
    expect(frame).not.toContain('discovered:');
    expect(frame).not.toContain('changed:');
    expect(frame).not.toContain('affected:');
    expect(frame).not.toContain('next:');
    expect(frame).not.toContain('unresolved:');
  });

  it('renders nothing when there is no run_state and no summary', () => {
    const event: SessionSummarizedEvent = { kind: 'session_summarized', id: 's4' };

    const { lastFrame } = render(
      <ThemeProvider>
        <FinalSummaryCard event={event} />
      </ThemeProvider>,
    );

    expect(lastFrame()).toBe('');
  });

  it('caps long sections at five rows', () => {
    const findings = Array.from({ length: 9 }, (_, i) => `Finding ${i + 1}`);
    const event: SessionSummarizedEvent = {
      kind: 'session_summarized',
      id: 's5',
      findings,
      runState: { status: 'completed', findings, final: { kind: 'success', message: 'ok' } },
    };

    const { lastFrame } = render(
      <ThemeProvider>
        <FinalSummaryCard event={event} />
      </ThemeProvider>,
    );

    const frame = lastFrame() || '';
    expect(frame).toContain('Finding 5');
    expect(frame).not.toContain('Finding 6');
  });
});
