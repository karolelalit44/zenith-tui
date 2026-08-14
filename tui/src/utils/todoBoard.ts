import type { ScenarioEvent, TodoBoardChange, TodoBoardEvent } from '../types/scenario';

const TODO_BOARD_KIND = 'todo_board';

export const MAX_ACTIVITY_ENTRIES = 6;

export interface TodoBoardActivityEntry {
  action: TodoBoardEvent['action'];
  message: string;
  change?: TodoBoardChange;
}

export interface ConsolidatedTodoBoard extends TodoBoardEvent {
  activity: TodoBoardActivityEntry[];
  lastChange?: TodoBoardChange;
  lastMessage?: string;
}

/**
 * Fold every `todo_board` emission into a single stable board card.
 *
 * The live stream emits a full snapshot per transition, so the UI must not
 * render N rows — it renders ONE card whose contents are the latest snapshot,
 * enriched with a bounded activity log of the lifecycle transitions that led
 * there. Returns `null` when no todo_board events are present.
 */
export function consolidateTodoBoardEvents(events: ScenarioEvent[]): ConsolidatedTodoBoard | null {
  const present = events.filter((e): e is TodoBoardEvent => e.kind === TODO_BOARD_KIND);
  if (present.length === 0) return null;

  const last = present[present.length - 1];
  const activity: TodoBoardActivityEntry[] = [];

  for (const evt of present) {
    const message = evt.message ?? '';
    if (activity.length >= MAX_ACTIVITY_ENTRIES) {
      activity.shift();
    }
    activity.push({ action: evt.action, message, change: evt.change });
  }

  return {
    kind: 'todo_board',
    id: last.id,
    action: last.action,
    board: last.board,
    change: last.change,
    message: last.message,
    activity,
    lastChange: last.change,
    lastMessage: last.message,
  };
}
