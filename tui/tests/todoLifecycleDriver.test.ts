import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { LIFECYCLE_PHASES, type LifecycleRun, runTodoLifecycle } from '../src/services/todo/todoLifecycleDriver';
import { TODO_LIFECYCLE_FILE, todoPersistence } from '../src/services/todo/todoPersistence';
import type { ScenarioEvent, TodoBoardEvent, TodoTestEvent } from '../src/types/scenario';

let tempDir: string;

beforeEach(() => {
  tempDir = mkdtempSync(path.join(tmpdir(), 'todo-driver-'));
});

afterEach(() => {
  rmSync(tempDir, { recursive: true, force: true });
});

function run(outputDir?: string): LifecycleRun {
  return runTodoLifecycle({ outputDir: outputDir ?? tempDir });
}

describe('runTodoLifecycle', () => {
  it('runs every lifecycle phase in order and reports all scenarios passing', () => {
    const result = run();
    const phases = result.testEvents.map((t) => t.phase);
    // Two scenarios share the 'complete' phase, so assert the FIRST occurrence
    // of each phase follows the canonical lifecycle order.
    const firstOccurrence = [...new Set(phases)];
    expect(firstOccurrence).toEqual(LIFECYCLE_PHASES);
    expect(phases.length).toBeGreaterThanOrEqual(LIFECYCLE_PHASES.length + 1);
    expect(result.passed).toBe(result.total);
    expect(result.passed).toBeGreaterThanOrEqual(8);
  });

  it('emits board snapshots interleaved with scenario results ending completed', () => {
    const result = run();
    const boardKinds = result.events.map((e) => e.kind);
    expect(boardKinds[0]).toBe('todo_board');

    const boards = result.events.filter((e): e is TodoBoardEvent => e.kind === 'todo_board');
    expect(boards[0].action).toBe('snapshot');
    expect(boards[boards.length - 1].action).toBe('completed');
    expect(result.finalBoard).toHaveLength(1);
    expect(result.finalBoard[0].status).toBe('done');
  });

  it('captures rejected edge cases as rejectedOps with reasons', () => {
    const result = run();
    const rejected = result.testEvents.flatMap((t) => t.rejectedOps ?? []);
    expect(rejected.length).toBeGreaterThan(10);
    const ops = rejected.map((r) => r.op);
    expect(ops).toContain('createTodo(blank title)');
    expect(ops).toContain('setStatus(todo → done) direct');
    expect(ops).toContain('completeTodo(already done)');
    expect(ops).toContain('reopenTodo(active item)');
    for (const r of rejected) {
      expect(r.reason.length).toBeGreaterThan(0);
    }
  });

  it('exercises real persistence: file written, fresh store reloads identical board', () => {
    const result = run(tempDir);
    expect(result.persistedPath).toBe(path.join(tempDir, TODO_LIFECYCLE_FILE));
    expect(() => readFileSync(result.persistedPath, 'utf8')).not.toThrow();

    const reloaded = todoPersistence.load(result.persistedPath);
    expect(reloaded).toEqual(result.finalBoard);

    // The persist scenario itself asserts deep equality after a fresh-store reload.
    const persistScenario = result.testEvents.at(-1);
    expect(persistScenario?.phase).toBe('persist');
    const reloadAssertion = persistScenario?.assertions.find((a) => a.label.includes('deep-equal'));
    expect(reloadAssertion?.passed).toBe(true);
  });

  it('uses the env override for the output directory when provided', () => {
    const override = path.join(tempDir, 'env-override');
    const prev = process.env.ZENITH_SIM_OUTPUT_DIR;
    process.env.ZENITH_SIM_OUTPUT_DIR = override;
    try {
      const result = runTodoLifecycle();
      expect(result.persistedPath.startsWith(override)).toBe(true);
    } finally {
      if (prev === undefined) delete process.env.ZENITH_SIM_OUTPUT_DIR;
      else process.env.ZENITH_SIM_OUTPUT_DIR = prev;
    }
  });

  it('writes deterministic ids and ends with message + success events', () => {
    const result = run();
    const kinds = result.events.map((e) => e.kind);
    expect(kinds[kinds.length - 1]).toBe('success');
    expect(kinds[kinds.length - 2]).toBe('message');
    const ids = result.events.map((e: ScenarioEvent) => e.id);
    expect(new Set(ids).size).toBe(ids.length);
    const tests = result.events.filter((e): e is TodoTestEvent => e.kind === 'todo_test');
    for (const t of tests) {
      expect(t.assertions.length).toBeGreaterThan(0);
    }
  });
});
