import { describe, expect, it } from 'vitest';
import { mapEvent } from '../src/services/backend/EventMapper';
import type { JsonRpcEvent } from '../src/services/backend/WebSocketClient';

/**
 * End-to-end test: raw JSON-RPC payloads from backend → EventMapper → ScenarioEvent.
 *
 * These payloads exactly match what the Python backend sends over WebSocket.
 * Validates that the frontend correctly maps every event kind.
 */

function makeRpcEvent(kind: string, data: Record<string, unknown>, sessionId = 'e2e-session-1'): JsonRpcEvent {
  return {
    jsonrpc: '2.0',
    method: 'event',
    params: {
      kind,
      id: `evt_${Date.now()}_${Math.random().toString(36).slice(2)}`,
      session_id: sessionId,
      timestamp: Date.now(),
      data,
    },
  };
}

describe('E2E: Backend JSON-RPC → EventMapper → ScenarioEvent', () => {
  it('maps thinking event', () => {
    const rpc = makeRpcEvent('thinking', { text: 'Processing your request in build mode...' });
    const evt = mapEvent(rpc);
    expect(evt.kind).toBe('thinking');
    expect(evt.id).toBeTruthy();
  });

  it('maps message(partial=true) for streaming tokens', () => {
    const rpc = makeRpcEvent('message', { text: 'Hello world', partial: true });
    const evt = mapEvent(rpc);
    expect(evt.kind).toBe('message');
    if (evt.kind === 'message') {
      expect(evt.text).toBe('Hello world');
      expect(evt.partial).toBe(true);
    }
  });

  it('maps message(partial=false) for final text', () => {
    const rpc = makeRpcEvent('message', { text: 'Done response', partial: false });
    const evt = mapEvent(rpc);
    expect(evt.kind).toBe('message');
    if (evt.kind === 'message') {
      expect(evt.text).toBe('Done response');
      expect(evt.partial).toBe(false);
    }
  });

  it('maps file_create with path and content', () => {
    const rpc = makeRpcEvent('file_create', {
      path: '/src/main.ts',
      content: 'const x = 1;\nconst y = 2;',
    });
    const evt = mapEvent(rpc);
    expect(evt.kind).toBe('file_create');
    if (evt.kind === 'file_create') {
      expect(evt.filePath).toBe('/src/main.ts');
      expect(evt.lines).toHaveLength(2);
      expect(evt.lines[0].type).toBe('add');
      expect(evt.language).toBe('typescript');
    }
  });

  it('maps file_edit with old/new strings', () => {
    const rpc = makeRpcEvent('file_edit', {
      path: '/src/app.py',
      old_string: 'x = 1',
      new_string: 'x = 2',
    });
    const evt = mapEvent(rpc);
    expect(evt.kind).toBe('file_edit');
    if (evt.kind === 'file_edit') {
      expect(evt.filePath).toBe('/src/app.py');
      expect(evt.removedLines).toHaveLength(1);
      expect(evt.removedLines[0].type).toBe('remove');
      expect(evt.addedLines).toHaveLength(1);
      expect(evt.addedLines[0].type).toBe('add');
      expect(evt.language).toBe('python');
    }
  });

  it('maps file_delete with path', () => {
    const rpc = makeRpcEvent('file_delete', { path: '/src/old.ts' });
    const evt = mapEvent(rpc);
    expect(evt.kind).toBe('file_delete');
    if (evt.kind === 'file_delete') {
      expect(evt.filePath).toBe('/src/old.ts');
    }
  });

  it('maps terminal with command and output', () => {
    const rpc = makeRpcEvent('terminal', {
      command: 'npm test',
      output: ['PASS src/app.test.ts', 'Tests: 1 passed'],
      duration: 500,
    });
    const evt = mapEvent(rpc);
    expect(evt.kind).toBe('terminal');
    if (evt.kind === 'terminal') {
      expect(evt.command).toBe('npm test');
      expect(evt.output).toHaveLength(2);
      expect(evt.duration).toBe(500);
    }
  });

  it('maps error with message, code, recoverable', () => {
    const rpc = makeRpcEvent('error', {
      message: 'Provider authentication failed',
      code: 'AUTH_ERROR',
      recoverable: true,
      provider: 'nvidia',
    });
    const evt = mapEvent(rpc);
    expect(evt.kind).toBe('error');
    if (evt.kind === 'error') {
      expect(evt.message).toBe('Provider authentication failed');
      expect(evt.code).toBe('AUTH_ERROR');
      expect(evt.recoverable).toBe(true);
      expect(evt.provider).toBe('nvidia');
    }
  });

  it('maps warning with message and code', () => {
    const rpc = makeRpcEvent('warning', {
      message: 'Context approaching token limit',
      code: 'TOKEN_LIMIT',
    });
    const evt = mapEvent(rpc);
    expect(evt.kind).toBe('warning');
    if (evt.kind === 'warning') {
      expect(evt.message).toBe('Context approaching token limit');
      expect(evt.code).toBe('TOKEN_LIMIT');
    }
  });

  it('maps retry with attempt number', () => {
    const rpc = makeRpcEvent('retry', {
      message: 'Rate limited, retrying...',
      attempt: 3,
    });
    const evt = mapEvent(rpc);
    expect(evt.kind).toBe('retry');
    if (evt.kind === 'retry') {
      expect(evt.attempt).toBe(3);
      expect(evt.message).toBe('Rate limited, retrying...');
    }
  });

  it('maps success with all fields', () => {
    const rpc = makeRpcEvent('success', {
      message: 'Request processed successfully',
      iterations: 3,
      tokenInfo: { used: 500, remaining: 127500, total: 128000, percent: 0.0039 },
      filesCreated: ['/src/app.ts'],
      commandsExecuted: ['npm test'],
    });
    const evt = mapEvent(rpc);
    expect(evt.kind).toBe('success');
    if (evt.kind === 'success') {
      expect(evt.message).toBe('Request processed successfully');
      expect(evt.iterations).toBe(3);
      expect(evt.tokenInfo).toBeDefined();
      expect(evt.tokenInfo!.used).toBe(500);
      expect(evt.filesCreated).toContain('/src/app.ts');
    }
  });

  it('maps summary with title and description', () => {
    const rpc = makeRpcEvent('summary', {
      title: 'Completed',
      description: 'All tasks done',
      filesCreated: ['/src/new.ts'],
    });
    const evt = mapEvent(rpc);
    expect(evt.kind).toBe('summary');
    if (evt.kind === 'summary') {
      expect(evt.title).toBe('Completed');
      expect(evt.description).toBe('All tasks done');
      expect(evt.filesCreated).toContain('/src/new.ts');
    }
  });

  it('maps progress with percent and label', () => {
    const rpc = makeRpcEvent('progress', {
      percent: 50,
      label: 'Executing 2 tool(s)...',
      iteration: 2,
      steps: [],
    });
    const evt = mapEvent(rpc);
    expect(evt.kind).toBe('progress');
    if (evt.kind === 'progress') {
      expect(evt.percent).toBe(50);
      expect(evt.label).toBe('Executing 2 tool(s)...');
    }
  });

  it('maps analysis with tool name and sections', () => {
    const rpc = makeRpcEvent('analysis', {
      tool: 'file_write',
      params: { filepath: '/src/app.ts' },
      text: 'Executing file_write...',
    });
    const evt = mapEvent(rpc);
    expect(evt.kind).toBe('analysis');
    if (evt.kind === 'analysis') {
      expect(evt.title).toContain('file_write');
      expect(evt.sections.length).toBeGreaterThan(0);
    }
  });

  it('maps waiting with message and duration', () => {
    const rpc = makeRpcEvent('waiting', {
      message: 'Waiting for backend response...',
      duration: 2000,
    });
    const evt = mapEvent(rpc);
    expect(evt.kind).toBe('waiting');
    if (evt.kind === 'waiting') {
      expect(evt.message).toBe('Waiting for backend response...');
      expect(evt.duration).toBe(2000);
    }
  });

  it('maps mode_mismatch with all fields', () => {
    const rpc = makeRpcEvent('mode_mismatch', {
      currentMode: 'plan',
      suggestedMode: 'build',
      reason: 'File edit required',
      prompt: 'Edit main.ts',
    });
    const evt = mapEvent(rpc);
    expect(evt.kind).toBe('mode_mismatch');
    if (evt.kind === 'mode_mismatch') {
      expect(evt.currentMode).toBe('plan');
      expect(evt.suggestedMode).toBe('build');
      expect(evt.reason).toBe('File edit required');
      expect(evt.prompt).toBe('Edit main.ts');
    }
  });

  it('unknown kind falls back to message', () => {
    const rpc = makeRpcEvent('future_kind', { foo: 'bar' });
    const evt = mapEvent(rpc);
    expect(evt.kind).toBe('message');
    if (evt.kind === 'message') {
      expect(evt.text).toContain('future_kind');
    }
  });

  it('handles null/undefined data fields gracefully', () => {
    const rpc = makeRpcEvent('message', { text: null, partial: null });
    const evt = mapEvent(rpc);
    expect(evt.kind).toBe('message');
    if (evt.kind === 'message') {
      expect(typeof evt.text).toBe('string');
    }
  });
});

describe('E2E: Full event sequence as sent by backend', () => {
  it('simulates a complete prompt cycle', () => {
    const sessionId = 'e2e-seq-1';
    const events = [
      makeRpcEvent('thinking', { text: 'Processing your request in build mode...' }, sessionId),
      makeRpcEvent('message', { text: 'Hello ', partial: true }, sessionId),
      makeRpcEvent('message', { text: 'Hello world', partial: true }, sessionId),
      makeRpcEvent('message', { text: 'Hello world response', partial: false }, sessionId),
      makeRpcEvent(
        'success',
        {
          message: 'Request processed successfully',
          iterations: 1,
          tokenInfo: { used: 100, remaining: 127900, total: 128000, percent: 0.0008 },
        },
        sessionId,
      ),
    ];

    const mapped = events.map((e) => mapEvent(e));

    expect(mapped[0].kind).toBe('thinking');
    expect(mapped[1].kind).toBe('message');
    expect(mapped[2].kind).toBe('message');
    expect(mapped[3].kind).toBe('message');
    expect(mapped[4].kind).toBe('success');

    if (mapped[1].kind === 'message' && mapped[2].kind === 'message') {
      expect(mapped[1].partial).toBe(true);
      expect(mapped[2].partial).toBe(true);
    }
    if (mapped[3].kind === 'message') {
      expect(mapped[3].partial).toBe(false);
    }
    if (mapped[4].kind === 'success') {
      expect(mapped[4].iterations).toBe(1);
    }
  });

  it('simulates a tool-use cycle: thinking → analysis → terminal → file_edit → success', () => {
    const sessionId = 'e2e-seq-2';
    const events = [
      makeRpcEvent('thinking', { text: 'Analyzing...' }, sessionId),
      makeRpcEvent('progress', { percent: 33, label: 'Executing 1 tool(s)...', iteration: 1 }, sessionId),
      makeRpcEvent('analysis', { tool: 'bash', params: { command: 'npm test' }, text: 'Executing bash...' }, sessionId),
      makeRpcEvent('terminal', { command: 'npm test', output: ['PASS'], duration: 200 }, sessionId),
      makeRpcEvent('progress', { percent: 66, label: 'Executing 1 tool(s)...', iteration: 2 }, sessionId),
      makeRpcEvent(
        'analysis',
        { tool: 'file_edit', params: { filepath: '/src/app.ts' }, text: 'Executing file_edit...' },
        sessionId,
      ),
      makeRpcEvent('file_edit', { path: '/src/app.ts', old_string: 'x = 1', new_string: 'x = 2' }, sessionId),
      makeRpcEvent('success', { message: 'Done', iterations: 2 }, sessionId),
    ];

    const mapped = events.map((e) => mapEvent(e));
    const kinds = mapped.map((e) => e.kind);

    expect(kinds).toEqual([
      'thinking',
      'progress',
      'analysis',
      'terminal',
      'progress',
      'analysis',
      'file_edit',
      'success',
    ]);
  });
});
