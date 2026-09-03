import { describe, expect, it, vi } from 'vitest';
import { commandRegistry, dispatchCommand } from '../src/services/api/CommandRegistry';

function makeContext() {
  return {
    openOverlay: vi.fn(),
    clearTurns: vi.fn(),
    clearTools: vi.fn(),
    setMode: vi.fn(),
    compactTurns: vi.fn(),
  };
}

describe('dispatchCommand registry dispatch', () => {
  it('dispatches /help to the help overlay', () => {
    const ctx = makeContext();
    expect(dispatchCommand('/help', ctx)).toBe(true);
    expect(ctx.openOverlay).toHaveBeenCalledWith('help');
  });

  it('dispatches /provider to the provider overlay', () => {
    const ctx = makeContext();
    expect(dispatchCommand('/provider', ctx)).toBe(true);
    expect(ctx.openOverlay).toHaveBeenCalledWith('provider');
  });

  it('dispatches clear, new, and clear-tools dynamically', () => {
    const ctx = makeContext();
    expect(dispatchCommand('/clear', ctx)).toBe(true);
    expect(ctx.clearTurns).toHaveBeenCalledTimes(1);

    expect(dispatchCommand('/new', ctx)).toBe(true);
    expect(ctx.clearTurns).toHaveBeenCalledTimes(2);

    expect(dispatchCommand('/clear-tools', ctx)).toBe(true);
    expect(ctx.clearTools).toHaveBeenCalled();
  });

  it('dispatches /compact to the compaction runner', () => {
    const ctx = makeContext();
    expect(dispatchCommand('/compact', ctx)).toBe(true);
    expect(ctx.compactTurns).toHaveBeenCalled();
  });

  it('is case-insensitive', () => {
    const ctx = makeContext();
    expect(dispatchCommand('  /HELP ', ctx)).toBe(true);
    expect(ctx.openOverlay).toHaveBeenCalledWith('help');
  });

  it('dispatches /sessions alias to the session overlay', () => {
    const ctx = makeContext();
    expect(dispatchCommand('/sessions', ctx)).toBe(true);
    expect(ctx.openOverlay).toHaveBeenCalledWith('session');
  });

  it('has no duplicate command IDs or slash commands', () => {
    const ids = commandRegistry.map((c) => c.id);
    expect(new Set(ids).size).toBe(ids.length);

    const slashes = commandRegistry.filter((c) => c.slash).map((c) => c.slash);
    expect(new Set(slashes).size).toBe(slashes.length);
  });

  it('returns false for unknown commands', () => {
    expect(dispatchCommand('/nope', makeContext())).toBe(false);
  });
});
