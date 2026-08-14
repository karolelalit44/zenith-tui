import type {
  ScenarioEvent,
  TodoLifecyclePhase,
  TodoTestAssertion,
  TodoTestEvent,
  TodoTestRejectedOp,
} from '../types/scenario';

const TODO_TEST_KIND = 'todo_test';

export interface ConsolidatedTodoReport {
  kind: 'todo_test';
  id: string;
  phase: TodoLifecyclePhase;
  scenario: string;
  passed: boolean;
  assertions: TodoTestAssertion[];
  rejectedOps?: TodoTestRejectedOp[];
  elapsedMs?: number;
  /** Phase index in the canonical lifecycle order, for the stepper. */
  stepIndex: number;
  passedCount: number;
  totalCount: number;
  phases: TodoLifecyclePhase[];
}

export const LIFECYCLE_ORDER: TodoLifecyclePhase[] = [
  'create',
  'manage',
  'update',
  'progress',
  'complete',
  'reopen',
  'persist',
];

export const LIFECYCLE_LABEL: Record<TodoLifecyclePhase, string> = {
  create: 'Create',
  manage: 'Manage',
  update: 'Update',
  progress: 'Progress',
  complete: 'Complete',
  reopen: 'Reopen',
  persist: 'Persist',
};

/**
 * Fold every `todo_test` emission into ONE evolving report card.
 *
 * The live simulation emits a scenario result per phase. Instead of stacking
 * N cards, the renderer shows a single card whose assertions/rejected-ops are
 * appended phase by phase, with a stepper that lights up as each phase lands.
 * Returns `null` when no todo_test events are present.
 */
export function consolidateTodoTestEvents(events: ScenarioEvent[]): ConsolidatedTodoReport | null {
  const present = events.filter((e): e is TodoTestEvent => e.kind === TODO_TEST_KIND);
  if (present.length === 0) return null;

  const last = present[present.length - 1];
  const assertions: TodoTestAssertion[] = [];
  const rejectedOps: TodoTestRejectedOp[] = [];

  for (const evt of present) {
    assertions.push(...evt.assertions);
    if (evt.rejectedOps) rejectedOps.push(...evt.rejectedOps);
  }

  const passedCount = assertions.filter((a) => a.passed).length;
  const stepIndex = Math.max(0, LIFECYCLE_ORDER.indexOf(last.phase));

  return {
    kind: 'todo_test',
    id: last.id,
    phase: last.phase,
    scenario: last.scenario,
    passed: last.passed,
    assertions,
    rejectedOps: rejectedOps.length > 0 ? rejectedOps : undefined,
    elapsedMs: last.elapsedMs,
    stepIndex,
    passedCount,
    totalCount: assertions.length,
    phases: LIFECYCLE_ORDER,
  };
}

/** % of assertions that passed so far, as an integer 0–100. */
export function reportPercent(report: ConsolidatedTodoReport): number {
  if (report.totalCount === 0) return 0;
  return Math.round((report.passedCount / report.totalCount) * 100);
}
