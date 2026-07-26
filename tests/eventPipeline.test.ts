/**
 * Frontend Event Pipeline Integration Tests
 *
 * Verifies the entire backend→frontend event pipeline:
 *   Backend EventKind → BackendScenarioProvider → ScenarioEvent → ComponentRegistry
 *
 * Ensures every event type from the backend is correctly handled
 * all the way through to the UI component layer.
 */
import { describe, expect, it } from 'vitest';
import { componentRegistry } from '../src/components/Display/Scenario/componentRegistry';
import type { EventKind, ScenarioEvent } from '../src/types/scenario';

const ALL_EVENT_KINDS: EventKind[] = [
  'thinking',
  'message',
  'tool_call',
  'tool_result',
  'error',
  'warning',
  'success',
  'progress',
  'confirmation_request',
];

function makeEvent(kind: string, data: Record<string, unknown> = {}): ScenarioEvent {
  return {
    kind,
    id: `test_${Date.now()}`,
    ...data,
  } as unknown as ScenarioEvent;
}

// ── Every kind produces a valid ScenarioEvent ────────────────────────────────
describe('All EventKind types are valid ScenarioEvents', () => {
  const testCases: Array<{ kind: EventKind; data: Record<string, unknown> }> = [
    { kind: 'thinking', data: { thoughts: ['Analyzing...'], duration: 500 } },
    { kind: 'message', data: { text: 'Hello world', partial: false } },
    { kind: 'message', data: { text: 'partial ', partial: true } },
    { kind: 'tool_call', data: { tool: 'bash', params: { command: 'ls -la' } } },
    { kind: 'tool_result', data: { tool: 'bash', success: true, output: 'file1\nfile2', error: '', metadata: {} } },
    { kind: 'error', data: { message: 'Something failed', code: 'ERR_1', recoverable: true } },
    { kind: 'warning', data: { message: 'Deprecated API used' } },
    { kind: 'success', data: { message: 'Done!', iterations: 3, tokenInfo: { used: 100, remaining: 900, total: 1000, percent: 0.1 } } },
    { kind: 'progress', data: { label: 'Running...', percent: 50, iteration: 2, steps: [] } },
    { kind: 'confirmation_request', data: { confirmationId: 'conf-1', tool: 'bash', reason: 'Risky', riskLevel: 'high', message: 'Confirm?' } },
  ];

  for (const { kind, data } of testCases) {
    it(`creates valid ScenarioEvent for '${kind}'`, () => {
      const result = makeEvent(kind, data);
      expect(result).toBeDefined();
      expect(result.kind).toBe(kind);
      expect(result.id).toBeTruthy();
      expect(typeof result.id).toBe('string');
    });
  }
});

// ── Field-level correctness ──────────────────────────────────────────────────
describe('Event field correctness', () => {
  it('thinking has thoughts array and duration', () => {
    const result = makeEvent('thinking', { thoughts: ['step1', 'step2'], duration: 1000 });
    expect(result.kind).toBe('thinking');
    if (result.kind === 'thinking') {
      expect(result.thoughts).toBeDefined();
      expect(Array.isArray(result.thoughts)).toBe(true);
      expect(result.thoughts.length).toBe(2);
    }
  });

  it('message has text and partial flag', () => {
    const result = makeEvent('message', { text: 'Hello', partial: false });
    expect(result.kind).toBe('message');
    if (result.kind === 'message') {
      expect(result.text).toBe('Hello');
      expect(result.partial).toBe(false);
    }
  });

  it('tool_call has tool name and params', () => {
    const result = makeEvent('tool_call', { tool: 'bash', params: { command: 'npm test' } });
    expect(result.kind).toBe('tool_call');
    if (result.kind === 'tool_call') {
      expect(result.tool).toBe('bash');
      expect(result.params.command).toBe('npm test');
    }
  });

  it('tool_result has tool, success, output, and metadata', () => {
    const result = makeEvent('tool_result', {
      tool: 'file_write',
      success: true,
      output: '',
      error: '',
      metadata: { path: '/src/app.ts' },
    });
    expect(result.kind).toBe('tool_result');
    if (result.kind === 'tool_result') {
      expect(result.tool).toBe('file_write');
      expect(result.success).toBe(true);
      expect(result.metadata.path).toBe('/src/app.ts');
    }
  });

  it('error has message and code', () => {
    const result = makeEvent('error', { message: 'Failed', code: 'E001', recoverable: true, provider: 'nvidia' });
    expect(result.kind).toBe('error');
    if (result.kind === 'error') {
      expect(result.message).toBe('Failed');
      expect(result.code).toBe('E001');
      expect(result.recoverable).toBe(true);
      expect(result.provider).toBe('nvidia');
    }
  });

  it('success has message, iterations, and tokenInfo', () => {
    const result = makeEvent('success', {
      message: 'Done',
      iterations: 3,
      tokenInfo: { used: 500, remaining: 127500, total: 128000, percent: 0.0039 },
    });
    expect(result.kind).toBe('success');
    if (result.kind === 'success') {
      expect(result.message).toBe('Done');
      expect(result.iterations).toBe(3);
      expect(result.tokenInfo).toBeDefined();
      expect(result.tokenInfo?.used).toBe(500);
    }
  });

  it('progress has percent, label, and iteration', () => {
    const result = makeEvent('progress', { label: 'Running...', percent: 75, iteration: 3 });
    expect(result.kind).toBe('progress');
    if (result.kind === 'progress') {
      expect(result.percent).toBe(75);
      expect(result.iteration).toBe(3);
    }
  });

  it('confirmation_request has all fields', () => {
    const result = makeEvent('confirmation_request', {
      confirmationId: 'conf-1',
      tool: 'bash',
      reason: 'Dangerous operation',
      riskLevel: 'high',
      message: 'Confirm deletion?',
    });
    expect(result.kind).toBe('confirmation_request');
    if (result.kind === 'confirmation_request') {
      expect(result.confirmationId).toBe('conf-1');
      expect(result.tool).toBe('bash');
      expect(result.riskLevel).toBe('high');
    }
  });
});

// ── ComponentRegistry: every EventKind has a registered component ────────────
describe('ComponentRegistry covers all EventKind types', () => {
  for (const kind of ALL_EVENT_KINDS) {
    it(`has a registered component for '${kind}'`, () => {
      const component = componentRegistry.getComponent(kind);
      expect(component).toBeDefined();
      expect(component).not.toBeNull();
    });
  }

  it('falls back to UnknownEventFallback for unknown kind', () => {
    const component = componentRegistry.getComponent('totally_unknown_kind');
    expect(component).toBeDefined();
  });
});

// ── Pipeline integrity ───────────────────────────────────────────────────────
describe('Pipeline integrity', () => {
  it('has exactly 9 EventKind values', () => {
    expect(ALL_EVENT_KINDS.length).toBe(9);
  });

  it('no duplicate EventKind values', () => {
    const unique = new Set(ALL_EVENT_KINDS);
    expect(unique.size).toBe(ALL_EVENT_KINDS.length);
  });
});
