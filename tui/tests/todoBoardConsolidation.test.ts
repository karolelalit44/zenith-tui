import { describe, expect, it } from 'vitest';
import { collectTodoBoardEvents } from '../src/services/transport/fixtureEmitter';
import type { ScenarioEvent, TodoBoardEvent } from '../src/types/scenario';
import { upsertEvent } from '../src/utils/eventUpsert';
import { consolidateTodoBoardEvents, MAX_ACTIVITY_ENTRIES } from '../src/utils/todoBoard';

function applyAll(events: ScenarioEvent[]): ScenarioEvent[] {
  let state: ScenarioEvent[] = [];
  events.forEach((event, index) => {
    state = upsertEvent(state, event, index);
  });
  return state;
}

describe('consolidateTodoBoardEvents', () => {
  it('returns null when there are no todo_board events', () => {
    expect(consolidateTodoBoardEvents([])).toBeNull();
    expect(consolidateTodoBoardEvents([{ kind: 'thinking', id: 't', thoughts: [], duration: 0 }])).toBeNull();
  });

  it('folds every emission into one card with the LATEST board snapshot', () => {
    const raw = collectTodoBoardEvents();
    const consolidated = consolidateTodoBoardEvents(applyAll(raw));
    expect(consolidated).not.toBeNull();

    const last = raw.filter((e): e is TodoBoardEvent => e.kind === 'todo_board').at(-1);
    expect(consolidated?.board).toEqual(last?.board);
    expect(consolidated?.action).toBe('completed');
  });

  it('keeps a bounded activity log with the lifecycle transitions', () => {
    const raw = collectTodoBoardEvents();
    const consolidated = consolidateTodoBoardEvents(applyAll(raw));
    const actions = consolidated?.activity.map((a) => a.action);
    expect(consolidated?.activity).toHaveLength(MAX_ACTIVITY_ENTRIES);
    // 11 emissions folded into a bounded log → oldest shifted out, newest kept.
    expect(actions?.[0]).toBe('updated');
    expect(actions?.includes('completed')).toBe(true);
    expect(actions?.at(-1)).toBe('completed');
  });

  it('carries the last change descriptor for UI highlighting', () => {
    const raw = collectTodoBoardEvents();
    const consolidated = consolidateTodoBoardEvents(applyAll(raw));
    expect(consolidated?.lastChange).toMatchObject({ itemId: 'T5', field: 'status', from: 'in_progress', to: 'done' });
    expect(consolidated?.lastMessage).toContain('Simulation complete');
  });

  it('bounds the activity log to MAX_ACTIVITY_ENTRIES, keeping the newest', () => {
    const many: ScenarioEvent[] = Array.from({ length: 20 }, (_, i) => ({
      kind: 'todo_board',
      id: `tb_${i}`,
      action: 'updated',
      board: [],
      message: `change ${i}`,
    }));
    const consolidated = consolidateTodoBoardEvents(many);
    expect(consolidated?.activity).toHaveLength(MAX_ACTIVITY_ENTRIES);
    expect(consolidated?.activity[0]?.message).toBe('change 14');
    expect(consolidated?.activity.at(-1)?.message).toBe('change 19');
  });
});
