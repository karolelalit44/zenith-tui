import { describe, expect, test } from 'vitest';
import type { ScenarioEvent, ToolCallEvent, ToolResultEvent } from '../src/types/scenario';
import { foldReadOnlyRepeats, pairToolEvents, progressDuplicatesPendingToolStep } from '../src/utils/pairToolEvents';

const call = (id: string, tool: string, params: Record<string, unknown> = {}): ToolCallEvent => ({
  kind: 'tool_call',
  id,
  tool,
  params,
});

const result = (id: string, tool: string, success = true): ToolResultEvent => ({
  kind: 'tool_result',
  id,
  tool,
  success,
  output: 'out',
  error: '',
  metadata: { duration_ms: 12 },
});

describe('pairToolEvents', () => {
  test('folds a call+result pair into ONE completed tool_step', () => {
    const events: ScenarioEvent[] = [call('c1', 'bash', { command: 'npm test' }), result('r1', 'bash')];
    const out = pairToolEvents(events);
    expect(out).toHaveLength(1);
    expect(out[0]).toMatchObject({
      kind: 'tool_step',
      id: 'c1',
      tool: 'bash',
      success: true,
      output: 'out',
      pending: false,
      params: { command: 'npm test' },
      metadata: { duration_ms: 12 },
    });
  });

  test('pairs FIFO when ids differ (persisted uuids)', () => {
    const events: ScenarioEvent[] = [
      call('uuid-a', 'file_read', { path: 'a.ts' }),
      result('uuid-b', 'file_read', false),
    ];
    const out = pairToolEvents(events);
    expect(out).toHaveLength(1);
    expect(out[0]).toMatchObject({ kind: 'tool_step', success: false });
  });

  test('keeps interleaved non-tool events in place', () => {
    const events: ScenarioEvent[] = [
      { kind: 'thinking', id: 't', thoughts: ['x'], duration: 1 },
      call('c1', 'grep', { pattern: 'p' }),
      result('r1', 'grep'),
      { kind: 'message', id: 'm', text: 'done', partial: false },
    ];
    const out = pairToolEvents(events);
    expect(out.map((e) => e.kind)).toEqual(['thinking', 'tool_step', 'message']);
  });

  test('unpaired trailing call becomes an interrupted step, not a drop', () => {
    const out = pairToolEvents([call('c1', 'bash')]);
    expect(out).toHaveLength(1);
    expect(out[0]).toMatchObject({
      kind: 'tool_step',
      success: false,
      metadata: { interrupted: true },
    });
  });

  test('orphan result becomes a standalone completed step', () => {
    const out = pairToolEvents([result('r1', 'glob')]);
    expect(out).toHaveLength(1);
    expect(out[0]).toMatchObject({ kind: 'tool_step', id: 'r1', tool: 'glob', success: true });
  });

  test('passes live tool_step events through untouched', () => {
    const step: ScenarioEvent = {
      kind: 'tool_step',
      id: 's1',
      tool: 'bash',
      params: {},
      success: true,
      output: '',
      error: '',
      metadata: {},
      pending: false,
    };
    expect(pairToolEvents([step])).toEqual([step]);
  });
});

describe('foldReadOnlyRepeats', () => {
  const step = (id: string, tool: string, value: string, success = true): ScenarioEvent => ({
    kind: 'tool_step',
    id,
    tool,
    params: { path: value },
    success,
    output: 'x\ny',
    error: '',
    metadata: {},
    pending: false,
  });

  test('collapses consecutive identical reads with a repeatCount badge', () => {
    const out = foldReadOnlyRepeats([
      step('a', 'file_read', 'App.tsx'),
      step('b', 'file_read', 'App.tsx'),
      step('c', 'file_read', 'App.tsx'),
    ]);
    expect(out).toHaveLength(1);
    expect((out[0] as { metadata: Record<string, unknown> }).metadata.repeatCount).toBe(3);
  });

  test('does not collapse different targets or failed runs or other tools', () => {
    const mixed = [
      step('a', 'file_read', 'A.ts'),
      step('b', 'file_read', 'B.ts'),
      step('c', 'file_read', 'A.ts', false),
      step('d', 'bash', 'A.ts'),
    ];
    expect(foldReadOnlyRepeats(mixed)).toHaveLength(4);
  });

  test('non-adjacent repeats stay separate', () => {
    const out = foldReadOnlyRepeats([
      step('a', 'file_read', 'A.ts'),
      step('b', 'grep', 'pat'),
      step('c', 'file_read', 'A.ts'),
    ]);
    expect(out).toHaveLength(3);
  });
});

describe('progressDuplicatesPendingToolStep', () => {
  const pendingBash: ScenarioEvent = {
    kind: 'tool_step',
    id: 'live1',
    tool: 'bash',
    params: { command: 'Get-ChildItem -Path . -Force -Recurse' },
    success: true,
    output: '',
    error: '',
    metadata: {},
    pending: true,
  };

  const progress = (label: string): ScenarioEvent => ({
    kind: 'progress',
    id: 'p',
    label,
    steps: [{ label, status: 'active' }],
  });

  test('suppresses a progress row echoing the in-flight command', () => {
    expect(
      progressDuplicatesPendingToolStep(
        progress('Running commands: Get-ChildItem -Path . -Force -Recurse | Select-O') as never,
        [pendingBash],
      ),
    ).toBe(true);
  });

  test('keeps phase-only rows like output summarization', () => {
    expect(
      progressDuplicatesPendingToolStep(progress('Running commands: summarizing 42 KB of output') as never, [
        pendingBash,
      ]),
    ).toBe(false);
  });

  test('keeps rows when nothing is pending', () => {
    expect(progressDuplicatesPendingToolStep(progress('Reading files: src/a.ts') as never, [])).toBe(false);
  });
});
