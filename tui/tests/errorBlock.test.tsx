import { render } from 'ink-testing-library';
import { describe, expect, it } from 'vitest';
import { ErrorBlock } from '../src/components/Display/Scenario/ErrorBlock';
import { ThemeProvider } from '../src/theme/ThemeContext';
import type { ErrorEvent } from '../src/types/scenario';

function makeError(overrides: Partial<ErrorEvent> = {}): ErrorEvent {
  return {
    id: 'evt_1',
    kind: 'error',
    message: 'something went wrong',
    code: '',
    recoverable: false,
    ...overrides,
  };
}

function renderError(event: ErrorEvent, context: { expandedWarnings?: boolean } = {}) {
  return render(
    <ThemeProvider>
      <ErrorBlock event={event} context={context} />
    </ThemeProvider>,
  );
}

describe('ErrorBlock', () => {
  it('renders a non-recoverable error with the FAILED badge and halted note', () => {
    const { lastFrame } = renderError(makeError({ message: 'boom' }));
    const frame = lastFrame();
    expect(frame).toContain('[FAILED]');
    expect(frame).toContain('boom');
    expect(frame).toContain('Execution halted');
    expect(frame).not.toContain('[ERROR]');
  });

  it('renders a recoverable error with the ERROR badge and no halted note', () => {
    const { lastFrame } = renderError(makeError({ message: 'try again', recoverable: true }));
    const frame = lastFrame();
    expect(frame).toContain('[ERROR]');
    expect(frame).toContain('try again');
    expect(frame).toContain('Recoverable');
    expect(frame).not.toContain('Execution halted');
  });

  it('shows the provider line when present', () => {
    const { lastFrame } = renderError(makeError({ provider: 'google' }));
    const frame = lastFrame();
    expect(frame).toContain('Provider:');
    expect(frame).toContain('google');
  });

  it('shows the hint when present', () => {
    const { lastFrame } = renderError(makeError({ hint: 'Wait for the rate limit to reset.' }));
    const frame = lastFrame();
    expect(frame).toContain('Hint:');
    expect(frame).toContain('Wait for the rate limit to reset.');
  });

  it('truncates long messages and expands on the shared expandedWarnings signal', async () => {
    const longMessage = 'x'.repeat(300);
    const { lastFrame } = renderError(makeError({ message: longMessage }));
    expect(lastFrame()).toContain('…');
    expect(lastFrame()).toContain('ctrl+e to show full details');
    expect(lastFrame()).not.toContain('ctrl+e to hide full details');

    const expanded = renderError(makeError({ message: longMessage }), { expandedWarnings: true }).lastFrame();
    expect(expanded).toContain('ctrl+e to hide full details');
    expect(expanded).not.toContain('…');
  });

  it('does not truncate short messages or show a toggle', () => {
    const { lastFrame } = renderError(makeError({ message: 'short' }));
    const frame = lastFrame();
    expect(frame).toContain('short');
    expect(frame).not.toContain('ctrl+e');
    expect(frame).not.toContain('…');
  });
});
