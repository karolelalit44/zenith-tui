import { describe, expect, it, vi } from 'vitest';
import { clearTerminalScreen } from '../src/utils/terminal';

describe('clearTerminalScreen', () => {
  it('writes screen and scrollback clearing ANSI sequence to stdout', () => {
    const writeSpy = vi.spyOn(process.stdout, 'write').mockImplementation(() => true);

    clearTerminalScreen();

    expect(writeSpy).toHaveBeenCalledWith('\x1B[H\x1B[2J\x1B[3J\x1B[H');
    writeSpy.mockRestore();
  });

  it('calls console.clear when stdout is a TTY', () => {
    const writeSpy = vi.spyOn(process.stdout, 'write').mockImplementation(() => true);
    const clearSpy = vi.spyOn(console, 'clear').mockImplementation(() => {});
    const origIsTTY = process.stdout.isTTY;

    try {
      Object.defineProperty(process.stdout, 'isTTY', { value: true, configurable: true });
      clearTerminalScreen();
      expect(clearSpy).toHaveBeenCalled();
      expect(writeSpy).toHaveBeenCalledWith('\x1B[H\x1B[2J\x1B[3J\x1B[H');
    } finally {
      Object.defineProperty(process.stdout, 'isTTY', { value: origIsTTY, configurable: true });
      writeSpy.mockRestore();
      clearSpy.mockRestore();
    }
  });
});
