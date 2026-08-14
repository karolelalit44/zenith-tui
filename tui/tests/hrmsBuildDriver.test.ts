import { describe, expect, it } from 'vitest';
import { HRMS_PROMPT, runHrmsBuildSimulation } from '../src/services/scenario/hrmsBuildDriver';
import type {
  AgentOrchestrationEvent,
  ScenarioEvent,
  TodoBoardEvent,
  ToolCallEvent,
  ToolResultEvent,
} from '../src/types/scenario';

const run = () => runHrmsBuildSimulation();

describe('runHrmsBuildSimulation', () => {
  it('is a long end-to-end build stream covering every event kind', () => {
    const { events } = run();
    expect(events.length).toBeGreaterThanOrEqual(60);

    const kinds = new Set(events.map((e) => e.kind));
    for (const expected of [
      'thinking',
      'message',
      'plan_ready',
      'agent_orchestration',
      'todo_board',
      'progress',
      'tool_call',
      'tool_result',
      'warning',
      'context_compaction_started',
      'context_compaction_phase',
      'context_compacted',
      'context_compaction_ended',
      'turn_manifest',
      'error',
      'success',
    ] as const) {
      expect(kinds.has(expected), `expected kind ${expected}`).toBe(true);
    }
  });

  it('pairs every tool_call with a tool_result sharing id + tool', () => {
    const { events } = run();
    const calls = events.filter((e): e is ToolCallEvent => e.kind === 'tool_call');
    const results = events.filter((e): e is ToolResultEvent => e.kind === 'tool_result');
    expect(calls.length).toBeGreaterThanOrEqual(5);
    expect(calls.length).toBe(results.length);

    for (let i = 0; i < calls.length; i += 1) {
      expect(results[i].id).toBe(calls[i].id);
      expect(results[i].tool).toBe(calls[i].tool);
    }
  });

  it('contains a failing tool step followed by a successful recovery', () => {
    const { events } = run();
    const results = events.filter((e): e is ToolResultEvent => e.kind === 'tool_result');
    const failed = results.find((r) => !r.success);
    expect(failed).toBeDefined();
    expect(failed?.output).toContain('FAILED');

    const failedIndex = events.findIndex((e) => e.id === failed?.id);
    const recovery = results.find(
      (r) => r.tool === 'bash' && r.success && events.findIndex((e) => e.id === r.id) > failedIndex,
    );
    expect(recovery).toBeDefined();
    expect(recovery?.output).toContain('OK');

    const successfulAfterFailure = results.find((r) => events.findIndex((e) => e.id === r.id) > failedIndex);
    expect(successfulAfterFailure).toBeDefined();
    expect(successfulAfterFailure?.id).toBe('tool_payroll_fix');
  });

  it('emits a non-recoverable error so no retry banner is triggered', () => {
    const { events } = run();
    const error = events.find((e): e is Extract<ScenarioEvent, { kind: 'error' }> => e.kind === 'error');
    expect(error).toBeDefined();
    expect(error?.recoverable).toBe(false);
  });

  it('keeps crewmate ids stable across orchestration events', () => {
    const { events } = run();
    const orch = events.filter((e): e is AgentOrchestrationEvent => e.kind === 'agent_orchestration');
    expect(orch.length).toBeGreaterThanOrEqual(4);
    const firstIds = (orch[0].crewmates ?? []).map((c) => c.id).sort();
    const lastIds = (orch[orch.length - 1].crewmates ?? []).map((c) => c.id).sort();
    expect(firstIds).toEqual(lastIds);
    expect(firstIds).toEqual(['dev-backend', 'dev-models', 'docs', 'qa']);
  });

  it('ends with a completed todo board snapshot and a success event', () => {
    const { events, finalBoard } = run();
    const boards = events.filter((e): e is TodoBoardEvent => e.kind === 'todo_board');
    expect(boards[boards.length - 1].action).toBe('completed');
    expect(finalBoard.length).toBeGreaterThanOrEqual(6);
    expect(finalBoard.some((t) => t.status === 'done')).toBe(true);
    expect(finalBoard.some((t) => t.status === 'cancelled')).toBe(true);
    expect(events.at(-1)?.kind).toBe('success');
  });

  it('produces a build-mode prompt for the turn header', () => {
    const { prompt } = run();
    expect(prompt).toContain('Django HRMS');
    expect(HRMS_PROMPT).toBe(prompt);
  });

  it('exercises todo board edge states: blocked → unblocked → cancelled', () => {
    const { events } = run();
    const messages = events.filter((e): e is TodoBoardEvent => e.kind === 'todo_board').map((e) => e.message ?? '');
    expect(messages.some((m) => m.includes('Blocked #H3'))).toBe(true);
    expect(messages.some((m) => m.includes('Unblocked #H3'))).toBe(true);
    expect(messages.some((m) => m.includes('Cancelled #H5'))).toBe(true);
  });
});
