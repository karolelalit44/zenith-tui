import { describe, expect, it, vi } from 'vitest';
import { CommandService } from '../src/services/api/CommandService';

describe('CommandService Dynamic options.json Loader', () => {
  const service = new CommandService();

  it('loads command options from options.json', () => {
    const handled = service.dispatchCommand('/help', {
      openOverlay: vi.fn(),
      clearTurns: vi.fn(),
      compactTurns: vi.fn(),
      clearTools: vi.fn(),
      setMode: vi.fn(),
    });
    expect(handled).toBe(true);
  });

  it('dispatches overlay command dynamically without static switch cases', () => {
    const openOverlay = vi.fn();
    const clearTurns = vi.fn();
    const compactTurns = vi.fn();
    const clearTools = vi.fn();
    const setMode = vi.fn();

    const handled = service.dispatchCommand('/provider', {
      openOverlay,
      clearTurns,
      compactTurns,
      clearTools,
      setMode,
    });

    expect(handled).toBe(true);
    expect(openOverlay).toHaveBeenCalledWith('provider');
  });

  it('dispatches /models to the models overlay', () => {
    const openOverlay = vi.fn();
    const clearTurns = vi.fn();
    const compactTurns = vi.fn();
    const clearTools = vi.fn();
    const setMode = vi.fn();

    const handled = service.dispatchCommand('/models', {
      openOverlay,
      clearTurns,
      compactTurns,
      clearTools,
      setMode,
    });

    expect(handled).toBe(true);
    expect(openOverlay).toHaveBeenCalledWith('models');
  });

  it('dispatches clear and compact commands dynamically', () => {
    const openOverlay = vi.fn();
    const clearTurns = vi.fn();
    const compactTurns = vi.fn();
    const clearTools = vi.fn();
    const setMode = vi.fn();

    service.dispatchCommand('/clear', { openOverlay, clearTurns, compactTurns, clearTools, setMode });
    expect(clearTurns).toHaveBeenCalled();

    service.dispatchCommand('/compact', { openOverlay, clearTurns, compactTurns, clearTools, setMode });
    expect(compactTurns).toHaveBeenCalled();

    service.dispatchCommand('/clear-tools', { openOverlay, clearTurns, compactTurns, clearTools, setMode });
    expect(clearTools).toHaveBeenCalled();
  });
});
