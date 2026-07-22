import { describe, expect, it, vi } from 'vitest';
import { CommandService } from '../src/services/data/CommandService';

describe('CommandService Dynamic options.json Loader', () => {
  const service = new CommandService();

  it('loads command options from options.json', () => {
    const commands = service.getCommands();
    expect(commands.length).toBeGreaterThan(0);

    const hints = service.getCommandHints();
    expect(hints.some((h) => h.command === '/mode')).toBe(true);
    expect(hints.some((h) => h.command === '/provider')).toBe(true);
  });

  it('dispatches overlay command dynamically without static switch cases', () => {
    const openOverlay = vi.fn();
    const clearTurns = vi.fn();
    const compactTurns = vi.fn();

    const handled = service.dispatchCommand('/provider', {
      openOverlay,
      clearTurns,
      compactTurns,
    });

    expect(handled).toBe(true);
    expect(openOverlay).toHaveBeenCalledWith('provider');
  });

  it('dispatches clear and compact commands dynamically', () => {
    const openOverlay = vi.fn();
    const clearTurns = vi.fn();
    const compactTurns = vi.fn();

    service.dispatchCommand('/clear', { openOverlay, clearTurns, compactTurns });
    expect(clearTurns).toHaveBeenCalled();

    service.dispatchCommand('/compact', { openOverlay, clearTurns, compactTurns });
    expect(compactTurns).toHaveBeenCalled();
  });
});
