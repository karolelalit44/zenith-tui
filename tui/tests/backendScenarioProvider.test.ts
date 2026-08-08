import { describe, expect, it } from 'vitest';
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
