import type { ScenarioEvent, TodoBoardChange, TodoBoardEvent, TodoItem } from '../types/scenario';

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
 * render N rows — it renders ONE card whose board is the union of every item
 * ever seen, each carrying its latest status. For a single simulation this
 * equals the latest snapshot; for a combined simulation (e.g. the showcase)
 * it keeps todos from every half visible in one window, ordered by the latest
 * snapshot then any earlier-only items. The card is also enriched with a
 * bounded activity log of the lifecycle transitions. Returns `null` when no
 * todo_board events are present.
 */
export function consolidateTodoBoardEvents(events: ScenarioEvent[]): ConsolidatedTodoBoard | null {
  const present = events.filter((e): e is TodoBoardEvent => e.kind === TODO_BOARD_KIND);
  if (present.length === 0) return null;

  const last = present[present.length - 1];
  const activity: TodoBoardActivityEntry[] = [];

  const byId = new Map<string, TodoItem>();
  const order: string[] = [];
  const seed = (item: TodoItem) => {
    if (!byId.has(item.id)) order.push(item.id);
    byId.set(item.id, item);
  };
  for (const item of last.board) seed(item);
  for (const evt of present) {
    for (const item of evt.board) seed(item);
  }
  const board = order.map((id) => byId.get(id)).filter((item): item is TodoItem => Boolean(item));

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
    board,
    change: last.change,
    message: last.message,
    activity,
    lastChange: last.change,
    lastMessage: last.message,
  };
}
