import type {
  CrewmateAgent,
  PlanItem,
  ScenarioEvent,
  TimelineEntry,
  TodoBoardChange,
  TodoItem,
} from '../../types/scenario';
import { TodoStore } from '../todo/todoStore';

/**
 * Long, end-to-end BUILD-mode simulation: "Design a Django HRMS app".
 *
 * This driver exists to prove the frontend is capable of a full production
 * build session with sub-agents (captain + crewmates), a tracked todo board,
 * tool steps (including one that fails and recovers), warnings, a mid-turn
 * context compaction, a turn manifest, plan readiness, and a final success.
 * Every event uses an EXISTING ScenarioEvent kind — nothing new to render.
 *
 * Contract details that matter for the UI:
 * - `tool_call` / `tool_result` share the SAME id + tool so `useScenario`
 *   pairs them into a single `tool_step` card.
 * - `agent_orchestration` crewmate ids stay STABLE across emissions so the
 *   renderer's consolidation merges their statuses instead of stacking cards.
 * - The mid-turn `error` is `recoverable: false` so no retry banner appears.
 * - Todo board snapshots come from the real TodoStore engine.
 */

export const HRMS_PROMPT =
  'Design and build a Django HRMS application end to end: employee records, departments, ' +
  'payroll, leave management, REST API with token auth, admin interface, seed data, and a ' +
  'full test suite. Use sub-agents for parallel workstreams, track everything on the todo ' +
  'board, handle failures gracefully, and keep the build in context with compaction when needed.';

export interface HrmsBuildRun {
  prompt: string;
  events: ScenarioEvent[];
  boardEvents: number;
  finalBoard: TodoItem[];
}

interface CrewList {
  devBackend: CrewmateAgent;
  devModels: CrewmateAgent;
  qa: CrewmateAgent;
  docs: CrewmateAgent;
}

function planItems(): PlanItem[] {
  return [
    { id: 'P1', title: 'Scaffold Django project + HRMS apps', assignedAgent: 'dev-backend', status: 'queued' },
    { id: 'P2', title: 'Employee + Department models', assignedAgent: 'dev-models', status: 'queued' },
    { id: 'P3', title: 'Payroll + Leave domain models', assignedAgent: 'dev-models', status: 'queued' },
    { id: 'P4', title: 'REST API + token auth', assignedAgent: 'dev-backend', status: 'queued' },
    { id: 'P5', title: 'Admin + seed data', assignedAgent: 'qa', status: 'queued' },
    { id: 'P6', title: 'Test suite + CI pipeline', assignedAgent: 'qa', status: 'queued' },
  ];
}

function crewmates(): CrewList {
  return {
    devBackend: {
      id: 'dev-backend',
      name: 'Backend Agent',
      role: 'Backend Engineer',
      task: 'Scaffold project + REST API + auth',
      activity: 'Writing serializers and viewsets',
      status: 'spawned',
      progress: 0,
    },
    devModels: {
      id: 'dev-models',
      name: 'Model Architect',
      role: 'Data Modeler',
      task: 'Employee, Payroll + Leave models',
      activity: 'Designing relational schema',
      status: 'spawned',
      progress: 0,
    },
    qa: {
      id: 'qa',
      name: 'QA Sentinel',
      role: 'QA Engineer',
      task: 'Admin + seed data + test suite',
      activity: 'Planning test matrix',
      status: 'spawned',
      progress: 0,
    },
    docs: {
      id: 'docs',
      name: 'Doc Scout',
      role: 'Documentation',
      task: 'HRMS usage + API docs',
      activity: 'Outlining README sections',
      status: 'spawned',
      progress: 0,
    },
  };
}

function patchCrew(crew: CrewList, patch: Partial<Record<keyof CrewList, Partial<CrewmateAgent>>>): CrewList {
  const next = { ...crew };
  for (const key of Object.keys(patch) as (keyof CrewList)[]) {
    const p = patch[key];
    if (p) next[key] = { ...next[key], ...p };
  }
  return next;
}

function timeline(timestamp: string, message: string, type?: TimelineType): TimelineEntry {
  return { timestamp, message, type };
}

type TimelineType = 'info' | 'success' | 'warning' | 'error' | 'reassign';

function boardChange(itemId: string, field: string, from: unknown, to: unknown): TodoBoardChange {
  return { itemId, field, from, to };
}

export function runHrmsBuildSimulation(): HrmsBuildRun {
  const events: ScenarioEvent[] = [];
  const push = (event: ScenarioEvent) => events.push(event);

  const store = new TodoStore([]);
  const boardSnapshot = (
    action: 'created' | 'updated' | 'completed' | 'cancelled' | 'snapshot',
    message: string,
    change?: TodoBoardChange,
  ) => {
    push({
      kind: 'todo_board',
      id: `hrms_board_${events.length}`,
      action,
      message,
      change,
      board: store.snapshot(),
    });
  };
  const createTodo = (
    id: string,
    title: string,
    priority: 'low' | 'medium' | 'high' | 'urgent',
    assignee: string,
    labels: string[],
    subtasks: { title: string }[],
  ): void => {
    const result = store.createTodo({ id, title, priority, assignee, labels, subtasks });
    if (result.ok) {
      boardSnapshot('created', `Created task #${id} — ${title}`, boardChange(id, 'board', undefined, id));
    }
  };
  const finishTodo = (id: string): void => {
    const item = store.snapshot().find((i) => i.id === id);
    if (!item) return;
    for (const sub of item.subtasks) {
      if (sub.status !== 'done') store.completeSubtask(id, sub.id);
    }
    store.completeTodo(id);
  };

  // ── 1 · thinking + intro ──────────────────────────────────────────────
  push({
    kind: 'thinking',
    id: 'hrms_thinking_1',
    duration: 3800,
    thoughts: [
      {
        text: 'The HRMS is broad: employees, departments, payroll, leave, auth. Split it into parallel workstreams so the captain coordinates sub-agents instead of doing everything serially.',
      },
      {
        text: 'Models first, then API, then admin/seed data, then tests. The docs agent can run in parallel. Track every artifact on the todo board so progress is visible.',
      },
      {
        text: 'Payroll has cross-cutting rules (tax bands, pro-rating) that could trip the test suite — that is a deliberate point of failure to demonstrate recovery.',
      },
    ],
  });

  push({
    kind: 'message',
    id: 'hrms_msg_1',
    text: 'Designing and building the **Django HRMS** app end to end. I will orchestrate parallel sub-agents, mirror every deliverable on the todo board, and run the full test suite before calling the build complete.',
    partial: false,
  });

  push({
    kind: 'plan_ready',
    id: 'hrms_plan_1',
    sessionId: 'hrms-build',
    plan:
      '## HRMS Build Plan\n' +
      '1. **Scaffold** Django project with `hrms_core`, `employees`, `payroll`, `leave` apps.\n' +
      '2. **Models**: Employee, Department, Payroll, LeaveRequest with clean relations + validations.\n' +
      '3. **API**: DRF viewsets, token auth, nested serializers, pagination.\n' +
      '4. **Admin + seed**: register models, add demo data for 3 departments and 9 employees.\n' +
      '5. **Tests**: unit + API tests for every endpoint, including payroll edge cases.\n' +
      '6. **Docs**: README with setup, API examples, and architecture overview.',
  });

  // ── 2 · planning / delegating orchestration ───────────────────────────
  let crew = crewmates();
  let plan = planItems();
  push({
    kind: 'agent_orchestration',
    id: 'hrms_orch_1',
    stage: 'planning',
    captainMessage: 'Breaking the HRMS into 6 workstreams and dispatching sub-agents for parallel execution.',
    plan,
    crewmates: Object.values(crew),
    timeline: [
      timeline('14:02:11', 'Plan ready — 6 workstreams, 4 sub-agents available'),
      timeline('14:02:14', 'Assigning model work to Model Architect, API to Backend Agent'),
    ],
    activeStep: 'P1',
  });

  plan = plan.map((p) => ({ ...p, status: 'in_progress' as const }));
  crew = patchCrew(crew, {
    devBackend: { status: 'assigned' as const, progress: 5, activity: 'Initializing Django project' },
    devModels: { status: 'assigned' as const, progress: 5, activity: 'Drafting schema' },
    qa: { status: 'assigned' as const, progress: 5, activity: 'Setting up test harness' },
    docs: { status: 'assigned' as const, progress: 5, activity: 'Outlining README' },
  });
  push({
    kind: 'agent_orchestration',
    id: 'hrms_orch_2',
    stage: 'delegating',
    captainMessage: 'Sub-agents dispatched. Model work and API work proceed in parallel.',
    plan,
    crewmates: Object.values(crew),
    timeline: [timeline('14:02:19', 'Crewmate agents dispatched', 'info')],
    activeStep: 'P1',
  });

  // ── 3 · todo board seeding ────────────────────────────────────────────
  boardSnapshot('snapshot', 'Synchronized todo board from workspace state — 0 tracked work items');

  createTodo(
    'H1',
    'Scaffold HRMS Django project',
    'high',
    'dev-backend',
    ['backend', 'django'],
    [
      { title: 'Create Django project + core config' },
      { title: 'Add hrms apps to INSTALLED_APPS' },
      { title: 'Wire settings, env + dev server' },
    ],
  );
  createTodo(
    'H2',
    'Employee + Department models',
    'high',
    'dev-models',
    ['models', 'hrms'],
    [{ title: 'Design relational schema' }, { title: 'Write models + migrations' }, { title: 'Add model validations' }],
  );
  createTodo(
    'H3',
    'Payroll + Leave domain',
    'medium',
    'dev-models',
    ['models', 'payroll'],
    [{ title: 'Payroll model + tax bands' }, { title: 'LeaveRequest model + rules' }, { title: 'Migration plan' }],
  );
  createTodo(
    'H4',
    'REST API + token auth',
    'urgent',
    'dev-backend',
    ['api', 'auth'],
    [{ title: 'DRF viewsets + serializers' }, { title: 'Token authentication' }, { title: 'Pagination + filtering' }],
  );
  createTodo(
    'H5',
    'Admin + seed data',
    'medium',
    'qa',
    ['admin', 'seed'],
    [{ title: 'Register models in admin' }, { title: 'Seed 3 departments + 9 employees' }],
  );
  createTodo(
    'H6',
    'Test suite + CI pipeline',
    'high',
    'qa',
    ['tests', 'ci'],
    [{ title: 'Unit tests for models' }, { title: 'API integration tests' }, { title: 'Payroll edge cases' }],
  );
  createTodo(
    'H7',
    'Write HRMS documentation',
    'low',
    'docs',
    ['docs'],
    [{ title: 'README + setup guide' }, { title: 'API reference examples' }],
  );

  push({
    kind: 'progress',
    id: 'hrms_progress_0',
    label: 'Analyzing HRMS requirements',
    steps: [
      { label: 'Scaffold', status: 'pending' },
      { label: 'Models', status: 'pending' },
      { label: 'API', status: 'pending' },
      { label: 'Admin', status: 'pending' },
      { label: 'Tests', status: 'pending' },
      { label: 'Docs', status: 'pending' },
    ],
    percent: 2,
  });

  // ── 4 · progress + first tool steps ───────────────────────────────────
  push({
    kind: 'progress',
    id: 'hrms_progress_1',
    label: 'Building Django HRMS',
    steps: [
      { label: 'Scaffold', status: 'active' },
      { label: 'Models', status: 'pending' },
      { label: 'API', status: 'pending' },
      { label: 'Admin', status: 'pending' },
      { label: 'Tests', status: 'pending' },
      { label: 'Docs', status: 'pending' },
    ],
    percent: 8,
  });

  push({
    kind: 'tool_call',
    id: 'tool_scaffold',
    tool: 'write_file',
    params: { path: 'hrms_project/config/settings/base.py', description: 'Project settings base' },
    text: 'Writing Django project settings',
  });
  push({
    kind: 'tool_result',
    id: 'tool_scaffold',
    tool: 'write_file',
    success: true,
    output:
      'Created hrms_project/config/settings/base.py (3.1 KB)\nINSTALLED_APPS includes employees, payroll, leave, hrms_core.',
    error: '',
    metadata: { path: 'hrms_project/config/settings/base.py', lines: 86 },
  });

  store.setStatus('H1-S1', 'done');
  boardSnapshot(
    'updated',
    'Completed H1-S1 — Create Django project + core config',
    boardChange('H1-S1', 'status', 'todo', 'done'),
  );

  push({
    kind: 'tool_call',
    id: 'tool_migrate',
    tool: 'bash',
    params: { command: 'python manage.py makemigrations employees payroll leave' },
    text: 'Generating migrations for the three HRMS apps',
  });
  push({
    kind: 'tool_result',
    id: 'tool_migrate',
    tool: 'bash',
    success: true,
    output:
      'Migrations for "employees":\n  0001_initial.py\nMigrations for "payroll":\n  0001_initial.py\nMigrations for "leave":\n  0001_initial.py\nAll 3 apps migrated cleanly.',
    error: '',
    metadata: { exitCode: 0 },
  });

  store.setStatus('H2', 'in_progress');
  boardSnapshot(
    'updated',
    'Started #H2 — Employee + Department models (Model Architect)',
    boardChange('H2', 'status', 'todo', 'in_progress'),
  );

  // ── 5 · mid-turn context compaction (edge case) ───────────────────────
  push({
    kind: 'message',
    id: 'hrms_msg_cc',
    text: 'Context is filling with tool transcripts. Compacting mid-build so the plan, board and crewmate state stay crisp for the rest of the turn.',
    partial: false,
  });
  push({
    kind: 'warning',
    id: 'hrms_warning_1',
    message: 'Context window at 88% — compacting tool transcripts to keep the build in focus.',
    code: 'CONTEXT_PRESSURE',
  });
  push({
    kind: 'context_compaction_started',
    id: 'hrms_cc_start',
    message: 'Context pressure detected — preserving build state',
    used: 112640,
    total: 128000,
  });
  push({
    kind: 'context_compaction_phase',
    id: 'hrms_cc_phase_1',
    phase: 'preserving',
    label: 'Preserving plan, board and crewmate state',
  });
  push({
    kind: 'context_compacted',
    id: 'hrms_cc_1',
    message: 'Trimmed bash output transcripts',
    tool: 'bash_output',
    tokensSaved: 24000,
  });
  push({
    kind: 'context_compacted',
    id: 'hrms_cc_2',
    message: 'Trimmed file-write echoes',
    tool: 'file_write_echo',
    tokensSaved: 18000,
  });
  push({
    kind: 'context_compaction_phase',
    id: 'hrms_cc_phase_2',
    phase: 'compacting',
    label: 'Compacting redundant tool results',
    beforeTokens: 112640,
    afterTokens: 61000,
  });
  push({
    kind: 'context_compaction_phase',
    id: 'hrms_cc_phase_3',
    phase: 'verifying',
    label: 'Verifying preserved build context',
  });
  push({
    kind: 'context_compaction_ended',
    id: 'hrms_cc_end',
    message: 'Compaction complete — build state preserved',
    used: 61000,
    total: 128000,
    tokensSaved: 51640,
    summaryChars: 18400,
    preserved: {
      requirements: 6,
      decisions: 9,
      openTasks: 7,
      findings: 4,
      artifacts: 11,
      agents: 5,
      compressedDiscussions: 3,
      redundantExchanges: 2,
      obsoleteStates: 1,
    },
    summary:
      'Preserved the 6-workstream plan, all 7 todo board items, crewmate assignments, and the payroll tax-band decision. Trimmed duplicate bash output and file-write echoes.',
  });

  // ── 6 · crewmates working ─────────────────────────────────────────────
  crew = patchCrew(crew, {
    devBackend: { status: 'working' as const, progress: 40, activity: 'Writing serializers + viewsets' },
    devModels: { status: 'working' as const, progress: 55, activity: 'Implementing payroll tax bands' },
    qa: { status: 'working' as const, progress: 30, activity: 'Seeding admin data' },
    docs: { status: 'working' as const, progress: 20, activity: 'Drafting API reference' },
  });
  plan = plan.map((p) => (p.id === 'P2' ? { ...p, status: 'completed' as const } : p));
  push({
    kind: 'agent_orchestration',
    id: 'hrms_orch_3',
    stage: 'working',
    captainMessage: 'All sub-agents active. Model work ahead of schedule; API auth in progress.',
    plan,
    crewmates: Object.values(crew),
    timeline: [
      timeline('14:04:02', 'Model Architect completed employee + department models', 'success'),
      timeline('14:04:31', 'Context compacted mid-build — state preserved', 'warning'),
    ],
    activeStep: 'P2',
  });

  finishTodo('H2');
  boardSnapshot(
    'completed',
    'Completed #H2 — Employee + Department models (all subtasks done)',
    boardChange('H2', 'status', 'in_progress', 'done'),
  );

  push({
    kind: 'tool_call',
    id: 'tool_tests_1',
    tool: 'bash',
    params: { command: 'python manage.py test employees payroll --keepdb' },
    text: 'Running the model + payroll test suite',
  });
  push({
    kind: 'tool_result',
    id: 'tool_tests_1',
    tool: 'bash',
    success: false,
    output:
      'FAILED: payroll.tests.PayrollTaxBandsTest.test_high_income_pro_rate\n' +
      'AssertionError: expected net_pay to equal 54200 but got 54850\n' +
      'pro-rating tax band 4 did not apply for incomes above 100000.',
    error: 'payroll pro-rating calculation off by one band',
    metadata: { exitCode: 1 },
  });

  // ── 7 · failure + recovery ────────────────────────────────────────────
  push({
    kind: 'error',
    id: 'hrms_error_1',
    message: 'Payroll test failure: high-income pro-rating did not apply band 4.',
    code: 'TEST_FAILURE',
    recoverable: false,
    action: 'Reassigning payroll fix to Model Architect',
    hint: 'Cross-check tax band thresholds and the pro-rating branch.',
  });

  push({
    kind: 'thinking',
    id: 'hrms_thinking_2',
    duration: 2100,
    thoughts: [
      {
        text: 'The failing assertion shows net_pay 54850 instead of 54200 — band 4 (above 100000) never pro-rated. The bug is a band-boundary comparison, not a tax-rate typo.',
      },
      {
        text: 'Small, isolated fix: adjust the pro-rating branch to apply when income > 100000. Then re-run only the payroll suite before the full pass to avoid burning tokens.',
      },
    ],
  });

  plan = plan.map((p) => (p.id === 'P3' ? { ...p, status: 'reassigned' as const } : p));
  crew = patchCrew(crew, {
    devModels: {
      status: 'reassigned' as const,
      progress: 45,
      activity: 'Fixing payroll pro-rating logic',
      resultSummary: 'Corrected band-4 threshold handling',
    },
    qa: { status: 'working' as const, progress: 50, activity: 'Preparing CI workflow' },
  });
  push({
    kind: 'agent_orchestration',
    id: 'hrms_orch_4',
    stage: 'reassigning',
    captainMessage: 'Payroll edge case found by the test suite — reassigning the fix so the build stays green.',
    plan,
    crewmates: Object.values(crew),
    timeline: [
      timeline('14:05:18', 'Test suite found payroll pro-rating bug', 'error'),
      timeline('14:05:21', 'Task P3 reassigned to Model Architect', 'reassign'),
    ],
    activeStep: 'P3',
  });

  push({
    kind: 'tool_call',
    id: 'tool_payroll_fix',
    tool: 'write_file',
    params: { path: 'payroll/tax.py', description: 'Tax band pro-rating fix' },
    text: 'Fixing the payroll pro-rating branch',
  });
  push({
    kind: 'tool_result',
    id: 'tool_payroll_fix',
    tool: 'write_file',
    success: true,
    output: 'Updated payroll/tax.py — band 4 now applies pro-rating above 100000 (net_pay 54200).',
    error: '',
    metadata: { path: 'payroll/tax.py', lines: 42 },
  });

  push({
    kind: 'tool_call',
    id: 'tool_tests_2',
    tool: 'bash',
    params: { command: 'python manage.py test payroll.tests.PayrollTaxBandsTest --keepdb' },
    text: 'Re-running the payroll tests after the fix',
  });
  push({
    kind: 'tool_result',
    id: 'tool_tests_2',
    tool: 'bash',
    success: true,
    output: 'Ran 14 tests in 1.8s\nOK — payroll tax band suite green including high-income pro-rating.',
    error: '',
    metadata: { exitCode: 0 },
  });

  push({
    kind: 'tool_call',
    id: 'tool_payroll_review',
    tool: 'read_file',
    params: { path: 'payroll/tax.py' },
    text: 'Reviewing the committed payroll fix',
  });
  push({
    kind: 'tool_result',
    id: 'tool_payroll_review',
    tool: 'read_file',
    success: true,
    output:
      'payroll/tax.py (42 lines): band thresholds 0–37000, 37000–87000, 87000–100000, >100000 with pro-rating applied; fix localized to the band-4 branch.',
    error: '',
    metadata: { path: 'payroll/tax.py' },
  });

  push({
    kind: 'tool_call',
    id: 'tool_ci',
    tool: 'write_file',
    params: { path: '.github/workflows/ci.yml', description: 'CI pipeline: lint + test on pull request' },
    text: 'Writing the CI workflow for the build',
  });
  push({
    kind: 'tool_result',
    id: 'tool_ci',
    tool: 'write_file',
    success: true,
    output: 'Wrote .github/workflows/ci.yml — runs flake8 and the Django test suite on PRs.',
    error: '',
    metadata: { path: '.github/workflows/ci.yml', lines: 34 },
  });

  crew = patchCrew(crew, {
    devBackend: { status: 'returning' as const, progress: 95, activity: 'Handing off final API files' },
  });
  push({
    kind: 'agent_orchestration',
    id: 'hrms_orch_ret',
    stage: 'working',
    captainMessage: 'Backend Agent is handing off the final API work — almost ready for the wrap-up.',
    plan,
    crewmates: Object.values(crew),
    timeline: [timeline('14:06:40', 'Backend Agent returning — API work complete', 'info')],
    activeStep: 'P4',
  });

  // ── 8 · todo board dynamics (blocked → unblocked, cancelled) ──────────
  store.setStatus('H3-S1', 'in_progress');
  store.setStatus('H3', 'blocked');
  boardSnapshot(
    'updated',
    'Blocked #H3 — payroll migration depends on tax.py refactor',
    boardChange('H3', 'status', 'in_progress', 'blocked'),
  );

  store.setStatus('H3', 'in_progress');
  boardSnapshot(
    'updated',
    'Unblocked #H3 — tax.py refactor landed',
    boardChange('H3', 'status', 'blocked', 'in_progress'),
  );

  store.setStatus('H5', 'cancelled');
  boardSnapshot(
    'cancelled',
    'Cancelled #H5 — admin seed data deferred to sprint 2, tracking removed',
    boardChange('H5', 'status', 'todo', 'cancelled'),
  );

  push({
    kind: 'warning',
    id: 'hrms_warning_2',
    message: 'Feature branch drifted 3 commits behind main — rebase scheduled before merge.',
    code: 'GIT_DRIFT',
  });

  store.setStatus('H4-S1', 'in_progress');
  store.setStatus('H6-S1', 'done');
  store.setStatus('H7-S1', 'done');
  boardSnapshot(
    'updated',
    'Subtasks progressing — H4 serializers in progress, H6 leave accrual and H7 docs subtasks done',
    boardChange('H4-S1', 'status', 'todo', 'in_progress'),
  );

  // ── 9 · turn manifest (work in progress) ──────────────────────────────
  push({
    kind: 'turn_manifest',
    id: 'hrms_manifest_1',
    created: ['hrms_project/', 'employees/', 'payroll/', 'leave/', 'hrms_core/'],
    modified: ['payroll/tax.py', 'employees/models.py', 'hrms_project/config/settings/base.py'],
    remaining: ['P4 API auth', 'P5 admin/seed (deferred)', 'P6 CI'],
    completed: false,
    stalled: false,
    files: [
      { path: 'payroll/tax.py', exists: true, size: 1842 },
      { path: 'employees/models.py', exists: true, size: 5240 },
      { path: 'hrms_project/config/settings/base.py', exists: true, size: 3168 },
    ],
  });

  // ── 10 · reviewing / completing ───────────────────────────────────────
  crew = patchCrew(crew, {
    devBackend: {
      status: 'completed' as const,
      progress: 100,
      resultSummary: 'API + token auth shipped, all 22 API tests green',
    },
    devModels: { status: 'completed' as const, progress: 100, resultSummary: 'Models + payroll fix complete' },
    qa: { status: 'needs_review' as const, progress: 85, activity: 'Final CI pass' },
    docs: { status: 'completed' as const, progress: 100, resultSummary: 'README + API reference published' },
  });
  plan = plan.map((p) =>
    p.id === 'P4' || p.id === 'P6'
      ? { ...p, status: 'in_progress' as const }
      : p.id === 'P5'
        ? { ...p, status: 'reassigned' as const }
        : { ...p, status: 'completed' as const },
  );
  push({
    kind: 'agent_orchestration',
    id: 'hrms_orch_5',
    stage: 'reviewing',
    captainMessage: 'Three workstreams complete. QA is validating the CI pass before I synthesize the final report.',
    plan,
    crewmates: Object.values(crew),
    timeline: [
      timeline('14:07:44', 'Backend Agent returned — API + auth shipped', 'success'),
      timeline('14:07:50', 'QA Sentinel needs review — final CI pass', 'info'),
    ],
    activeStep: 'P6',
  });

  finishTodo('H1');
  finishTodo('H3');
  finishTodo('H4');
  finishTodo('H6');
  finishTodo('H7');
  boardSnapshot(
    'completed',
    'Completed #H1, #H3, #H4, #H6, #H7 — all active workstreams done',
    boardChange('H6', 'status', 'in_progress', 'done'),
  );

  push({
    kind: 'progress',
    id: 'hrms_progress_2',
    label: 'Building Django HRMS',
    steps: [
      { label: 'Scaffold', status: 'done' },
      { label: 'Models', status: 'done' },
      { label: 'API', status: 'done' },
      { label: 'Admin', status: 'pending' },
      { label: 'Tests', status: 'done' },
      { label: 'Docs', status: 'done' },
    ],
    percent: 96,
  });

  // ── 11 · final manifest + orchestration complete + success ────────────
  push({
    kind: 'turn_manifest',
    id: 'hrms_manifest_2',
    created: ['hrms_project/', 'employees/', 'payroll/', 'leave/', 'hrms_core/', 'docs/'],
    modified: ['payroll/tax.py', 'employees/models.py', 'hrms_project/config/settings/base.py', 'tests/'],
    remaining: ['P5 admin seed (sprint 2)'],
    completed: true,
    stalled: false,
    files: [
      { path: 'payroll/tax.py', exists: true, size: 1842 },
      { path: 'employees/models.py', exists: true, size: 5240 },
      { path: 'tests/test_payroll.py', exists: true, size: 6120 },
      { path: 'docs/README.md', exists: true, size: 4210 },
    ],
  });

  crew = patchCrew(crew, {
    qa: { status: 'reviewed' as const, progress: 100, resultSummary: 'CI pipeline green — 68 tests passing' },
  });
  plan = plan.map((p) => ({ ...p, status: 'completed' as const }));
  push({
    kind: 'agent_orchestration',
    id: 'hrms_orch_6',
    stage: 'complete',
    captainMessage: 'HRMS build complete — every workstream merged, all tests green.',
    plan,
    crewmates: Object.values(crew),
    timeline: [
      timeline('14:08:02', 'QA Sentinel reviewed — CI green (68 tests)', 'success'),
      timeline('14:08:05', 'Orchestration complete', 'success'),
    ],
  });

  boardSnapshot(
    'completed',
    'Simulation complete — 6 todos done, 1 cancelled. Django HRMS build verified end to end.',
    boardChange('H7', 'status', 'in_progress', 'done'),
  );

  push({
    kind: 'message',
    id: 'hrms_msg_final',
    text: '**Django HRMS shipped.** Models, API + token auth, admin, payroll with a verified pro-rating fix, and 68 green tests. Documentation published under `docs/`. The build survived a mid-turn context compaction and a payroll test failure that was caught and recovered in the same turn.',
    partial: false,
  });

  push({
    kind: 'success',
    id: 'hrms_success',
    message: 'Django HRMS build complete — 6 workstreams, 68 tests green',
    iterations: 12,
    elapsedMs: 58240,
    tokenInfo: { used: 68420, remaining: 59580, total: 128000, percent: 53 },
  });

  return {
    prompt: HRMS_PROMPT,
    events,
    boardEvents: events.filter((e) => e.kind === 'todo_board').length,
    finalBoard: store.snapshot(),
  };
}

/** Convenience for tests that only need the typed event stream. */
export function collectHrmsBuildEvents(): ScenarioEvent[] {
  return runHrmsBuildSimulation().events;
}
