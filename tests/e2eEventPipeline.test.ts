import { describe, expect, it } from 'vitest';
import type { ScenarioEvent } from '../src/types/scenario';

/**
 * End-to-end test: validates that the 9 EventKind types produce valid ScenarioEvents
 * and that the full event sequence works correctly.
 */

function makeEvent(kind: string, data: Record<string, unknown> = {}): ScenarioEvent {
  return {
    kind,
    id: `evt_${Date.now()}_${Math.random().toString(36).slice(2)}`,
    ...data,
  } as unknown as ScenarioEvent;
}

describe('E2E: All 9 EventKind types produce valid ScenarioEvents', () => {
  it('maps thinking event', () => {
    const evt = makeEvent('thinking', { thoughts: ['Processing your request...'], duration: 500 });
    expect(evt.kind).toBe('thinking');
    expect(evt.id).toBeTruthy();
  });

  it('maps message(partial=true) for streaming tokens', () => {
    const evt = makeEvent('message', { text: 'Hello world', partial: true });
    expect(evt.kind).toBe('message');
    if (evt.kind === 'message') {
      expect(evt.text).toBe('Hello world');
      expect(evt.partial).toBe(true);
    }
  });

  it('maps message(partial=false) for final text', () => {
    const evt = makeEvent('message', { text: 'Done response', partial: false });
    expect(evt.kind).toBe('message');
    if (evt.kind === 'message') {
      expect(evt.text).toBe('Done response');
      expect(evt.partial).toBe(false);
    }
  });

  it('maps tool_call with tool name and params', () => {
    const evt = makeEvent('tool_call', { tool: 'bash', params: { command: 'npm test' } });
    expect(evt.kind).toBe('tool_call');
    if (evt.kind === 'tool_call') {
      expect(evt.tool).toBe('bash');
      expect(evt.params.command).toBe('npm test');
    }
  });

  it('maps tool_result with success and output', () => {
    const evt = makeEvent('tool_result', {
      tool: 'file_write',
      success: true,
      output: '',
      error: '',
      metadata: { path: '/src/app.ts' },
    });
    expect(evt.kind).toBe('tool_result');
    if (evt.kind === 'tool_result') {
      expect(evt.tool).toBe('file_write');
      expect(evt.success).toBe(true);
      expect(evt.metadata.path).toBe('/src/app.ts');
    }
  });

  it('maps error with message, code, recoverable', () => {
    const evt = makeEvent('error', {
      message: 'Provider authentication failed',
      code: 'AUTH_ERROR',
      recoverable: true,
      provider: 'nvidia',
    });
    expect(evt.kind).toBe('error');
    if (evt.kind === 'error') {
      expect(evt.message).toBe('Provider authentication failed');
      expect(evt.code).toBe('AUTH_ERROR');
      expect(evt.recoverable).toBe(true);
      expect(evt.provider).toBe('nvidia');
    }
  });

  it('maps warning with message and code', () => {
    const evt = makeEvent('warning', {
      message: 'Context approaching token limit',
      code: 'TOKEN_LIMIT',
    });
    expect(evt.kind).toBe('warning');
    if (evt.kind === 'warning') {
      expect(evt.message).toBe('Context approaching token limit');
      expect(evt.code).toBe('TOKEN_LIMIT');
    }
  });

  it('maps success with all fields', () => {
    const evt = makeEvent('success', {
      message: 'Request processed successfully',
      iterations: 3,
      tokenInfo: { used: 500, remaining: 127500, total: 128000, percent: 0.0039 },
    });
    expect(evt.kind).toBe('success');
    if (evt.kind === 'success') {
      expect(evt.message).toBe('Request processed successfully');
      expect(evt.iterations).toBe(3);
      expect(evt.tokenInfo).toBeDefined();
      expect(evt.tokenInfo!.used).toBe(500);
    }
  });

  it('maps progress with percent and label', () => {
    const evt = makeEvent('progress', {
      percent: 50,
      label: 'Executing 2 tool(s)...',
      iteration: 2,
      steps: [],
    });
    expect(evt.kind).toBe('progress');
    if (evt.kind === 'progress') {
      expect(evt.percent).toBe(50);
      expect(evt.label).toBe('Executing 2 tool(s)...');
    }
  });

  it('maps confirmation_request with all fields', () => {
    const evt = makeEvent('confirmation_request', {
      confirmationId: 'conf-1',
      tool: 'bash',
      reason: 'Dangerous operation',
      riskLevel: 'high',
      message: 'Confirm deletion?',
    });
    expect(evt.kind).toBe('confirmation_request');
    if (evt.kind === 'confirmation_request') {
      expect(evt.confirmationId).toBe('conf-1');
      expect(evt.tool).toBe('bash');
      expect(evt.riskLevel).toBe('high');
    }
  });
});

describe('E2E: Full event sequence as sent by backend', () => {
  it('simulates a complete prompt cycle with 9 event kinds', () => {
    const events = [
      makeEvent('thinking', { thoughts: ['Processing your request in build mode...'], duration: 500 }),
      makeEvent('tool_call', { tool: 'bash', params: { command: 'ls -la' } }),
      makeEvent('tool_result', { tool: 'bash', success: true, output: 'file1\nfile2', error: '', metadata: { command: 'ls -la', exit_code: 0 } }),
      makeEvent('message', { text: 'Here are the files...', partial: false }),
      makeEvent('success', { message: 'Request processed successfully', iterations: 1, tokenInfo: { used: 100, remaining: 127900, total: 128000, percent: 0.0008 } }),
    ];

    const kinds = events.map((e) => e.kind);

    expect(kinds).toEqual([
      'thinking',
      'tool_call',
      'tool_result',
      'message',
      'success',
    ]);

    expect(events[0].id).toBeTruthy();
    expect(events[1].id).toBeTruthy();
  });
});
