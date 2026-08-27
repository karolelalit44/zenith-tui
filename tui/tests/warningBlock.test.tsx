import { render } from 'ink-testing-library';
import { describe, expect, it } from 'vitest';
import {
  compactDiagnosticMessage,
  isLoopDiagnostic,
  WarningBlock,
} from '../src/components/Display/Scenario/WarningBlock';
import { ThemeProvider } from '../src/theme/ThemeContext';
import type { WarningEvent } from '../src/types/scenario';

function makeWarning(overrides: Partial<WarningEvent> = {}): WarningEvent {
  return { kind: 'warning', id: 'w1', message: 'Something needs attention', ...overrides };
}

function renderWarning(event: WarningEvent) {
  const { lastFrame } = render(
    <ThemeProvider>
      <WarningBlock event={event} />
    </ThemeProvider>,
  );
  return lastFrame();
}

describe('isLoopDiagnostic', () => {
  it('classifies agent-loop codes as diagnostics', () => {
    expect(isLoopDiagnostic('STALL')).toBe(true);
    expect(isLoopDiagnostic('REJECTED')).toBe(true);
    expect(isLoopDiagnostic('SKIPPED_CALLS')).toBe(true);
    expect(isLoopDiagnostic('LOOP_DETECTED')).toBe(true);
    expect(isLoopDiagnostic('NO_FILES_CREATED')).toBe(true);
  });

  it('keeps user-facing codes prominent', () => {
    expect(isLoopDiagnostic('RATE_LIMIT')).toBe(false);
    expect(isLoopDiagnostic('QUOTA')).toBe(false);
    expect(isLoopDiagnostic('CANCELLED')).toBe(false);
    expect(isLoopDiagnostic(undefined)).toBe(false);
  });
});

describe('compactDiagnosticMessage', () => {
  it('shortens the REJECTED tool prefix', () => {
    expect(compactDiagnosticMessage("Tool 'file_write' rejected: File already exists.")).toBe(
      'file_write rejected: File already exists.',
    );
  });
});

describe('WarningBlock', () => {
  it('renders loop diagnostics as a dim status line without the warning badge', () => {
    const frame = renderWarning(makeWarning({ code: 'STALL', message: 'No new tool work this iteration' }));
    expect(frame).toContain('↳');
    expect(frame).toContain('No new tool work this iteration');
    expect(frame).not.toContain('[WARNING]');
    expect(frame).not.toContain('▲');
  });

  it('renders real warnings with the prominent badge', () => {
    const frame = renderWarning(makeWarning({ code: 'RATE_LIMIT', message: 'Rate limit hit, cooling down' }));
    expect(frame).toContain('▲ [WARNING]');
    expect(frame).toContain('Rate limit hit, cooling down');
    expect(frame).toContain('RATE_LIMIT');
  });

  it('truncates long messages with a ctrl+e hint', () => {
    const frame = renderWarning(makeWarning({ message: 'x'.repeat(300) }));
    expect(frame).toContain('ctrl+e to show full details');
    expect(frame).not.toContain('x'.repeat(300));
  });
});
