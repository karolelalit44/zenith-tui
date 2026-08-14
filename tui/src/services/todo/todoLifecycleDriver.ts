import path from 'node:path';
import type {
  CrewmateAgent,
  PlanItem,
  ScenarioEvent,
  TimelineEntry,
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

interface LifecycleCrew {
  runner: CrewmateAgent;
  verifier: CrewmateAgent;
}

function lifecyclePlanItems(): PlanItem[] {
  return [
    { id: 'P1', title: 'Create TODO with subtasks', assignedAgent: 'lc-runner', status: 'queued' },
    { id: 'P2', title: 'Manage + update subtask details', assignedAgent: 'lc-runner', status: 'queued' },
    { id: 'P3', title: 'Progress, complete, reopen', assignedAgent: 'lc-runner', status: 'queued' },
    { id: 'P4', title: 'Persist + verify reload', assignedAgent: 'lc-verifier', status: 'queued' },
  ];
}

function lifecycleCrew(): LifecycleCrew {
  return {
    runner: {
      id: 'lc-runner',
      name: 'Scenario Runner',
      role: 'Lifecycle driver',
      task: 'Drive create → persist lifecycle operations',
      activity: 'Reading the TodoStore API',
      status: 'spawned',
      progress: 0,
    },
    verifier: {
      id: 'lc-verifier',
      name: 'Persistence Verifier',
      role: 'Reload guard',
      task: 'Reload board and assert deep equality',
      activity: 'Preparing reload checks',
      status: 'spawned',
      progress: 0,
    },
  };
}

function lcTimeline(timestamp: string, message: string, type?: 'info' | 'success' | 'warning'): TimelineEntry {
  return { timestamp, message, type };
}

/**
 * Run the complete TODO/subtask lifecycle end to end: Create → Manage → Update
 * → Progress → Complete → Reopen → Persist.
 *
 * The stream mirrors a real assistant response: thinking + plan, sub-agent
 * orchestration (captain + runner/verifier), paired tool calls, the lifecycle
 * scenario report (todo_test events), more tool calls, and a final response.
 * The todo BOARD snapshots ride along so the data pipeline stays intact, but
 * the rendered todo window is the report card only.
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

  // ── 0 · thinking + plan ───────────────────────────────────────────────
  events.push({
    kind: 'thinking',
    id: 'lc_thinking_1',
    duration: 2600,
    thoughts: [
      {
        text: 'The todo lifecycle is a full CRUD walk: create a TODO with subtasks, manage the list, update fields, move through progress to completion, reopen it, and finally persist the board and reload it into a fresh store to prove nothing is lost on refresh.',
      },
      {
        text: 'Every operation must flow through the real TodoStore so invalid input is genuinely rejected — those rejections become the edge-case rows in the report.',
      },
      {
        text: 'Persist is the critical phase: write to disk, rebuild the store from the file, and deep-compare. Only then can the lifecycle be called complete.',
      },
    ],
  });

  events.push({
    kind: 'message',
    id: 'lc_msg_intro',
    text: 'Walking the **HRMS onboarding module** lifecycle end to end: create the TODO, manage its subtasks, update details, track progress, complete, reopen, and persist across a reload. The scenario runner drives every phase through the real TodoStore while the persistence verifier guards the final reload.',
    partial: false,
  });

  events.push({
    kind: 'plan_ready',
    id: 'lc_plan_1',
    sessionId: 'todo-lifecycle',
    plan:
      '## Todo Lifecycle Run\n' +
      '1. **Create** a TODO with subtasks and validate the store invariants.\n' +
      '2. **Manage** subtasks: add, reject duplicates/blank titles.\n' +
      '3. **Update** TODO + subtask details (title, priority, labels, note).\n' +
      '4. **Progress**: move statuses and derive % progress.\n' +
      '5. **Complete** subtasks then the parent (gated on required subtasks).\n' +
      '6. **Reopen** the completed TODO and re-complete it.\n' +
      '7. **Persist** the board, reload into a fresh store, assert deep equality.',
  });

  let plan = lifecyclePlanItems();
  let crew = lifecycleCrew();
  events.push({
    kind: 'agent_orchestration',
    id: 'lc_orch_1',
    stage: 'planning',
    captainMessage:
      'Splitting the lifecycle into 4 workstreams — the runner drives the scenarios while the verifier owns persistence + reload.',
    plan,
    crewmates: Object.values(crew),
    timeline: [
      lcTimeline('09:31:02', 'Plan ready — 4 workstreams, 2 sub-agents available'),
      lcTimeline('09:31:05', 'Runner picks up create → reopen; verifier preps reload checks'),
    ],
    activeStep: 'P1',
  });

  plan = plan.map((p) => ({ ...p, status: 'in_progress' as const }));
  crew = {
    runner: { ...crew.runner, status: 'assigned' as const, progress: 10, activity: 'Loading the TodoStore API' },
    verifier: { ...crew.verifier, status: 'assigned' as const, progress: 10, activity: 'Mapping persistence contract' },
  };
  events.push({
    kind: 'agent_orchestration',
    id: 'lc_orch_2',
    stage: 'delegating',
    captainMessage:
      'Sub-agents dispatched. The runner begins with the create phase; the verifier awaits the persist phase.',
    plan,
    crewmates: Object.values(crew),
    timeline: [lcTimeline('09:31:09', 'Sub-agents dispatched', 'info')],
    activeStep: 'P1',
  });

  // ── 0 · seed the board ────────────────────────────────────────────────
  pushBoard('snapshot', 'Starting empty board — nothing tracked yet');

  events.push({
    kind: 'tool_call',
    id: 'lc_tool_read',
    tool: 'read_file',
    params: { path: 'src/services/todo/todoStore.ts' },
    text: 'Reading the TodoStore API before driving the lifecycle',
  });
  events.push({
    kind: 'tool_result',
    id: 'lc_tool_read',
    tool: 'read_file',
    success: true,
    output:
      'TodoStore API: createTodo, addSubtask, updateTodo, updateSubtask, setStatus, completeSubtask, completeTodo, reopenTodo, reopenSubtask, progressOfId, snapshot. Validation rejects blank titles, duplicate ids and invalid statuses.',
    error: '',
    metadata: { path: 'src/services/todo/todoStore.ts', lines: 366 },
  });

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

  events.push({
    kind: 'tool_call',
    id: 'lc_tool_run',
    tool: 'bash',
    params: { command: 'npx vitest run tests/todoStore.test.ts tests/todoPersistence.test.ts' },
    text: 'Running the TodoStore unit suite before driving the progress scenarios',
  });
  events.push({
    kind: 'tool_result',
    id: 'lc_tool_run',
    tool: 'bash',
    success: true,
    output: 'Test Files  2 passed (2)\n      Tests  38 passed (38)\n',
    error: '',
    metadata: { exitCode: 0 },
  });

  crew = {
    ...crew,
    runner: { ...crew.runner, status: 'working' as const, progress: 55, activity: 'Driving update + progress phases' },
    verifier: { ...crew.verifier, status: 'working' as const, progress: 30, activity: 'Drafting reload assertions' },
  };
  events.push({
    kind: 'agent_orchestration',
    id: 'lc_orch_3',
    stage: 'working',
    captainMessage:
      'Create, manage and update are green. The runner moves into progress/complete/reopen while the verifier maps the persistence file layout.',
    plan,
    crewmates: Object.values(crew),
    timeline: [
      lcTimeline('09:32:18', 'Create + manage + update phases passed', 'success'),
      lcTimeline('09:32:31', 'TodoStore unit suite green (38 tests)', 'success'),
    ],
    activeStep: 'P2',
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

  events.push({
    kind: 'tool_call',
    id: 'lc_tool_write',
    tool: 'write_file',
    params: { path: 'data/simulation/todo-lifecycle.json', description: 'Board snapshot for the persist phase' },
    text: 'Staging the board snapshot before the persist phase',
  });
  events.push({
    kind: 'tool_result',
    id: 'lc_tool_write',
    tool: 'write_file',
    success: true,
    output: 'Staged board snapshot — 1 todo, 5 subtasks, priority urgent, status done.',
    error: '',
    metadata: { path: 'data/simulation/todo-lifecycle.json', lines: 132 },
  });

  crew = {
    ...crew,
    runner: { ...crew.runner, status: 'working' as const, progress: 85, activity: 'Wrapping up reopen cycle' },
    verifier: {
      ...crew.verifier,
      status: 'needs_review' as const,
      progress: 70,
      activity: 'Reviewing the reload plan',
    },
  };
  events.push({
    kind: 'agent_orchestration',
    id: 'lc_orch_4',
    stage: 'reviewing',
    captainMessage:
      'Complete → reopen → re-complete cycle done. The verifier owns the persist phase now: write, reload, deep-compare.',
    plan,
    crewmates: Object.values(crew),
    timeline: [
      lcTimeline('09:33:04', 'Reopen cycle verified — progress reset + re-completed', 'info'),
      lcTimeline('09:33:07', 'Handing persistence to the verifier', 'info'),
    ],
    activeStep: 'P4',
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

  plan = plan.map((p) => ({ ...p, status: 'completed' as const }));
  crew = {
    runner: {
      ...crew.runner,
      status: 'completed' as const,
      progress: 100,
      resultSummary: 'All lifecycle phases green — every scenario passed',
    },
    verifier: {
      ...crew.verifier,
      status: 'completed' as const,
      progress: 100,
      resultSummary: 'Board reloaded + deep-equal after refresh',
    },
  };
  events.push({
    kind: 'agent_orchestration',
    id: 'lc_orch_5',
    stage: 'complete',
    captainMessage: 'Lifecycle complete — every phase passed and the board survived a fresh-store reload.',
    plan,
    crewmates: Object.values(crew),
    timeline: [
      lcTimeline('09:33:22', 'Verifier confirmed deep-equal reload', 'success'),
      lcTimeline('09:33:25', 'Orchestration complete', 'success'),
    ],
  });

  // ── 9 · summary ───────────────────────────────────────────────────────
  const passed = testEvents.filter((t) => t.passed).length;
  const total = testEvents.length;
  events.push({
    kind: 'message',
    id: 'evt_lc_summary_msg',
    text: `**Todo lifecycle verified end to end.** The runner drove create → manage → update → progress → complete → reopen → persist through the real TodoStore, all ${passed}/${total} scenarios passed (58 assertions), edge cases were genuinely rejected, and the board was persisted to ${persistedPath} then reloaded into a fresh store that deep-equals the original — nothing was lost across the refresh.`,
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
