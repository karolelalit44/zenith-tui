import { describe, expect, it } from 'vitest';
import type { ScenarioEvent } from '../src/types/scenario';
import { consolidateOrchestrationEvents } from '../src/utils/orchestration';

describe('consolidateOrchestrationEvents', () => {
  it('returns null when no orchestration or crewmate events exist', () => {
    const events: ScenarioEvent[] = [
      { kind: 'user_prompt', id: '1', prompt: 'Hello' } as any,
      { kind: 'message', id: '2', text: 'Hi', partial: false } as any,
    ];
    expect(consolidateOrchestrationEvents(events)).toBeNull();
  });

  it('consolidates raw crewmate lifecycle events into single unified state', () => {
    const events: ScenarioEvent[] = [
      {
        kind: 'crewmate_spawned',
        id: 'ev_spawn',
        crewmateId: 'scout_1',
        name: 'Apogee',
        role: 'Explorer',
        taskId: 't1',
        capability: 'read_code',
      } as any,
      {
        kind: 'crewmate_status',
        id: 'ev_stat',
        crewmateId: 'scout_1',
        status: 'working',
        activity: 'Reading files',
        progress: 50,
      } as any,
      {
        kind: 'crewmate_complete',
        id: 'ev_comp',
        crewmateId: 'scout_1',
        taskId: 't1',
        resultSummary: 'Investigation successful',
        status: 'completed',
      } as any,
    ];

    const orch = consolidateOrchestrationEvents(events);
    expect(orch).not.toBeNull();
    expect(orch?.crewmates).toHaveLength(1);
    expect(orch?.crewmates?.[0].name).toBe('Apogee');
    expect(orch?.crewmates?.[0].status).toBe('completed');
    expect(orch?.crewmates?.[0].resultSummary).toBe('Investigation successful');
    expect(orch?.allComplete).toBe(true);
    expect(orch?.hasFailedCrew).toBe(false);
    expect(orch?.timeline).toBeDefined();
    expect(orch?.timeline?.some((t) => t.message.includes('Spawned Apogee'))).toBe(true);
    expect(orch?.timeline?.some((t) => t.message.includes('Investigation successful'))).toBe(true);
  });

  it('flags hasFailedCrew when crewmate fails', () => {
    const events: ScenarioEvent[] = [
      {
        kind: 'crewmate_spawned',
        id: 'ev_spawn',
        crewmateId: 'builder_1',
        name: 'Builder',
        role: 'Implementer',
        taskId: 't2',
        capability: 'build',
      } as any,
      {
        kind: 'crewmate_failed',
        id: 'ev_fail',
        crewmateId: 'builder_1',
        taskId: 't2',
        error: 'Syntax error in generated code',
      } as any,
    ];

    const orch = consolidateOrchestrationEvents(events);
    expect(orch).not.toBeNull();
    expect(orch?.hasFailedCrew).toBe(true);
    expect(orch?.allComplete).toBe(false);
    expect(orch?.crewmates?.[0].status).toBe('failed');
    expect(orch?.crewmates?.[0].error).toBe('Syntax error in generated code');
  });

  it('merges lifecycle events into the orchid crewmate when ids match (no phantom rows)', () => {
    const events: ScenarioEvent[] = [
      {
        kind: 'captain_orchestration',
        id: 'ev_orch',
        stage: 'working',
        captainMessage: 'Audit the config layer',
        crewmates: [
          {
            id: 'apogee:abc12345',
            name: 'Apogee',
            role: 'Codebase Cartographer',
            task: 'Audit the config layer',
            status: 'assigned',
            progress: 0,
          },
        ],
      } as any,
      {
        kind: 'crewmate_status',
        id: 'ev_stat',
        crewmateId: 'apogee:abc12345',
        status: 'working',
        activity: 'Reading tools.py',
        progress: 50,
      } as any,
      {
        kind: 'crewmate_complete',
        id: 'ev_comp',
        crewmateId: 'apogee:abc12345',
        taskId: 't1',
        resultSummary: 'Audit complete',
        status: 'completed',
      } as any,
    ];

    const orch = consolidateOrchestrationEvents(events);
    expect(orch?.crewmates).toHaveLength(1);
    const crew = orch?.crewmates?.[0];
    expect(crew?.id).toBe('apogee:abc12345');
    expect(crew?.status).toBe('completed');
    expect(crew?.progress).toBe(100);
    expect(crew?.resultSummary).toBe('Audit complete');
    expect(orch?.allComplete).toBe(true);
  });

  it('synthesizes in-flight explore tool step from real nested crewmate params', () => {
    const events: ScenarioEvent[] = [
      {
        kind: 'tool_step',
        id: 'ev_tool',
        tool: 'explore',
        pending: true,
        params: {
          objective: 'Find constants',
          crewmate: { name: 'Nimue', role: 'Implementer', model: 'nemotron-70b' },
        },
      } as any,
    ];

    const orch = consolidateOrchestrationEvents(events);
    expect(orch).not.toBeNull();
    expect(orch?.stage).toBe('working');
    expect(orch?.crewmates).toHaveLength(1);
    expect(orch?.crewmates?.[0].name).toBe('Nimue');
    expect(orch?.crewmates?.[0].role).toBe('Implementer');
    expect(orch?.crewmates?.[0].status).toBe('working');
    // No fabricated progress on an unresolved mission.
    expect(orch?.crewmates?.[0].progress).toBeUndefined();
  });

  it('resolves to null once explore finishes without an orchestration snapshot', () => {
    const events: ScenarioEvent[] = [
      {
        kind: 'tool_step',
        id: 'ev_tool',
        tool: 'explore',
        pending: true,
        params: { objective: 'Find constants', crewmate: { name: 'Apogee' } },
      } as any,
      {
        kind: 'tool_step',
        id: 'ev_tool',
        tool: 'explore',
        pending: false,
        success: false,
        params: { objective: 'Find constants', crewmate: { name: 'Apogee' } },
      } as any,
    ];

    const orch = consolidateOrchestrationEvents(events);
    expect(orch).toBeNull();
  });
});
