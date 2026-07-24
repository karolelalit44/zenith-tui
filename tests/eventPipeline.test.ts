/**
 * Frontend Event Pipeline Integration Tests
 *
 * Verifies the entire backend→frontend event pipeline:
 *   Backend EventKind → EventMapper → ScenarioEvent → ComponentRegistry
 *
 * Ensures every event type from the backend is correctly handled
 * all the way through to the UI component layer.
 */
import { describe, expect, it } from 'vitest';
import { componentRegistry } from '../src/components/Display/Scenario/componentRegistry';
import { mapEvent } from '../src/services/backend/EventMapper';
import type { JsonRpcEvent } from '../src/services/backend/WebSocketClient';
import type { EventKind, ScenarioEvent } from '../src/types/scenario';

// ── All 20 backend EventKind values ──────────────────────────────────────────
const ALL_EVENT_KINDS: EventKind[] = [
  'thinking',
  'file_create',
  'file_edit',
  'file_delete',
  'terminal',
  'error',
  'warning',
  'retry',
  'success',
  'summary',
  'message',
  'progress',
  'waiting',
  'test_execution',
  'build_step',
  'deployment',
  'analysis',
  'planner_action_panel',
  'mode_mismatch',
  'permission_request',
];

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

// ── EventMapper: every kind produces a valid ScenarioEvent ───────────────────
describe('EventMapper handles all EventKind types', () => {
  const testCases: Array<{ kind: EventKind; data: Record<string, unknown>; expectedKind: EventKind }> = [
    { kind: 'thinking', data: { text: 'Analyzing...' }, expectedKind: 'thinking' },
    { kind: 'file_create', data: { path: '/src/main.ts', content: 'const x = 1;' }, expectedKind: 'file_create' },
    {
      kind: 'file_edit',
      data: { path: '/src/main.ts', old_string: 'old', new_string: 'new' },
      expectedKind: 'file_edit' as EventKind,
    },
    { kind: 'file_delete', data: { path: '/src/old.ts' }, expectedKind: 'file_delete' as EventKind },
    {
      kind: 'terminal',
      data: { command: 'ls -la', output: ['file1', 'file2'], duration: 150 },
      expectedKind: 'terminal' as EventKind,
    },
    {
      kind: 'error',
      data: { message: 'Something failed', code: 'ERR_1', recoverable: true },
      expectedKind: 'error' as EventKind,
    },
    { kind: 'warning', data: { message: 'Deprecated API used' }, expectedKind: 'warning' },
    { kind: 'retry', data: { message: 'Retrying...', attempt: 2 }, expectedKind: 'retry' as EventKind },
    {
      kind: 'success',
      data: { message: 'Done!', iterations: 3, tokenInfo: { used: 100, remaining: 900, total: 1000, percent: 0.1 } },
      expectedKind: 'success' as EventKind,
    },
    { kind: 'summary', data: { action: 'summarize', text: 'Context summarized' }, expectedKind: 'summary' },
    { kind: 'message', data: { text: 'Hello world', partial: false }, expectedKind: 'message' },
    { kind: 'message', data: { text: 'partial ', partial: true }, expectedKind: 'message' },
    { kind: 'progress', data: { percent: 50, status: 'Running tools...', iteration: 2 }, expectedKind: 'progress' },
    { kind: 'waiting', data: { message: 'Waiting...', duration: 2000 }, expectedKind: 'waiting' },
    {
      kind: 'test_execution',
      data: {
        command: 'pytest',
        framework: 'pytest',
        results: [],
        summary: { total: 0, passed: 0, failed: 0, skipped: 0 },
      },
      expectedKind: 'test_execution' as EventKind,
    },
    { kind: 'build_step', data: { step: 'compile', status: 'running' }, expectedKind: 'build_step' },
    { kind: 'deployment', data: { target: 'production', status: 'deploying' }, expectedKind: 'deployment' },
    { kind: 'analysis', data: { tool: 'grep', params: { filepath: 'src/main.ts' } }, expectedKind: 'analysis' },
    { kind: 'planner_action_panel', data: { defaultFilename: 'plan.md' }, expectedKind: 'planner_action_panel' },
    {
      kind: 'mode_mismatch',
      data: { currentMode: 'plan', suggestedMode: 'build', reason: 'File edit required', prompt: 'Edit main.ts' },
      expectedKind: 'mode_mismatch' as EventKind,
    },
  ];

  for (const { kind, data, expectedKind } of testCases) {
    it(`maps '${kind}' to a valid ScenarioEvent`, () => {
      const rpcEvent = makeRpcEvent(kind, data);
      const result: ScenarioEvent = mapEvent(rpcEvent);

      expect(result).toBeDefined();
      expect(result.kind).toBe(expectedKind);
      expect(result.id).toBeTruthy();
      expect(typeof result.id).toBe('string');
    });
  }
});

// ── EventMapper: field-level correctness ─────────────────────────────────────
describe('EventMapper field correctness', () => {
  it('maps thinking with thoughts array', () => {
    const result = mapEvent(makeRpcEvent('thinking', { text: 'Analyzing code...' }));
    expect(result.kind).toBe('thinking');
    if (result.kind === 'thinking') {
      expect(result.thoughts).toBeDefined();
      expect(Array.isArray(result.thoughts)).toBe(true);
      expect(result.thoughts.length).toBeGreaterThan(0);
    }
  });

  it('maps message with correct text and partial flag', () => {
    const result = mapEvent(makeRpcEvent('message', { text: 'Hello', partial: false }));
    expect(result.kind).toBe('message');
    if (result.kind === 'message') {
      expect(result.text).toBe('Hello');
      expect(result.partial).toBe(false);
    }
  });

  it('maps message partial with correct text', () => {
    const result = mapEvent(makeRpcEvent('message', { text: 'partial token', partial: true }));
    expect(result.kind).toBe('message');
    if (result.kind === 'message') {
      expect(result.text).toBe('partial token');
      expect(result.partial).toBe(true);
    }
  });

  it('maps file_create with path and lines', () => {
    const result = mapEvent(makeRpcEvent('file_create', { path: '/src/index.ts', content: 'line1\nline2' }));
    expect(result.kind).toBe('file_create');
    if (result.kind === 'file_create') {
      expect(result.filePath).toBe('/src/index.ts');
      expect(result.lines.length).toBe(2);
      expect(result.lines[0].type).toBe('add');
    }
  });

  it('maps file_edit with removed and added lines', () => {
    const result = mapEvent(
      makeRpcEvent('file_edit', {
        path: '/src/index.ts',
        old_string: 'old',
        new_string: 'new',
      }),
    );
    expect(result.kind).toBe('file_edit');
    if (result.kind === 'file_edit') {
      expect(result.removedLines.length).toBe(1);
      expect(result.addedLines.length).toBe(1);
      expect(result.removedLines[0].type).toBe('remove');
      expect(result.addedLines[0].type).toBe('add');
    }
  });

  it('maps terminal with command and output', () => {
    const result = mapEvent(
      makeRpcEvent('terminal', {
        command: 'npm test',
        output: ['pass', 'fail'],
        duration: 500,
      }),
    );
    expect(result.kind).toBe('terminal');
    if (result.kind === 'terminal') {
      expect(result.command).toBe('npm test');
      expect(result.output).toEqual(['pass', 'fail']);
      expect(result.duration).toBe(500);
    }
  });

  it('maps error with message and code', () => {
    const result = mapEvent(
      makeRpcEvent('error', { message: 'Failed', code: 'E001', recoverable: true, provider: 'nvidia' }),
    );
    expect(result.kind).toBe('error');
    if (result.kind === 'error') {
      expect(result.message).toBe('Failed');
      expect(result.code).toBe('E001');
      expect(result.recoverable).toBe(true);
      expect(result.provider).toBe('nvidia');
    }
  });

  it('maps success with tokenInfo', () => {
    const result = mapEvent(
      makeRpcEvent('success', {
        message: 'Done',
        iterations: 3,
        tokenInfo: { used: 500, remaining: 127500, total: 128000, percent: 0.0039 },
      }),
    );
    expect(result.kind).toBe('success');
    if (result.kind === 'success') {
      expect(result.message).toBe('Done');
      expect(result.iterations).toBe(3);
      expect(result.tokenInfo).toBeDefined();
      expect(result.tokenInfo?.used).toBe(500);
    }
  });

  it('maps progress with percent and iteration', () => {
    const result = mapEvent(makeRpcEvent('progress', { percent: 75, status: 'Running...', iteration: 3 }));
    expect(result.kind).toBe('progress');
    if (result.kind === 'progress') {
      expect(result.percent).toBe(75);
      expect(result.iteration).toBe(3);
    }
  });

  it('maps analysis from tool params', () => {
    const result = mapEvent(makeRpcEvent('analysis', { tool: 'file_read', params: { filepath: 'src/main.ts' } }));
    expect(result.kind).toBe('analysis');
    if (result.kind === 'analysis') {
      expect(result.sections.length).toBeGreaterThan(0);
      expect(result.sections[0].items.some((i) => i.includes('src/main.ts'))).toBe(true);
    }
  });

  it('maps mode_mismatch with all fields', () => {
    const result = mapEvent(
      makeRpcEvent('mode_mismatch', {
        currentMode: 'plan',
        suggestedMode: 'build',
        reason: 'File edit required',
        prompt: 'Edit main.ts',
      }),
    );
    expect(result.kind).toBe('mode_mismatch');
    if (result.kind === 'mode_mismatch') {
      expect(result.currentMode).toBe('plan');
      expect(result.suggestedMode).toBe('build');
      expect(result.reason).toBe('File edit required');
      expect(result.prompt).toBe('Edit main.ts');
    }
  });
});

// ── EventMapper: null/undefined safety ───────────────────────────────────────
describe('EventMapper null-safety', () => {
  it('handles empty data object gracefully', () => {
    const result = mapEvent(makeRpcEvent('thinking', {}));
    expect(result).toBeDefined();
    expect(result.kind).toBe('thinking');
  });

  it('handles null text in message', () => {
    const result = mapEvent(makeRpcEvent('message', { text: null }));
    expect(result.kind).toBe('message');
    if (result.kind === 'message') {
      expect(typeof result.text).toBe('string');
    }
  });

  it('handles undefined output in terminal', () => {
    const result = mapEvent(makeRpcEvent('terminal', {}));
    expect(result.kind).toBe('terminal');
    if (result.kind === 'terminal') {
      expect(Array.isArray(result.output)).toBe(true);
    }
  });

  it('handles missing tokenInfo in success', () => {
    const result = mapEvent(makeRpcEvent('success', {}));
    expect(result.kind).toBe('success');
    if (result.kind === 'success') {
      expect(result.tokenInfo).toBeUndefined();
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

// ── Pipeline integrity: EventKind count matches ─────────────────────────────
describe('Pipeline integrity', () => {
  it('has exactly 20 EventKind values', () => {
    expect(ALL_EVENT_KINDS.length).toBe(20);
  });

  it('no duplicate EventKind values', () => {
    const unique = new Set(ALL_EVENT_KINDS);
    expect(unique.size).toBe(ALL_EVENT_KINDS.length);
  });

  it('EventMapper produces valid kind for every backend kind', () => {
    for (const kind of ALL_EVENT_KINDS) {
      const rpcEvent = makeRpcEvent(kind, {});
      const result = mapEvent(rpcEvent);
      expect(result.kind).toBeTruthy();
      expect(typeof result.kind).toBe('string');
    }
  });
});
