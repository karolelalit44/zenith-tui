import type { SubtaskItem, TodoItem, TodoPriority, TodoStatus } from '../../types/scenario';

/**
 * Result type used by every TodoStore mutation. Callers never throw for
 * domain errors — invalid operations return `{ ok: false, error }` so the
 * lifecycle driver can assert that invalid/incomplete states are REJECTED.
 */
export type OpResult<T> = { ok: true; value: T } | { ok: false; error: string };

export const TODO_STATUSES: TodoStatus[] = ['todo', 'in_progress', 'blocked', 'done', 'cancelled'];

export const TODO_PRIORITIES: TodoPriority[] = ['low', 'medium', 'high', 'urgent'];

/**
 * Allowed status transitions. `done`/`cancelled` are only reachable via the
 * gated complete/reopen operations or their explicit transition below.
 */
const ALLOWED_TRANSITIONS: Record<TodoStatus, TodoStatus[]> = {
  todo: ['in_progress', 'blocked', 'cancelled'],
  in_progress: ['todo', 'blocked', 'done', 'cancelled'],
  blocked: ['todo', 'in_progress', 'cancelled'],
  done: ['in_progress', 'todo'],
  cancelled: ['todo', 'in_progress'],
};

export interface CreateSubtaskInput {
  title: string;
  id?: string;
  assignee?: string;
  note?: string;
}

export interface CreateTodoInput {
  id?: string;
  title: string;
  priority?: TodoPriority;
  assignee?: string;
  labels?: string[];
  dueDate?: string;
  subtasks?: CreateSubtaskInput[];
}

export interface TodoPatch {
  title?: string;
  priority?: TodoPriority;
  assignee?: string;
  labels?: string[];
  dueDate?: string;
}

export interface SubtaskPatch {
  title?: string;
  status?: TodoStatus;
  assignee?: string;
  note?: string;
}

export interface TodoStoreOptions {
  /** Clock override for deterministic tests. */
  now?: () => number;
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function isNonEmptyTitle(value: string): boolean {
  return typeof value === 'string' && value.trim().length > 0;
}

/**
 * Pure, in-memory todo board with real CRUD semantics and validation.
 *
 * This is the engine behind the todo lifecycle simulation: every operation
 * either applies cleanly (`ok: true`) or is rejected with a human reason
 * (`ok: false`), which is exactly what lets the simulation prove that edge
 * cases and invalid/incomplete states are handled correctly.
 */
export class TodoStore {
  private items: TodoItem[];
  private nowFn: () => number;

  constructor(initial?: TodoItem[], options?: TodoStoreOptions) {
    this.items = clone(initial ?? []);
    this.nowFn = options?.now ?? Date.now;
  }

  /** Deep copy of the board — safe to emit over the wire / render. */
  snapshot(): TodoItem[] {
    return clone(this.items);
  }

  private findItem(id: string): { item: TodoItem; parent: null } | { item: SubtaskItem; parent: TodoItem } | null {
    for (const parent of this.items) {
      if (parent.id === id) return { item: parent, parent: null };
      for (const sub of parent.subtasks) {
        if (sub.id === id) return { item: sub, parent };
      }
    }
    return null;
  }

  private touch<T extends object>(entity: T): T & { updatedAt: number } {
    return { ...entity, updatedAt: this.nowFn() };
  }

  /** Replace the parent's subtask array and bump its updatedAt. */
  private applySubtasks(parent: TodoItem, subtasks: SubtaskItem[]): TodoItem {
    const updated: TodoItem = {
      ...parent,
      updatedAt: this.nowFn(),
      subtasks,
    };
    const index = this.items.findIndex((i) => i.id === parent.id);
    if (index >= 0) this.items[index] = updated;
    return updated;
  }

  private bumpTodo(item: TodoItem): TodoItem {
    const index = this.items.findIndex((i) => i.id === item.id);
    if (index >= 0) this.items[index] = item;
    return item;
  }

  static validateTransition(from: TodoStatus, to: TodoStatus): string | null {
    if (!TODO_STATUSES.includes(to)) return `invalid status "${to}"`;
    if (from === to) return `already ${from}`;
    if (!ALLOWED_TRANSITIONS[from].includes(to)) return `illegal transition ${from} → ${to}`;
    return null;
  }

  /** Require all subtasks to be done before the parent can be completed. */
  static incompleteSubtasks(item: TodoItem | SubtaskItem): SubtaskItem[] {
    const subtasks = 'subtasks' in item ? item.subtasks : [];
    return subtasks.filter((s) => s.status !== 'done');
  }

  static progressOf(item: TodoItem | SubtaskItem): number {
    if (item.status === 'done') return 100;
    if (item.status === 'cancelled') return 0;
    const subtasks = 'subtasks' in item ? item.subtasks : [];
    if (subtasks.length === 0) {
      if (item.status === 'in_progress') return 40;
      if (item.status === 'blocked') return 15;
      return 0;
    }
    const done = subtasks.filter((s) => s.status === 'done').length;
    return Math.round((done / subtasks.length) * 100);
  }

  /** Derived, never-trusted-from-wire progress for any item id. */
  progressOfId(id: string): number | null {
    const found = this.findItem(id);
    return found ? TodoStore.progressOf(found.item) : null;
  }

  createTodo(input: CreateTodoInput): OpResult<TodoItem> {
    if (!isNonEmptyTitle(input.title)) {
      return { ok: false, error: 'createTodo rejected: title must be a non-empty string' };
    }
    const id = input.id ?? `T${this.items.length + 1}`;
    if (this.findItem(id)) {
      return { ok: false, error: `createTodo rejected: id "${id}" already exists` };
    }
    const now = this.nowFn();
    const subtasks: SubtaskItem[] = (input.subtasks ?? []).map((s, index) => {
      const sid = s.id ?? `${id}-S${index + 1}`;
      return {
        id: sid,
        title: s.title,
        status: 'todo',
        assignee: s.assignee,
        note: s.note,
      };
    });
    for (const s of subtasks) {
      if (!isNonEmptyTitle(s.title)) {
        return { ok: false, error: 'createTodo rejected: every subtask needs a non-empty title' };
      }
      if (this.findItem(s.id)) {
        return { ok: false, error: `createTodo rejected: subtask id "${s.id}" already exists` };
      }
    }
    const item: TodoItem = {
      id,
      title: input.title.trim(),
      status: 'todo',
      priority: input.priority ?? 'medium',
      assignee: input.assignee,
      labels: input.labels?.map((l) => l.trim()).filter(Boolean),
      dueDate: input.dueDate,
      createdAt: now,
      updatedAt: now,
      subtasks,
    };
    this.items.push(item);
    return { ok: true, value: clone(item) };
  }

  addSubtask(parentId: string, input: CreateSubtaskInput): OpResult<SubtaskItem> {
    const parent = this.items.find((i) => i.id === parentId);
    if (!parent) return { ok: false, error: `addSubtask rejected: parent "${parentId}" not found` };
    if (!isNonEmptyTitle(input.title)) {
      return { ok: false, error: 'addSubtask rejected: title must be a non-empty string' };
    }
    const id = input.id ?? `${parentId}-S${parent.subtasks.length + 1}`;
    if (this.findItem(id)) return { ok: false, error: `addSubtask rejected: id "${id}" already exists` };
    const subtask: SubtaskItem = {
      id,
      title: input.title.trim(),
      status: 'todo',
      assignee: input.assignee,
      note: input.note,
    };
    this.applySubtasks(parent, [...parent.subtasks, subtask]);
    return { ok: true, value: clone(subtask) };
  }

  updateTodo(id: string, patch: TodoPatch): OpResult<TodoItem> {
    const found = this.findItem(id);
    if (!found || found.parent) return { ok: false, error: `updateTodo rejected: "${id}" not found` };
    if (patch.title !== undefined && !isNonEmptyTitle(patch.title)) {
      return { ok: false, error: 'updateTodo rejected: title must be a non-empty string' };
    }
    if (patch.priority !== undefined && !TODO_PRIORITIES.includes(patch.priority)) {
      return { ok: false, error: `updateTodo rejected: invalid priority "${patch.priority}"` };
    }
    if (patch.labels !== undefined && !patch.labels.every((l) => typeof l === 'string')) {
      return { ok: false, error: 'updateTodo rejected: labels must be strings' };
    }
    const updated: TodoItem = {
      ...found.item,
      ...(patch.title !== undefined ? { title: patch.title.trim() } : {}),
      ...(patch.priority !== undefined ? { priority: patch.priority } : {}),
      ...(patch.assignee !== undefined ? { assignee: patch.assignee } : {}),
      ...(patch.labels !== undefined ? { labels: patch.labels.map((l) => l.trim()).filter(Boolean) } : {}),
      ...(patch.dueDate !== undefined ? { dueDate: patch.dueDate } : {}),
      updatedAt: this.nowFn(),
    };
    this.bumpTodo(updated);
    return { ok: true, value: clone(updated) };
  }

  updateSubtask(parentId: string, subtaskId: string, patch: SubtaskPatch): OpResult<SubtaskItem> {
    const parent = this.items.find((i) => i.id === parentId);
    if (!parent) return { ok: false, error: `updateSubtask rejected: parent "${parentId}" not found` };
    const subtask = parent.subtasks.find((s) => s.id === subtaskId);
    if (!subtask) return { ok: false, error: `updateSubtask rejected: "${subtaskId}" not found` };
    if (patch.title !== undefined && !isNonEmptyTitle(patch.title)) {
      return { ok: false, error: 'updateSubtask rejected: title must be a non-empty string' };
    }
    if (patch.status !== undefined) {
      const invalid = TodoStore.validateTransition(subtask.status, patch.status);
      if (invalid) return { ok: false, error: `updateSubtask rejected: ${invalid}` };
    }
    const updated: SubtaskItem = {
      ...subtask,
      ...(patch.title !== undefined ? { title: patch.title.trim() } : {}),
      ...(patch.assignee !== undefined ? { assignee: patch.assignee } : {}),
      ...(patch.note !== undefined ? { note: patch.note } : {}),
      status: patch.status ?? subtask.status,
    };
    this.applySubtasks(
      parent,
      parent.subtasks.map((s) => (s.id === updated.id ? updated : s)),
    );
    return { ok: true, value: clone(updated) };
  }

  /** Status change with full transition + completeness validation. */
  setStatus(id: string, status: TodoStatus): OpResult<TodoItem | SubtaskItem> {
    const found = this.findItem(id);
    if (!found) return { ok: false, error: `setStatus rejected: "${id}" not found` };
    const invalid = TodoStore.validateTransition(found.item.status, status);
    if (invalid) return { ok: false, error: `setStatus rejected: ${invalid}` };
    if (status === 'done' && !found.parent) {
      const open = TodoStore.incompleteSubtasks(found.item);
      if (open.length > 0) {
        return {
          ok: false,
          error: `setStatus rejected: cannot complete "${id}" — ${open.length} of ${found.item.subtasks.length} subtasks still open`,
        };
      }
    }
    const updated = this.touch({ ...found.item, status });
    if (found.parent) {
      this.applySubtasks(
        found.parent,
        found.parent.subtasks.map((s) => (s.id === (updated as SubtaskItem).id ? (updated as SubtaskItem) : s)),
      );
    } else {
      this.bumpTodo(updated as TodoItem);
    }
    return { ok: true, value: clone(updated) };
  }

  completeTodo(id: string): OpResult<TodoItem> {
    const found = this.findItem(id);
    if (!found || found.parent) return { ok: false, error: `completeTodo rejected: todo "${id}" not found` };
    if (found.item.status === 'done') return { ok: false, error: `completeTodo rejected: "${id}" already done` };
    const open = TodoStore.incompleteSubtasks(found.item);
    if (open.length > 0) {
      return {
        ok: false,
        error: `completeTodo rejected: cannot complete "${id}" — ${open.length} of ${found.item.subtasks.length} required subtasks still open`,
      };
    }
    const updated: TodoItem = this.touch({ ...found.item, status: 'done' });
    this.bumpTodo(updated);
    return { ok: true, value: clone(updated) };
  }

  completeSubtask(parentId: string, subtaskId: string): OpResult<SubtaskItem> {
    const parent = this.items.find((i) => i.id === parentId);
    if (!parent) return { ok: false, error: `completeSubtask rejected: parent "${parentId}" not found` };
    const subtask = parent.subtasks.find((s) => s.id === subtaskId);
    if (!subtask) return { ok: false, error: `completeSubtask rejected: "${subtaskId}" not found` };
    if (subtask.status === 'done') {
      return { ok: false, error: `completeSubtask rejected: "${subtaskId}" is already done` };
    }
    const updated: SubtaskItem = this.touch({ ...subtask, status: 'done' });
    this.applySubtasks(
      parent,
      parent.subtasks.map((s) => (s.id === updated.id ? updated : s)),
    );
    return { ok: true, value: clone(updated) };
  }

  /** Reopen a completed/cancelled item back into active work. */
  reopenTodo(id: string): OpResult<TodoItem> {
    const found = this.findItem(id);
    if (!found || found.parent) return { ok: false, error: `reopenTodo rejected: todo "${id}" not found` };
    if (found.item.status !== 'done' && found.item.status !== 'cancelled') {
      return { ok: false, error: `reopenTodo rejected: "${id}" is ${found.item.status}, not completed` };
    }
    const updated: TodoItem = this.touch({
      ...found.item,
      status: found.item.status === 'done' ? 'in_progress' : 'todo',
    });
    this.bumpTodo(updated);
    return { ok: true, value: clone(updated) };
  }

  reopenSubtask(parentId: string, subtaskId: string): OpResult<SubtaskItem> {
    const parent = this.items.find((i) => i.id === parentId);
    if (!parent) return { ok: false, error: `reopenSubtask rejected: parent "${parentId}" not found` };
    const subtask = parent.subtasks.find((s) => s.id === subtaskId);
    if (!subtask) return { ok: false, error: `reopenSubtask rejected: "${subtaskId}" not found` };
    if (subtask.status !== 'done' && subtask.status !== 'cancelled') {
      return { ok: false, error: `reopenSubtask rejected: "${subtaskId}" is ${subtask.status}, not completed` };
    }
    const updated: SubtaskItem = this.touch({
      ...subtask,
      status: subtask.status === 'done' ? 'in_progress' : 'todo',
    });
    this.applySubtasks(
      parent,
      parent.subtasks.map((s) => (s.id === updated.id ? updated : s)),
    );
    return { ok: true, value: clone(updated) };
  }

  itemsCount(): number {
    return this.items.length;
  }
}
