import type { ScenarioEvent, TodoBoardChange, TodoBoardEvent, TodoItem, TodoStatus } from '../types/scenario';

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
  // Find index of the latest explicit todo_board event
  let lastBoardIdx = -1;
  for (let i = events.length - 1; i >= 0; i--) {
    if (events[i].kind === TODO_BOARD_KIND) {
      lastBoardIdx = i;
      break;
    }
  }

  // Check for in-flight tool_step or tool_call that executed after the latest todo_board
  for (let i = events.length - 1; i > lastBoardIdx; i--) {
    const ev = events[i];
    if (ev.kind === 'tool_step' && ev.tool === 'todo') {
      const boardData = ev.metadata?.board;
      if (Array.isArray(boardData) && boardData.length > 0) {
        return {
          kind: 'todo_board',
          id: ev.id,
          action: (ev.metadata?.action as any) || 'snapshot',
          board: boardData as TodoItem[],
          activity: [{ action: 'snapshot', message: ev.output || 'Tasks updated' }],
          message: ev.output,
        };
      }
    } else if (ev.kind === 'tool_call' && ev.tool === 'todo') {
      const rawTasks = ev.params?.tasks;
      if (Array.isArray(rawTasks) && rawTasks.length > 0) {
        const items: TodoItem[] = rawTasks.map((t: any, idx: number) => {
          const rawStatus = String(t.status || 'todo').toLowerCase();
          const status: TodoStatus =
            rawStatus === 'completed' || rawStatus === 'done'
              ? 'done'
              : rawStatus === 'in_progress' || rawStatus === 'in-progress'
              ? 'in_progress'
              : rawStatus === 'blocked'
              ? 'blocked'
              : rawStatus === 'cancelled' || rawStatus === 'canceled'
              ? 'cancelled'
              : 'todo';
          return {
            id: String(t.id || `t${idx + 1}`),
            title: String(t.title || ''),
            status,
            priority: (t.priority || 'medium') as any,
            createdAt: Date.now(),
            updatedAt: Date.now(),
            subtasks: [],
            notes: t.notes ? String(t.notes) : undefined,
            depends_on: Array.isArray(t.depends_on) ? t.depends_on.map(String) : undefined,
          };
        });
        return {
          kind: 'todo_board',
          id: ev.id,
          action: 'snapshot',
          board: items,
          activity: [{ action: 'snapshot', message: 'Tasks in progress...' }],
        };
      }
    }
  }

  if (lastBoardIdx === -1) {
    return null;
  }

  const present = events.filter((e): e is TodoBoardEvent => e.kind === TODO_BOARD_KIND);
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
