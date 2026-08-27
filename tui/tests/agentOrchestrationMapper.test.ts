import { describe, expect, it } from 'vitest';
import { mapRawEvent } from '../src/services/transport/rawEventMapper';

describe('rawEventMapper sub-agent lifecycle kinds', () => {
  it('maps agent_spawned to a typed AgentSpawnedEvent', () => {
    const evt = mapRawEvent(
      'agent_spawned',
      {
        agent_id: 'codebase-scout',
        name: 'Codebase Scout',
        role: 'Codebase Investigator',
        task_id: 'task-123',
        capability: 'persistence_analysis',
        parent_session_id: 'sess-parent',
        model: 'gpt-test',
      },
      'evt_1',
    );

    expect(evt.kind).toBe('agent_spawned');
    if (evt.kind !== 'agent_spawned') return;
    expect(evt.agentId).toBe('codebase-scout');
    expect(evt.name).toBe('Codebase Scout');
    expect(evt.role).toBe('Codebase Investigator');
    expect(evt.taskId).toBe('task-123');
    expect(evt.capability).toBe('persistence_analysis');
    expect(evt.parentSessionId).toBe('sess-parent');
    expect(evt.model).toBe('gpt-test');
  });

  it('maps agent_status with truncated activity and progress', () => {
    const evt = mapRawEvent(
      'agent_status',
      {
        agent_id: 'codebase-scout',
        status: 'working',
        activity: 'tool file_read: server/domain/session.py',
        progress: 50,
      },
      'evt_2',
    );

    expect(evt.kind).toBe('agent_status');
    if (evt.kind !== 'agent_status') return;
    expect(evt.agentId).toBe('codebase-scout');
    expect(evt.status).toBe('working');
    expect(evt.activity).toContain('file_read');
    expect(evt.progress).toBe(50);
  });

  it('maps agent_complete with result summary', () => {
    const evt = mapRawEvent(
      'agent_complete',
      {
        agent_id: 'codebase-scout',
        task_id: 'task-123',
        result_summary: 'Sessions persist via SQLite SessionRepository.',
        status: 'completed',
      },
      'evt_3',
    );

    expect(evt.kind).toBe('agent_complete');
    if (evt.kind !== 'agent_complete') return;
    expect(evt.agentId).toBe('codebase-scout');
    expect(evt.taskId).toBe('task-123');
    expect(evt.resultSummary).toBe('Sessions persist via SQLite SessionRepository.');
    expect(evt.status).toBe('completed');
  });

  it('maps agent_failed with error text', () => {
    const evt = mapRawEvent(
      'agent_failed',
      {
        agent_id: 'codebase-scout',
        task_id: 'task-456',
        error: 'Investigation exceeded timeout.',
      },
      'evt_4',
    );

    expect(evt.kind).toBe('agent_failed');
    if (evt.kind !== 'agent_failed') return;
    expect(evt.agentId).toBe('codebase-scout');
    expect(evt.taskId).toBe('task-456');
    expect(evt.error).toBe('Investigation exceeded timeout.');
  });

  it('still falls back to a warning card for unknown kinds', () => {
    const evt = mapRawEvent('totally_unknown_kind', { foo: 1 }, 'evt_5');

    expect(evt.kind).toBe('warning');
    if (evt.kind !== 'warning') return;
    expect(evt.code).toBe('UNKNOWN_EVENT');
    expect(evt.message).toContain('totally_unknown_kind');
  });
});
