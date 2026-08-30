import { describe, expect, it } from 'vitest';
import { mapRawEvent } from '../src/services/transport/rawEventMapper';

describe('rawEventMapper crewmate lifecycle kinds', () => {
  it('maps crewmate_spawned to a typed CrewmateSpawnedEvent', () => {
    const evt = mapRawEvent(
      'crewmate_spawned',
      {
        crewmate_id: 'codebase-scout',
        name: 'Apogee',
        role: 'Codebase Cartographer',
        task_id: 'task-123',
        capability: 'persistence_analysis',
        parent_session_id: 'sess-parent',
        model: 'gpt-test',
      },
      'evt_1',
    );

    expect(evt.kind).toBe('crewmate_spawned');
    if (evt.kind !== 'crewmate_spawned') return;
    expect(evt.crewmateId).toBe('codebase-scout');
    expect(evt.name).toBe('Apogee');
    expect(evt.role).toBe('Codebase Cartographer');
    expect(evt.taskId).toBe('task-123');
    expect(evt.capability).toBe('persistence_analysis');
    expect(evt.parentSessionId).toBe('sess-parent');
    expect(evt.model).toBe('gpt-test');
  });

  it('maps crewmate_status with truncated activity and progress', () => {
    const evt = mapRawEvent(
      'crewmate_status',
      {
        crewmate_id: 'codebase-scout',
        status: 'working',
        activity: 'tool file_read: server/domain/session.py',
        progress: 50,
      },
      'evt_2',
    );

    expect(evt.kind).toBe('crewmate_status');
    if (evt.kind !== 'crewmate_status') return;
    expect(evt.crewmateId).toBe('codebase-scout');
    expect(evt.status).toBe('working');
    expect(evt.activity).toContain('file_read');
    expect(evt.progress).toBe(50);
  });

  it('maps crewmate_complete with result summary', () => {
    const evt = mapRawEvent(
      'crewmate_complete',
      {
        crewmate_id: 'codebase-scout',
        task_id: 'task-123',
        result_summary: 'Sessions persist via SQLite SessionRepository.',
        status: 'completed',
      },
      'evt_3',
    );

    expect(evt.kind).toBe('crewmate_complete');
    if (evt.kind !== 'crewmate_complete') return;
    expect(evt.crewmateId).toBe('codebase-scout');
    expect(evt.taskId).toBe('task-123');
    expect(evt.resultSummary).toBe('Sessions persist via SQLite SessionRepository.');
    expect(evt.status).toBe('completed');
  });

  it('maps crewmate_failed with error text', () => {
    const evt = mapRawEvent(
      'crewmate_failed',
      {
        crewmate_id: 'codebase-scout',
        task_id: 'task-456',
        error: 'Investigation exceeded timeout.',
      },
      'evt_4',
    );

    expect(evt.kind).toBe('crewmate_failed');
    if (evt.kind !== 'crewmate_failed') return;
    expect(evt.crewmateId).toBe('codebase-scout');
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
