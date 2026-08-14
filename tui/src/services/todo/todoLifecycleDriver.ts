import path from 'node:path';
import type {
  ScenarioEvent,
  TodoBoardChange,
  TodoBoardEvent,
  TodoItem,
  TodoLifecyclePhase,
  TodoPriority,
  TodoStatus,
  TodoTestAssertion,
  TodoTestEvent,
  TodoTestRejectedOp,
} from '../../types/scenario';
import { type BoardPersistence, simOutputDir, TODO_LIFECYCLE_FILE, todoPersistence } from './todoPersistence';
import { type OpResult, TodoStore } from './todoStore';

export const LIFECYCLE_PHASES: TodoLifecyclePhase[] = [
  'create',
  'manage',
  'update',
  'progress',
  'complete',
  'reopen',
  'persist',
];

export const LIFECYCLE_PHASE_LABEL: Record<TodoLifecyclePhase, string> = {
  create: 'Create',
  manage: 'Manage',
  update: 'Update',
  progress: 'Progress',
  complete: 'Complete',
  reopen: 'Reopen',
  persist: 'Persist',
};

export interface LifecycleDriverOptions {
  /** Clock override for deterministic tests. */
  now?: () => number;
  /** Where the persist phase writes the board snapshot. */
  outputDir?: string;
  /** Injectable save/load port so tests can point at a temp directory. */
  persistence?: BoardPersistence;
}

export interface LifecycleRun {
  /** Ordered event stream (board snapshots interleaved with scenario results). */
  events: ScenarioEvent[];
  boardEvents: TodoBoardEvent[];
  testEvents: TodoTestEvent[];
  finalBoard: TodoItem[];
  passed: number;
  total: number;
  persistedPath: string;
  durationMs: number;
}

function deepEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

interface ScenarioCtx {
  assert: (passed: boolean, label: string, detail?: string) => void;
  expectRejected: (result: OpResult<unknown>, op: string) => void;
  done: () => void;
}

/**
 * Run the complete TODO/subtask lifecycle end to end: Create → Manage → Update
 * → Progress → Complete → Reopen → Persist.
 *
 * Every mutation flows through the real TodoStore validation, so invalid and
 * incomplete states are genuinely rejected — those rejections are captured as
 * assertions + rejected-op rows in the emitted test report. The Persist phase
 * writes the board to disk, constructs a FRESH store, reloads it, and asserts
 * deep equality: real refresh/reload verification.
 */
export function runTodoLifecycle(options: LifecycleDriverOptions = {}): LifecycleRun {
  const startedAt = Date.now();
  const store = new TodoStore([], { now: options.now });
  const events: ScenarioEvent[] = [];
  const boardEvents: TodoBoardEvent[] = [];
  const testEvents: TodoTestEvent[] = [];

  const pushBoard = (action: TodoBoardEvent['action'], message: string, change?: TodoBoardChange): void => {
    const evt: TodoBoardEvent = {
      kind: 'todo_board',
      id: `tb_${events.length}`,
      action,
      message,
      change,
      board: store.snapshot(),
    };
    boardEvents.push(evt);
    events.push(evt);
  };

  const scenario = (phase: TodoLifecyclePhase, scenarioName: string): ScenarioCtx => {
    const start = options.now ? options.now() : Date.now();
    const assertions: TodoTestAssertion[] = [];
    const rejectedOps: TodoTestRejectedOp[] = [];

    const assert = (passed: boolean, label: string, detail?: string): void => {
      assertions.push({ label, passed, detail });
    };

    const expectRejected = (result: OpResult<unknown>, op: string): void => {
      if (result.ok) {
        assert(false, `${op} should be rejected`, 'unexpectedly succeeded');
      } else {
        rejectedOps.push({ op, reason: result.error });
        assert(true, `${op} rejected`, result.error);
      }
    };

    return {
      assert,
      expectRejected,
      done: () => {
        const passed = assertions.every((a) => a.passed);
        const evt: TodoTestEvent = {
          kind: 'todo_test',
          id: `tt_${events.length}`,
          phase,
          scenario: scenarioName,
          passed,
          assertions,
          rejectedOps: rejectedOps.length > 0 ? rejectedOps : undefined,
          elapsedMs: (options.now ? options.now() : Date.now()) - start,
        };
        testEvents.push(evt);
        events.push(evt);
      },
    };
  };

  // ── 0 · seed the board ────────────────────────────────────────────────
  pushBoard('snapshot', 'Starting empty board — nothing tracked yet');

  // ── 1 · CREATE — a TODO with subtasks ─────────────────────────────────
  const create = scenario('create', 'Create a TODO with subtasks');
  const created = store.createTodo({
    id: 'T1',
    title: 'Build the HRMS employee onboarding module',
    priority: 'high',
    assignee: 'zenith',
    labels: ['backend', 'django', 'v1'],
    dueDate: '2026-08-20',
    subtasks: [
      { title: 'Design data model', assignee: 'captain' },
      { title: 'Scaffold Django app', assignee: 'dev-agent' },
    ],
  });
  create.assert(created.ok, 'createTodo accepts a valid TODO with subtasks');
  if (created.ok) {
    create.assert(created.value.id === 'T1', 'TODO id assigned (T1)');
    create.assert(created.value.subtasks.length === 2, 'TODO created with 2 subtasks');
    create.assert(created.value.status === 'todo', 'new TODO starts in todo status');
    create.assert(created.value.priority === 'high', 'priority persisted');
    create.assert(created.value.labels?.includes('django') === true, 'labels persisted');
  }
  create.expectRejected(store.createTodo({ title: '   ' }), 'createTodo(blank title)');
  create.expectRejected(store.createTodo({ title: 'x', subtasks: [{ title: '' }] }), 'createTodo(empty subtask title)');
  create.expectRejected(store.createTodo({ id: 'T1', title: 'Duplicate' }), 'createTodo(duplicate id)');
  create.done();
  pushBoard('created', 'Created task #T1 — Build the HRMS employee onboarding module', {
    itemId: 'T1',
    field: 'board',
    to: 'T1',
  });

  // ── 2 · MANAGE — multiple subtasks under the TODO ─────────────────────
  const manage = scenario('manage', 'Add multiple subtasks under the TODO');
  manage.assert(store.addSubtask('T1', { title: 'Implement models + admin' }).ok, 'addSubtask #3');
  manage.assert(store.addSubtask('T1', { title: 'Add REST serializers' }).ok, 'addSubtask #4');
  manage.assert(store.addSubtask('T1', { title: 'Write migration plan' }).ok, 'addSubtask #5');
  manage.assert(store.snapshot().find((i) => i.id === 'T1')?.subtasks.length === 5, 'board grows to 5 subtasks');
  manage.expectRejected(store.addSubtask('NOPE', { title: 'orphan' }), 'addSubtask(unknown parent)');
  manage.expectRejected(store.addSubtask('T1', { title: '' }), 'addSubtask(blank title)');
  manage.expectRejected(store.addSubtask('T1', { title: 'dup', id: 'T1-S1' }), 'addSubtask(duplicate id)');
  manage.done();
  pushBoard('updated', 'Added 3 subtasks to #T1 — 5 work items tracked', {
    itemId: 'T1',
    field: 'subtasks',
    from: 2,
    to: 5,
  });

  // ── 3 · UPDATE — TODO and subtask details ─────────────────────────────
  const update = scenario('update', 'Edit TODO + subtask details');
  update.assert(
    store.updateTodo('T1', {
      title: 'Build the HRMS employee onboarding module (Django)',
      priority: 'urgent',
      assignee: 'zenith',
      labels: ['backend', 'django', 'hrms', 'v1.0'],
    }).ok,
    'updateTodo title/priority/assignee/labels',
  );
  update.assert(
    store.updateSubtask('T1', 'T1-S1', {
      note: 'Relations: Employee → Department, Payroll, Leave',
      assignee: 'captain',
    }).ok,
    'updateSubtask note + assignee',
  );
  const updatedItem = store.snapshot().find((i) => i.id === 'T1');
  update.assert(updatedItem?.title.includes('Django') === true, 'title updated');
  update.assert(updatedItem?.priority === 'urgent', 'priority updated to urgent');
  update.assert((updatedItem?.subtasks[0]?.note ?? '').length > 0, 'subtask note persisted');
  update.expectRejected(store.updateTodo('NOPE', { title: 'x' }), 'updateTodo(unknown id)');
  update.expectRejected(
    store.updateTodo('T1', { priority: 'epic' as unknown as TodoPriority }),
    'updateTodo(invalid priority)',
  );
  update.expectRejected(store.updateTodo('T1', { title: '' }), 'updateTodo(blank title)');
  update.done();
  pushBoard('updated', 'Edited #T1 — title, priority → urgent, labels, subtask note', {
    itemId: 'T1',
    field: 'priority',
    from: 'high',
    to: 'urgent',
  });

  // ── 4 · PROGRESS — status + derived progress ──────────────────────────
  const progress = scenario('progress', 'Change status / progress');
  progress.assert(store.setStatus('T1', 'in_progress').ok, 'start TODO #T1');
  progress.assert(store.setStatus('T1-S1', 'in_progress').ok, 'start subtask T1-S1');
  progress.assert(store.setStatus('T1-S2', 'in_progress').ok, 'start subtask T1-S2');
  progress.assert(store.progressOfId('T1') === 0, 'derived progress 0% (0/5 done)');
  progress.expectRejected(store.setStatus('T1', 'done'), 'setStatus(todo → done) direct');
  progress.expectRejected(store.setStatus('T1-S9', 'done'), 'setStatus(unknown id)');
  progress.expectRejected(store.setStatus('T1', 'flying' as unknown as TodoStatus), 'setStatus(invalid status value)');
  progress.done();
  pushBoard('updated', 'Started #T1 + subtasks T1-S1, T1-S2 — tracking progress', {
    itemId: 'T1',
    field: 'status',
    from: 'todo',
    to: 'in_progress',
  });

  // ── 5 · COMPLETE — individual subtasks ────────────────────────────────
  const completeSubs = scenario('complete', 'Complete individual subtasks');
  completeSubs.assert(store.completeSubtask('T1', 'T1-S1').ok, 'complete T1-S1');
  completeSubs.assert(store.completeSubtask('T1', 'T1-S2').ok, 'complete T1-S2');
  completeSubs.assert(store.completeSubtask('T1', 'T1-S3').ok, 'complete T1-S3');
  completeSubs.assert(store.progressOfId('T1') === 60, 'progress advances to 60% (3/5)');
  completeSubs.expectRejected(store.completeSubtask('T1', 'T1-S1'), 'completeSubtask(already done)');
  completeSubs.done();
  pushBoard('updated', 'Completed 3/5 subtasks — progress 60%', {
    itemId: 'T1-S3',
    field: 'status',
    from: 'in_progress',
    to: 'done',
  });

  // ── 6 · COMPLETE — parent gated on required subtasks ──────────────────
  const completeParent = scenario('complete', 'Complete parent after all required subtasks');
  const earlyAttempt = store.completeTodo('T1');
  completeParent.assert(!earlyAttempt.ok, 'parent completion BLOCKED while required subtasks open');
  if (!earlyAttempt.ok) {
    completeParent.assert(
      earlyAttempt.error.includes('2 of 5'),
      'rejection cites the open subtask count',
      earlyAttempt.error,
    );
  }
  completeParent.assert(store.completeSubtask('T1', 'T1-S4').ok, 'complete T1-S4');
  completeParent.assert(store.completeSubtask('T1', 'T1-S5').ok, 'complete T1-S5');
  completeParent.assert(store.progressOfId('T1') === 100, 'progress reaches 100% (5/5)');
  completeParent.assert(store.completeTodo('T1').ok, 'parent completes once all required subtasks are done');
  completeParent.assert(store.snapshot().find((i) => i.id === 'T1')?.status === 'done', 'todo status is done');
  completeParent.expectRejected(store.completeTodo('NOPE'), 'completeTodo(unknown id)');
  completeParent.expectRejected(store.completeTodo('T1'), 'completeTodo(already done)');
  completeParent.done();
  pushBoard('updated', 'Completed all 5 subtasks → completed #T1', {
    itemId: 'T1',
    field: 'status',
    from: 'in_progress',
    to: 'done',
  });

  // ── 7 · REOPEN — completed TODO + subtask ─────────────────────────────
  const reopen = scenario('reopen', 'Reopen a completed TODO / subtask');
  reopen.assert(store.reopenSubtask('T1', 'T1-S5').ok, 'reopen subtask T1-S5');
  reopen.assert(store.reopenTodo('T1').ok, 'reopen TODO #T1');
  reopen.assert(store.progressOfId('T1') === 80, 'progress resets to 80% after reopen');
  reopen.expectRejected(store.reopenTodo('NOPE'), 'reopenTodo(unknown id)');
  reopen.expectRejected(store.reopenTodo('T1'), 'reopenTodo(active item)');
  reopen.assert(store.completeSubtask('T1', 'T1-S5').ok, 're-complete reopened subtask');
  reopen.assert(store.completeTodo('T1').ok, 're-complete reopened TODO');
  reopen.assert(store.snapshot().find((i) => i.id === 'T1')?.status === 'done', 'todo done again after reopen cycle');
  reopen.done();
  pushBoard('updated', 'Reopened #T1 + subtask T1-S5, then re-completed', {
    itemId: 'T1',
    field: 'status',
    from: 'done',
    to: 'in_progress',
  });

  // ── 8 · PERSIST — real file + fresh-store reload ──────────────────────
  const persist = scenario('persist', 'Persist board + verify after refresh/reload');
  const outputDir = options.outputDir ?? simOutputDir();
  const persistedPath = path.join(outputDir, TODO_LIFECYCLE_FILE);
  const persistence = options.persistence ?? todoPersistence;
  const board = store.snapshot();

  persistence.save(persistedPath, board);
  const fresh = new TodoStore(persistence.load(persistedPath), { now: options.now });
  persist.assert(fresh.itemsCount() === 1, 'reloaded board has exactly 1 todo');
  persist.assert(deepEqual(board, fresh.snapshot()), 'board deep-equal after fresh-store reload');
  persist.assert(persistedPath.endsWith(TODO_LIFECYCLE_FILE), 'persisted to todo-lifecycle.json');

  let missingFileError = '';
  try {
    persistence.load(path.join(outputDir, 'does-not-exist.json'));
    persist.assert(false, 'load(missing file) rejected', 'did not throw');
  } catch (err) {
    missingFileError = err instanceof Error ? err.message : String(err);
    persist.assert(true, 'load(missing file) rejected', missingFileError);
  }
  if (missingFileError) {
    persist.assert(true, 'rejection carries a reason', missingFileError);
  }
  persist.done();
  pushBoard('completed', `Persisted board to ${persistedPath} and reloaded — identical after refresh`, {
    itemId: 'T1',
    field: 'persistence',
    to: persistedPath,
  });

  // ── 9 · summary ───────────────────────────────────────────────────────
  const passed = testEvents.filter((t) => t.passed).length;
  const total = testEvents.length;
  events.push({
    kind: 'message',
    id: 'evt_lc_summary_msg',
    text:
      `✓ TODO lifecycle simulation complete — ${passed}/${total} scenarios passed across ` +
      `create → manage → update → progress → complete → reopen → persist. ` +
      `Board persisted to ${persistedPath} and verified identical after a fresh-store reload.`,
    partial: false,
  });
  events.push({
    kind: 'success',
    id: 'evt_lc_success',
    message: `TODO lifecycle simulation complete — ${passed}/${total} scenarios passed`,
    iterations: total,
    elapsedMs: Date.now() - startedAt,
    tokenInfo: {
      used: 0,
      remaining: 0,
      total: 0,
      percent: 0,
    },
  });

  return {
    events,
    boardEvents,
    testEvents,
    finalBoard: store.snapshot(),
    passed,
    total,
    persistedPath,
    durationMs: Date.now() - startedAt,
  };
}
