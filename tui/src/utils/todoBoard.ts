import { MAX_TODO_ACTIVITY_ENTRIES } from '../constants/todo';
import type { ScenarioEvent, TodoBoardChange, TodoBoardEvent, TodoItem, TodoStatus } from '../types/scenario';

const TODO_BOARD_KIND = 'todo_board';

export { MAX_TODO_ACTIVITY_ENTRIES };

export interface TodoBoardActivityEntry {
  action: TodoBoardEvent['action'];
  message: string;
  change?: TodoBoardChange;
}

export interface ConsolidatedTodoBoard extends TodoBoardEvent {
  activity: TodoBoardActivityEntry[];
  lastChange?: TodoBoardChange;
  lastMessage?: string;
  pending?: boolean;
}

function buildPendingBoard(
  ev: ScenarioEvent & { params?: Record<string, unknown> },
  rawTasks: unknown[],
): ConsolidatedTodoBoard {
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
      createdAt: 0,
      updatedAt: 0,
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
    activity: [{ action: 'snapshot', message: 'Awaiting tool result…' }],
    pending: true,
  };
}

/**
 * Fold every `todo_board` emission in one turn into a single stable board card.
 *
 * The live stream emits a full snapshot per transition, so the UI must not
 * render N rows — it renders ONE card carrying the LATEST snapshot's board
 * verbatim (`last.board`). Earlier snapshots contribute only the bounded
 * activity log of lifecycle transitions.
 *
 * This is deliberately latest-snapshot, not a union of every item ever seen.
 * A union would resurrect items a later `todo` write had already removed, and
 * would carry a previous turn's finished items into a new one. The card is
 * scoped to a single turn by its caller; do not feed it events from several
 * turns and expect per-turn isolation.
 *
 * Returns `null` when no `todo_board` events are present.
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

  // Check for in-flight tool_step or tool_call that executed after the latest
  // todo_board. A resolved tool_step carries the real board in metadata.board.
  // A pending tool_step or raw tool_call only carries the MODEL-REQUESTED
  // board; surface it as pending (unconfirmed) to avoid false-completeness.
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
      const rawTasks = (ev as any).params?.tasks;
      if ((ev as any).pending === true && Array.isArray(rawTasks) && rawTasks.length > 0) {
        return buildPendingBoard(ev, rawTasks);
      }
    } else if (ev.kind === 'tool_call' && ev.tool === 'todo') {
      const rawTasks = ev.params?.tasks;
      if (Array.isArray(rawTasks) && rawTasks.length > 0) {
        return buildPendingBoard(ev, rawTasks);
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
    if (activity.length >= MAX_TODO_ACTIVITY_ENTRIES) {
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
