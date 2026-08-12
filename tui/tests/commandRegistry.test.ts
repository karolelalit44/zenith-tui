import { describe, expect, it, vi } from 'vitest';
import { dispatchCommand } from '../src/services/api/CommandRegistry';

function makeContext() {
  return {
    openOverlay: vi.fn(),
    clearTurns: vi.fn(),
    compactTurns: vi.fn(),
    clearTools: vi.fn(),
    setMode: vi.fn(),
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

  it('dispatches /models to the models overlay', () => {
    const ctx = makeContext();
    expect(dispatchCommand('/models', ctx)).toBe(true);
    expect(ctx.openOverlay).toHaveBeenCalledWith('models');
  });

  it('dispatches clear, compact, and clear-tools dynamically', () => {
    const ctx = makeContext();
    expect(dispatchCommand('/clear', ctx)).toBe(true);
    expect(ctx.clearTurns).toHaveBeenCalled();

    expect(dispatchCommand('/compact', ctx)).toBe(true);
    expect(ctx.compactTurns).toHaveBeenCalled();

    expect(dispatchCommand('/clear-tools', ctx)).toBe(true);
    expect(ctx.clearTools).toHaveBeenCalled();
  });

  it('is case-insensitive', () => {
    const ctx = makeContext();
    expect(dispatchCommand('  /HELP ', ctx)).toBe(true);
    expect(ctx.openOverlay).toHaveBeenCalledWith('help');
  });

  it('returns false for unknown commands', () => {
    expect(dispatchCommand('/nope', makeContext())).toBe(false);
  });
});
