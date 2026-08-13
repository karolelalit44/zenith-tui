import { afterEach, describe, expect, it, vi } from 'vitest';
import { backendScenarioProvider } from '../src/services/transport/BackendScenarioProvider';
import { type JsonRpcEvent, wsClient } from '../src/services/transport/WebSocketClient';

function makeRpcEvent(kind: string, data: Record<string, unknown> = {}): JsonRpcEvent {
  return {
    jsonrpc: '2.0',
    method: 'event',
    params: {
      kind,
      id: `test_${Date.now()}`,
      data,
    },
  };
}

describe('BackendScenarioProvider Multi-Step & Terminal Event Handling', () => {
  it('does not finalize on intermediate tool result success events', () => {
    let completed = false;
    const eventsRecv: unknown[] = [];

    const scenario = backendScenarioProvider.resolve('test prompt', 'build');
    const _runner = backendScenarioProvider.execute(
      scenario,
      (evt) => {
        eventsRecv.push(evt);
      },
      () => {
        completed = true;
      },
    );

    // Emit intermediate tool_result success event (tool="glob")
    const toolResultEvent = makeRpcEvent('success', {
      tool: 'glob',
      result: { success: true, output: 'file1.py\nfile2.py', error: '' },
    });

    // Simulate WS event arriving
    (wsClient as unknown as { emitter: { emit: (name: string, data: unknown) => void } }).emitter.emit(
      'event',
      toolResultEvent,
    );

    expect(eventsRecv.length).toBe(1);
    expect(completed).toBe(false); // MUST NOT BE COMPLETED!

    _runner.abort();
  });

  it('finalizes on recoverable tool error events (retry banner)', () => {
    let completed = false;
    const eventsRecv: unknown[] = [];

    const scenario = backendScenarioProvider.resolve('test prompt', 'build');
    const _runner = backendScenarioProvider.execute(
      scenario,
      (evt) => {
        eventsRecv.push(evt);
      },
      () => {
        completed = true;
      },
    );

    // Emit recoverable tool error event (code="TOOL_ERROR_BASH", recoverable=true)
    const toolErrorEvent = makeRpcEvent('error', {
      message: "'ls' is not recognized as an internal command",
      code: 'TOOL_ERROR_BASH',
      recoverable: true,
    });

    (wsClient as unknown as { emitter: { emit: (name: string, data: unknown) => void } }).emitter.emit(
      'event',
      toolErrorEvent,
    );

    expect(eventsRecv.length).toBe(1);
    expect(completed).toBe(true); // MUST BE COMPLETED so retry banner shows

    _runner.abort();
  });

  it('finalizes on final prompt success event', () => {
    let completed = false;
    const eventsRecv: unknown[] = [];

    const scenario = backendScenarioProvider.resolve('test prompt', 'build');
    const _runner = backendScenarioProvider.execute(
      scenario,
      (evt) => {
        eventsRecv.push(evt);
      },
      () => {
        completed = true;
      },
    );

    // Emit intermediate tool success
    (wsClient as unknown as { emitter: { emit: (name: string, data: unknown) => void } }).emitter.emit(
      'event',
      makeRpcEvent('success', {
        tool: 'glob',
        result: { success: true, output: 'files...', error: '' },
      }),
    );
    expect(completed).toBe(false);

    // Emit final prompt success event
    const finalSuccessEvent = makeRpcEvent('success', {
      message: 'Request processed successfully',
      iterations: 2,
      tokenInfo: { used: 100, remaining: 900, total: 1000, percent: 0.1 },
    });

    (wsClient as unknown as { emitter: { emit: (name: string, data: unknown) => void } }).emitter.emit(
      'event',
      finalSuccessEvent,
    );

    expect(eventsRecv.length).toBe(2);
    expect(completed).toBe(true); // MUST BE COMPLETED NOW!
  });

  it('finalizes on unrecoverable fatal error event', () => {
    let completed = false;
    const eventsRecv: unknown[] = [];

    const scenario = backendScenarioProvider.resolve('test prompt', 'build');
    const _runner = backendScenarioProvider.execute(
      scenario,
      (evt) => {
        eventsRecv.push(evt);
      },
      () => {
        completed = true;
      },
    );

    const fatalErrorEvent = makeRpcEvent('error', {
      message: 'Max iterations (10) exceeded',
      code: 'MAX_ITERATIONS',
      recoverable: false,
    });

    (wsClient as unknown as { emitter: { emit: (name: string, data: unknown) => void } }).emitter.emit(
      'event',
      fatalErrorEvent,
    );

    expect(eventsRecv.length).toBe(1);
    expect(completed).toBe(true); // MUST BE COMPLETED!
  });
});

describe('Context compaction events map to typed events (no UNKNOWN_EVENT)', () => {
  const emit = (kind: string, data: Record<string, unknown>) =>
    (wsClient as unknown as { emitter: { emit: (name: string, data: unknown) => void } }).emitter.emit(
      'event',
      makeRpcEvent(kind, data),
    );

  function runOnce(kind: string, data: Record<string, unknown>) {
    const eventsRecv: Array<{ kind: string; message?: string }> = [];
    const scenario = backendScenarioProvider.resolve('test prompt', 'build');
    const runner = backendScenarioProvider.execute(
      scenario,
      (evt) => {
        eventsRecv.push(evt as { kind: string; message?: string });
      },
      () => {},
    );
    emit(kind, data);
    runner.abort();
    return eventsRecv;
  }

  it('maps context_compacted to a typed event with a readable message', () => {
    const [evt] = runOnce('context_compacted', {
      tool: 'glob',
      charsRemoved: 12340,
      tokensSaved: 1234,
      reason: 'output too large',
    });
    expect(evt).toBeDefined();
    expect(evt.kind).toBe('context_compacted');
    expect(evt.message).toContain('Compacted glob output');
    expect(evt.message).toContain('1234');
    expect(evt.message).not.toContain('Unknown event');
  });

  it('maps context_compaction_started to a typed event', () => {
    const [evt] = runOnce('context_compaction_started', {
      reason: 'context approaching limit',
      used: 90000,
      total: 100000,
    });
    expect(evt.kind).toBe('context_compaction_started');
    expect(evt.message).toContain('started');
    expect(evt.message).toContain('90%');
    expect(evt.message).not.toContain('Unknown event');
  });

  it('maps context_compaction_ended to a typed event', () => {
    const [evt] = runOnce('context_compaction_ended', {
      reason: 'context approaching limit',
      used: 30000,
      total: 100000,
      tokensSaved: 60000,
      summaryChars: 1200,
    });
    expect(evt.kind).toBe('context_compaction_ended');
    expect(evt.message).toContain('finished');
    expect(evt.message).toContain('60000');
    expect(evt.message).not.toContain('Unknown event');
  });

  it('maps turn_manifest to a typed event (no UNKNOWN_EVENT)', () => {
    const [evt] = runOnce('turn_manifest', {
      created: ['a.txt'],
      modified: ['b.txt'],
      remaining: ['x'],
      completed: false,
      stalled: true,
      files: [
        { path: 'a.txt', exists: true, size: 123 },
        { path: 'b.txt', exists: true, size: 45 },
      ],
    });
    expect(evt.kind).toBe('turn_manifest');
    expect(evt).toMatchObject({
      created: ['a.txt'],
      modified: ['b.txt'],
      remaining: ['x'],
      completed: false,
      stalled: true,
    });
  });

  it('maps message iteration when the server provides it', () => {
    const [evt] = runOnce('message', { text: 'done', partial: false, iteration: 3 });
    expect(evt.kind).toBe('message');
    expect(evt).toMatchObject({ text: 'done', partial: false, iteration: 3 });
  });
});

describe('executeCompaction (manual /compact pipeline)', () => {
  const emit = (kind: string, data: Record<string, unknown>) =>
    (wsClient as unknown as { emitter: { emit: (name: string, data: unknown) => void } }).emitter.emit(
      'event',
      makeRpcEvent(kind, data),
    );

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('streams real compaction events and completes on context_compaction_ended', () => {
    const compactSpy = vi.spyOn(wsClient, 'contextCompact').mockResolvedValue({ summary: 'ok', cleared: 1 });
    let completed = false;
    const kinds: string[] = [];

    const runner = backendScenarioProvider.executeCompaction(
      'sess-1',
      (evt) => {
        kinds.push(evt.kind);
      },
      () => {
        completed = true;
      },
    );

    expect(compactSpy).toHaveBeenCalledWith('sess-1');

    emit('context_compaction_started', { used: 90000, total: 100000 });
    emit('context_compaction_phase', { phase: 'compacting', used: 60000, total: 100000 });
    emit('context_compacted', { tool: 'glob', charsRemoved: 1234, tokensSaved: 100 });
    expect(completed).toBe(false);

    emit('context_compaction_ended', { used: 30000, total: 100000, tokensSaved: 60000 });

    expect(completed).toBe(true);
    expect(kinds).toEqual([
      'context_compaction_started',
      'context_compaction_phase',
      'context_compacted',
      'context_compaction_ended',
    ]);
    runner.abort();
  });

  it('ignores non-compaction events while the compaction runs', () => {
    vi.spyOn(wsClient, 'contextCompact').mockResolvedValue({ summary: 'ok', cleared: 1 });
    let completed = false;
    const kinds: string[] = [];

    const runner = backendScenarioProvider.executeCompaction(
      'sess-1',
      (evt) => {
        kinds.push(evt.kind);
      },
      () => {
        completed = true;
      },
    );

    emit('message', { text: 'unrelated', partial: false });
    emit('context_compaction_ended', { used: 30000, total: 100000 });
    expect(completed).toBe(true);
    expect(kinds).toEqual(['context_compaction_ended']);
    runner.abort();
  });

  it('reports an error and completes when the context.compact RPC rejects', async () => {
    vi.spyOn(wsClient, 'contextCompact').mockRejectedValue(new Error('No active session'));
    let completed = false;
    const eventsRecv: Array<{ kind: string; message?: string }> = [];

    const runner = backendScenarioProvider.executeCompaction(
      'sess-1',
      (evt) => {
        eventsRecv.push(evt as { kind: string; message?: string });
      },
      () => {
        completed = true;
      },
    );

    await new Promise((r) => setTimeout(r, 0));
    expect(completed).toBe(true);
    expect(eventsRecv.some((e) => e.kind === 'error')).toBe(true);
    expect(eventsRecv.some((e) => e.message?.includes('No active session'))).toBe(true);
    runner.abort();
  });

  it('completes when the RPC resolves even if context_compaction_ended was not emitted', async () => {
    vi.spyOn(wsClient, 'contextCompact').mockResolvedValue({ summary: 'ok', cleared: 1 });
    let completed = false;

    const runner = backendScenarioProvider.executeCompaction(
      'sess-1',
      () => {},
      () => {
        completed = true;
      },
    );

    await new Promise((r) => setTimeout(r, 0));
    expect(completed).toBe(true);
    runner.abort();
  });
});
