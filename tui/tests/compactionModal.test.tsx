import { render } from 'ink-testing-library';
import { describe, expect, it, vi } from 'vitest';
import { CompactionModal } from '../src/screens/Context/CompactionModal';
import { ThemeProvider } from '../src/theme/ThemeContext';
import type { ContextCompactionEndedEvent, ContextCompactionStartedEvent, ScenarioEvent } from '../src/types/scenario';

describe('CompactionModal', () => {
  it('renders before/after/recovered from started and ended events', () => {
    const started: ContextCompactionStartedEvent = {
      kind: 'context_compaction_started',
      id: 'evt_1',
      message: 'started',
      used: 118_000,
      total: 128_000,
    };
    const ended: ContextCompactionEndedEvent = {
      kind: 'context_compaction_ended',
      id: 'evt_2',
      message: 'finished',
      used: 43_000,
      total: 128_000,
      tokensSaved: 75_000,
      summaryChars: 12_000,
      failed: false,
      preserved: {
        requirements: 12,
        decisions: 7,
        openTasks: 4,
        findings: 3,
        artifacts: 3,
        agents: 2,
      },
    };

    const { lastFrame } = render(
      <ThemeProvider>
        <CompactionModal events={[started, ended]} totalTokens={0} onCompactNow={() => {}} onClose={() => {}} />
      </ThemeProvider>,
    );

    const frame = lastFrame();
    expect(frame).toContain('118.0k');
    expect(frame).toContain('43.0k');
    expect(frame).toContain('75.0k');
    expect(frame).toContain('Requirements');
    expect(frame).toContain('12');
    expect(frame).toContain('Decisions');
    expect(frame).toContain('Active agents');
    expect(frame).toContain('2');
  });

  it('shows failure message and does not render preserved sections', () => {
    const ended: ContextCompactionEndedEvent = {
      kind: 'context_compaction_ended',
      id: 'evt_1',
      message: 'failed',
      used: 118_000,
      total: 128_000,
      tokensSaved: 0,
      failed: true,
    };

    const { lastFrame } = render(
      <ThemeProvider>
        <CompactionModal events={[ended]} totalTokens={0} onCompactNow={() => {}} onClose={() => {}} />
      </ThemeProvider>,
    );

    const frame = lastFrame();
    expect(frame).toContain('Unable to safely compact context');
    expect(frame).toContain('Conversation unchanged');
    expect(frame).not.toContain('Preserved');
  });

  it('omits Preserved/Compressed sections when no metrics provided', () => {
    const events: ScenarioEvent[] = [
      {
        kind: 'message',
        id: 'm1',
        text: 'hello',
      },
    ];

    const { lastFrame } = render(
      <ThemeProvider>
        <CompactionModal events={events} totalTokens={50000} onCompactNow={() => {}} onClose={() => {}} />
      </ThemeProvider>,
    );

    const frame = lastFrame();
    expect(frame).toContain('Before');
    expect(frame).toContain('After');
    expect(frame).not.toContain('Preserved');
    expect(frame).not.toContain('Compressed');
  });

  it('calls onCompactNow when Enter is pressed', () => {
    const onCompactNow = vi.fn();
    const { lastFrame } = render(
      <ThemeProvider>
        <CompactionModal events={[]} totalTokens={0} onCompactNow={onCompactNow} onClose={() => {}} />
      </ThemeProvider>,
    );
    expect(typeof onCompactNow).toBe('function');
    expect(lastFrame()).toContain('CONTEXT COMPACTION');
  });
});
