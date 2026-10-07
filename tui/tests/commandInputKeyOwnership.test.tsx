/**
 * Key ownership for the composer's arrow keys while a turn is running.
 *
 * Ink registers every useInput hook on one emitter with no propagation stop, so
 * a keypress reaches every mounted hook. Arrows therefore have exactly one owner
 * (CommandInput, and only while the draft is empty); PgUp/PgDn are owned by
 * useTerminalKeyboard alone.
 */
import { render } from 'ink-testing-library';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CommandInput } from '../src/components/Input/CommandInput';
import { ThemeProvider } from '../src/theme/ThemeContext';

const UP = '\x1B[A';
const DOWN = '\x1B[B';
const PAGE_DOWN = '\x1B[6~';

const cleanups: Array<() => void> = [];

function mountRunning(value: string) {
  const scrollUp = vi.fn();
  const scrollDown = vi.fn();
  const app = render(
    <ThemeProvider>
      <CommandInput
        input={value}
        onInputChange={vi.fn()}
        onSubmit={vi.fn()}
        running
        scrollUp={scrollUp}
        scrollDown={scrollDown}
      />
    </ThemeProvider>,
  );
  cleanups.push(app.unmount);
  return { app, scrollUp, scrollDown };
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 30));

describe('CommandInput running-turn key ownership', () => {
  afterEach(() => {
    for (const unmount of cleanups.splice(0)) unmount();
    vi.clearAllMocks();
  });

  it('scrolls the transcript on arrows when the draft is empty', async () => {
    const { app, scrollUp, scrollDown } = mountRunning('');
    await settle();

    app.stdin.write(UP);
    app.stdin.write(DOWN);
    await settle();

    expect(scrollUp).toHaveBeenCalledTimes(1);
    expect(scrollDown).toHaveBeenCalledTimes(1);
  });

  it('leaves arrows to the editor when a draft is present', async () => {
    // With a non-empty draft, up/down are history recall and cursor line
    // movement; CommandInput must not swallow them.
    const { app, scrollUp, scrollDown } = mountRunning('draft text');
    await settle();

    app.stdin.write(UP);
    app.stdin.write(DOWN);
    await settle();

    expect(scrollUp).not.toHaveBeenCalled();
    expect(scrollDown).not.toHaveBeenCalled();
  });

  it('does not bind page keys, so PgDn cannot double-scroll', async () => {
    const { app, scrollUp, scrollDown } = mountRunning('');
    await settle();

    app.stdin.write(PAGE_DOWN);
    await settle();

    // useTerminalKeyboard is the sole owner of page keys. If CommandInput also
    // bound them, one press would scroll twice (Ink has no propagation stop).
    expect(scrollUp).not.toHaveBeenCalled();
    expect(scrollDown).not.toHaveBeenCalled();
  });
});
