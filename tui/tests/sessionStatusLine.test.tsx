import { render } from 'ink-testing-library';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SessionStatusLine } from '../src/components/Display/Scenario/SessionStatusLine';
import { ThemeProvider } from '../src/theme/ThemeContext';
import type { ContextUpdatedEvent, SessionInfoEvent, TokenUsageRecordedEvent } from '../src/types/scenario';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('SessionStatusLine (QA-9)', () => {
  it('renders a dim status line for session_state_changed', () => {
    const event: SessionInfoEvent = {
      kind: 'session_state_changed',
      id: 's1',
      message: 'Session state changed: active → completed',
      fromState: 'active',
      toState: 'completed',
    };
    const { lastFrame } = render(
      <ThemeProvider>
        <SessionStatusLine event={event} />
      </ThemeProvider>,
    );
    expect(lastFrame()).toContain('state changed: active → completed');
  });

  it('renders session_error with an error marker', () => {
    const event: SessionInfoEvent = {
      kind: 'session_error',
      id: 's2',
      message: 'Session error: boom',
      error: 'boom',
    };
    const { lastFrame } = render(
      <ThemeProvider>
        <SessionStatusLine event={event} />
      </ThemeProvider>,
    );
    expect(lastFrame()).toContain('error');
    expect(lastFrame()).toContain('boom');
  });

  it('renders session_status as a dim run-status line', () => {
    const event: SessionInfoEvent = {
      kind: 'session_status',
      id: 's3',
      message: 'Session status: completed',
      status: 'completed',
    };
    const { lastFrame } = render(
      <ThemeProvider>
        <SessionStatusLine event={event} />
      </ThemeProvider>,
    );
    expect(lastFrame()).toContain('status:');
    expect(lastFrame()).toContain('completed');
  });

  it('renders context_updated as context occupancy', () => {
    const event: ContextUpdatedEvent = {
      kind: 'context_updated',
      id: 'c1',
      used: 50_000,
      total: 128_000,
      percent: 39,
    };
    const { lastFrame } = render(
      <ThemeProvider>
        <SessionStatusLine event={event} />
      </ThemeProvider>,
    );
    expect(lastFrame()).toContain('50.0K/128.0K');
    expect(lastFrame()).toContain('39%');
  });

  it('renders token_usage_recorded with cost when present', () => {
    const event: TokenUsageRecordedEvent = {
      kind: 'token_usage_recorded',
      id: 't1',
      totalTokens: 52_316,
      totalCost: 0.05,
    };
    const { lastFrame } = render(
      <ThemeProvider>
        <SessionStatusLine event={event} />
      </ThemeProvider>,
    );
    expect(lastFrame()).toContain('52.3K');
    expect(lastFrame()).toContain('$0.0500');
  });

  it('renders token_usage_recorded without cost when absent', () => {
    const event: TokenUsageRecordedEvent = {
      kind: 'token_usage_recorded',
      id: 't2',
      totalTokens: 420,
    };
    const { lastFrame } = render(
      <ThemeProvider>
        <SessionStatusLine event={event} />
      </ThemeProvider>,
    );
    expect(lastFrame()).toContain('420');
    expect(lastFrame()).not.toContain('$');
  });
});
