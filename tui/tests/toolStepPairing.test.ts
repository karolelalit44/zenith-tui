import { describe, expect, it } from 'vitest';
import { resolvePendingToolStep } from '../src/utils/eventUpsert';

function pending(tool: string, index: number) {
  return { index, tool, params: {} };
}

describe('resolvePendingToolStep', () => {
  it('pairs by exact id when tool_result shares the tool_call id', () => {
    const map = new Map([['call_1', pending('glob', 3)]]);
    const result = resolvePendingToolStep(map, 'call_1', 'glob');
    expect(result?.key).toBe('call_1');
    expect(result?.step.index).toBe(3);
    expect(map.size).toBe(0);
  });

  it('falls back to the earliest unresolved call of the same tool when ids differ', () => {
    const map = new Map([
      ['call_1', pending('glob', 3)],
      ['call_2', pending('file_write', 4)],
      ['call_3', pending('glob', 8)],
    ]);
    const result = resolvePendingToolStep(map, 'result_for_call_1', 'glob');
    expect(result?.key).toBe('call_1');
    expect(result?.step.index).toBe(3);
    expect(map.size).toBe(2);
  });

  it('resolves nested same-tool pairs in FIFO order', () => {
    const map = new Map([
      ['outer', pending('file_write', 2)],
      ['inner', pending('file_write', 5)],
    ]);
    const first = resolvePendingToolStep(map, 'inner_result', 'file_write');
    expect(first?.step.index).toBe(2);
    const second = resolvePendingToolStep(map, 'outer_result', 'file_write');
    expect(second?.step.index).toBe(5);
    expect(map.size).toBe(0);
  });

  it('returns null and leaves the map intact for a true orphan', () => {
    const map = new Map([['call_1', pending('bash', 1)]]);
    const result = resolvePendingToolStep(map, 'unknown_result', 'file_write');
    expect(result).toBeNull();
    expect(map.size).toBe(1);
  });

  it('returns null when there is no pending work at all', () => {
    const map = new Map();
    expect(resolvePendingToolStep(map, 'x', 'bash')).toBeNull();
  });
});
