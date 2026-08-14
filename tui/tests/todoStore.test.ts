import { describe, expect, it } from 'vitest';
import { TodoStore } from '../src/services/todo/todoStore';

function freshStore() {
  return new TodoStore([], { now: () => 1000 });
}

describe('TodoStore · CRUD', () => {
  it('creates a todo with nested subtasks and assigned ids', () => {
    const store = freshStore();
    const r = store.createTodo({
      id: 'T1',
      title: 'Build the HRMS onboarding module',
      priority: 'high',
      assignee: 'zenith',
      labels: ['backend', 'django'],
      subtasks: [{ title: 'Design data model' }, { title: 'Scaffold app' }],
    });
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.value.id).toBe('T1');
      expect(r.value.status).toBe('todo');
      expect(r.value.priority).toBe('high');
      expect(r.value.subtasks.map((s) => s.id)).toEqual(['T1-S1', 'T1-S2']);
      expect(r.value.subtasks.every((s) => s.status === 'todo')).toBe(true);
    }
    expect(store.itemsCount()).toBe(1);
  });

  it('snapshot returns a deep copy that cannot mutate internal state', () => {
    const store = freshStore();
    store.createTodo({ id: 'T1', title: 'A', subtasks: [{ title: 'S1' }] });
    const snap = store.snapshot();
    snap[0].title = 'mutated';
    snap[0].subtasks[0].title = 'mutated sub';
    expect(store.snapshot()[0].title).toBe('A');
    expect(store.snapshot()[0].subtasks[0].title).toBe('S1');
  });

  it('addSubtask appends and bumps the parent updatedAt', () => {
    const store = new TodoStore([], { now: () => 500 });
    store.createTodo({ id: 'T1', title: 'A', subtasks: [{ title: 'S1' }] });
    const r = store.addSubtask('T1', { title: 'S2' });
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.value.id).toBe('T1-S2');
      expect(r.value.status).toBe('todo');
    }
    const item = store.snapshot()[0];
    expect(item.subtasks).toHaveLength(2);
    expect(item.updatedAt).toBe(500);
  });

  it('updateTodo updates title, priority, labels and assignee', () => {
    const store = freshStore();
    store.createTodo({ id: 'T1', title: 'A', priority: 'high', labels: ['a'] });
    const r = store.updateTodo('T1', { title: 'A (Django)', priority: 'urgent', labels: ['a', 'b', ' '] });
    expect(r.ok).toBe(true);
    const item = store.snapshot()[0];
    expect(item.title).toBe('A (Django)');
    expect(item.priority).toBe('urgent');
    expect(item.labels).toEqual(['a', 'b']);
  });

  it('updateSubtask patches note, assignee, title and status', () => {
    const store = freshStore();
    store.createTodo({ id: 'T1', title: 'A', subtasks: [{ title: 'S1' }] });
    const r = store.updateSubtask('T1', 'T1-S1', { note: 'note', assignee: 'captain', status: 'in_progress' });
    expect(r.ok).toBe(true);
    const sub = store.snapshot()[0].subtasks[0];
    expect(sub.note).toBe('note');
    expect(sub.assignee).toBe('captain');
    expect(sub.status).toBe('in_progress');
  });
});

describe('TodoStore · validation and edge cases', () => {
  it('rejects blank titles, duplicate ids, and unknown ids', () => {
    const store = freshStore();
    store.createTodo({ id: 'T1', title: 'A' });
    expect(store.createTodo({ title: '   ' }).ok).toBe(false);
    expect(store.createTodo({ title: 'x', subtasks: [{ title: '  ' }] }).ok).toBe(false);
    expect(store.createTodo({ id: 'T1', title: 'dup' }).ok).toBe(false);
    expect(store.updateTodo('NOPE', { title: 'x' }).ok).toBe(false);
    expect(store.addSubtask('NOPE', { title: 'x' }).ok).toBe(false);
    expect(store.completeTodo('NOPE').ok).toBe(false);
    expect(store.reopenTodo('NOPE').ok).toBe(false);
  });

  it('rejects invalid priority values and blank update titles', () => {
    const store = freshStore();
    store.createTodo({ id: 'T1', title: 'A' });
    expect(store.updateTodo('T1', { priority: 'epic' as never }).ok).toBe(false);
    expect(store.updateTodo('T1', { title: '' }).ok).toBe(false);
  });

  it('enforces the status transition table', () => {
    const store = freshStore();
    store.createTodo({ id: 'T1', title: 'A', subtasks: [{ title: 'S1' }] });
    // Direct todo → done is illegal
    expect(store.setStatus('T1', 'done').ok).toBe(false);
    expect(store.setStatus('T1', 'cancelled').ok).toBe(true);
    // cancelled → done is illegal; cancelled → todo is allowed
    expect(store.setStatus('T1', 'done').ok).toBe(false);
    expect(store.setStatus('T1', 'todo').ok).toBe(true);
    // invalid enum value rejected
    expect(store.setStatus('T1', 'flying' as never).ok).toBe(false);
  });

  it('blocks completing a parent while required subtasks are open', () => {
    const store = freshStore();
    store.createTodo({
      id: 'T1',
      title: 'A',
      subtasks: [{ title: 'S1' }, { title: 'S2' }, { title: 'S3' }],
    });
    const blocked = store.completeTodo('T1');
    expect(blocked.ok).toBe(false);
    if (!blocked.ok) expect(blocked.error).toContain('3 of 3');
    store.completeSubtask('T1', 'T1-S1');
    store.completeSubtask('T1', 'T1-S2');
    expect(store.completeTodo('T1').ok).toBe(false);
    store.completeSubtask('T1', 'T1-S3');
    expect(store.completeTodo('T1').ok).toBe(true);
    expect(store.snapshot()[0].status).toBe('done');
    // completing an already-done todo is rejected
    expect(store.completeTodo('T1').ok).toBe(false);
  });

  it('rejects duplicate/unknown subtask completions', () => {
    const store = freshStore();
    store.createTodo({ id: 'T1', title: 'A', subtasks: [{ title: 'S1' }] });
    expect(store.completeSubtask('T1', 'T1-S1').ok).toBe(true);
    expect(store.completeSubtask('T1', 'T1-S1').ok).toBe(false);
    expect(store.completeSubtask('T1', 'T1-S9').ok).toBe(false);
    expect(store.completeSubtask('NOPE', 'T1-S1').ok).toBe(false);
  });

  it('reopens completed items and rejects reopening active ones', () => {
    const store = freshStore();
    store.createTodo({
      id: 'T1',
      title: 'A',
      subtasks: [{ title: 'S1' }, { title: 'S2' }],
    });
    store.completeSubtask('T1', 'T1-S1');
    store.completeSubtask('T1', 'T1-S2');
    store.completeTodo('T1');
    expect(store.reopenTodo('T1').ok).toBe(true);
    expect(store.snapshot()[0].status).toBe('in_progress');
    // active item cannot be reopened
    expect(store.reopenTodo('T1').ok).toBe(false);
    // reopened subtask → re-complete cycle
    expect(store.reopenSubtask('T1', 'T1-S2').ok).toBe(true);
    expect(store.completeSubtask('T1', 'T1-S2').ok).toBe(true);
  });
});

describe('TodoStore · derived progress', () => {
  it('derives progress purely from status + subtasks', () => {
    const store = freshStore();
    store.createTodo({ id: 'T1', title: 'A', subtasks: [{ title: 'S1' }, { title: 'S2' }] });
    expect(store.progressOfId('T1')).toBe(0);
    store.completeSubtask('T1', 'T1-S1');
    expect(store.progressOfId('T1')).toBe(50);
    store.completeSubtask('T1', 'T1-S2');
    expect(store.progressOfId('T1')).toBe(100);
    store.reopenTodo('T1');
    expect(store.progressOfId('T1')).toBe(100);
    expect(store.progressOfId('NOPE')).toBeNull();
  });
});
