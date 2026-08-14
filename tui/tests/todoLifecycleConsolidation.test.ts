import os from 'node:os';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { collectTodoLifecycleEvents } from '../src/services/transport/todoLifecycleEmitter';
import type { ScenarioEvent, TodoTestEvent } from '../src/types/scenario';
import { upsertEvent } from '../src/utils/eventUpsert';
import { consolidateTodoTestEvents, reportPercent } from '../src/utils/todoLifecycle';

const outputDir = path.join(os.tmpdir(), `zenith-todo-consolidation-${process.pid}`);
const collect = () => collectTodoLifecycleEvents({ outputDir });

function applyAll(events: ScenarioEvent[]): ScenarioEvent[] {
  let state: ScenarioEvent[] = [];
  events.forEach((event, index) => {
    state = upsertEvent(state, event, index);
  });
  return state;
}

describe('consolidateTodoTestEvents', () => {
  it('returns null when there are no todo_test events', () => {
    expect(consolidateTodoTestEvents([])).toBeNull();
    expect(consolidateTodoTestEvents([{ kind: 'thinking', id: 't', thoughts: [], duration: 0 }])).toBeNull();
  });

  it('folds every scenario into one report with ALL assertions accumulated', () => {
    const raw = collect();
    const testEvents = raw.filter((e): e is TodoTestEvent => e.kind === 'todo_test');
    const consolidated = consolidateTodoTestEvents(applyAll(raw));
    expect(consolidated).not.toBeNull();

    const expectedAssertions = testEvents.reduce((sum, t) => sum + t.assertions.length, 0);
    expect(consolidated?.assertions).toHaveLength(expectedAssertions);
    expect(consolidated?.passedCount).toBe(consolidated?.totalCount);
    expect(consolidated?.phases).toHaveLength(7);
    expect(consolidated?.stepIndex).toBe(6);
  });

  it('accumulates rejectedOps across scenarios', () => {
    const raw = collect();
    const consolidated = consolidateTodoTestEvents(applyAll(raw));
    const expected = raw
      .filter((e): e is TodoTestEvent => e.kind === 'todo_test')
      .reduce((sum, t) => sum + (t.rejectedOps?.length ?? 0), 0);
    expect(consolidated?.rejectedOps).toHaveLength(expected);
  });

  it('reportPercent reflects the pass rate', () => {
    const raw = collect();
    const consolidated = consolidateTodoTestEvents(applyAll(raw));
    expect(reportPercent(consolidated!)).toBe(100);
  });

  it('handles a partial stream: latest phase wins', () => {
    const raw = collect();
    const slice = applyAll(raw.slice(0, 9));
    const consolidated = consolidateTodoTestEvents(slice);
    expect(consolidated).not.toBeNull();
    // The create phase has landed by index 8 (after thinking, plan, crew, tool read).
    expect(consolidated?.phase).toBe('create');
    expect(consolidated?.totalCount).toBeLessThanOrEqual(30);
  });
});
