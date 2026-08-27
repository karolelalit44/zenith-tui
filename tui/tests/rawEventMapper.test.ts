import { describe, expect, it } from 'vitest';
import { mapRawEvent } from '../src/services/transport/rawEventMapper';

describe('rawEventMapper success tokenInfo', () => {
  it('passes through composed occupancy plus run/API telemetry fields', () => {
    const evt = mapRawEvent(
      'success',
      {
        message: 'ok',
        iterations: 5,
        elapsedMs: 1000,
        tokenInfo: {
          used: 50_000,
          remaining: 78_000,
          total: 128_000,
          percent: 0.390625,
          estimated: false,
          windowEstimated: true,
          runTotal: 52_316,
          runPrompt: 1_821,
          runCompletion: 50_495,
        },
      },
      'evt_modern',
    );

    expect(evt.kind).toBe('success');
    if (evt.kind !== 'success') return;
    expect(evt.tokenInfo).toEqual({
      used: 50_000,
      remaining: 78_000,
      total: 128_000,
      percent: 0.390625,
      estimated: false,
      windowEstimated: true,
      runTotal: 52_316,
      runPrompt: 1_821,
      runCompletion: 50_495,
    });
  });

  it('keeps legacy events byte-compatible (new fields omitted, safe defaults)', () => {
    const evt = mapRawEvent(
      'success',
      {
        message: 'legacy',
        tokenInfo: { used: 100, remaining: 900, total: 1000, percent: 0.1 },
      },
      'evt_legacy',
    );

    expect(evt.kind).toBe('success');
    if (evt.kind !== 'success') return;
    expect(evt.tokenInfo).toEqual({
      used: 100,
      remaining: 900,
      total: 1000,
      percent: 0.1,
      estimated: false,
    });
    expect(evt.tokenInfo?.runTotal).toBeUndefined();
    expect(evt.tokenInfo?.windowEstimated).toBeUndefined();
  });

  it('maps a success without tokenInfo to undefined', () => {
    const evt = mapRawEvent('success', { message: 'done' }, 'evt_none');
    expect(evt.kind).toBe('success');
    if (evt.kind !== 'success') return;
    expect(evt.tokenInfo).toBeUndefined();
  });

  it('omits non-finite or non-numeric run telemetry values', () => {
    const evt = mapRawEvent(
      'success',
      {
        message: 'x',
        tokenInfo: {
          used: 1,
          remaining: 1,
          total: 2,
          percent: 0.5,
          windowEstimated: 'yes',
          runTotal: '52316',
          runPrompt: Number.NaN,
        } as unknown as Record<string, unknown>,
      },
      'evt_bad',
    );

    expect(evt.kind).toBe('success');
    if (evt.kind !== 'success') return;
    expect(evt.tokenInfo?.runTotal).toBeUndefined();
    expect(evt.tokenInfo?.runPrompt).toBeUndefined();
    expect(evt.tokenInfo?.runCompletion).toBeUndefined();
    expect(evt.tokenInfo?.windowEstimated).toBeUndefined();
    expect(evt.tokenInfo?.estimated).toBe(false);
  });
});

describe('rawEventMapper progress (QA-7)', () => {
  it('maps progress events derived from executed tool activity', () => {
    const evt = mapRawEvent(
      'progress',
      {
        percent: 50,
        label: 'Writing files',
        iteration: 2,
        steps: [
          { label: 'Writing files', status: 'done' },
          { label: 'Reading files', status: 'done' },
        ],
      },
      'evt_prog',
    );

    expect(evt.kind).toBe('progress');
    if (evt.kind !== 'progress') return;
    expect(evt.label).toBe('Writing files');
    expect(evt.percent).toBe(50);
    expect(evt.iteration).toBe(2);
    expect(evt.steps).toHaveLength(2);
    expect(evt.steps[0].label).toBe('Writing files');
    expect(evt.steps[0].status).toBe('done');
  });

  it('falls back to status when label is absent and defaults steps to empty', () => {
    const evt = mapRawEvent('progress', { status: 'Working', percent: 10 }, 'evt_prog2');

    expect(evt.kind).toBe('progress');
    if (evt.kind !== 'progress') return;
    expect(evt.label).toBe('Working');
    expect(evt.steps).toEqual([]);
  });
});

describe('rawEventMapper session/context/token (QA-9)', () => {
  it('maps session_state_changed to a typed status line (no UNKNOWN_EVENT)', () => {
    const evt = mapRawEvent(
      'session_state_changed',
      { session_id: 's1', from_state: 'active', to_state: 'completed', reason: 'Turn done' },
      'evt_sess',
    );

    expect(evt.kind).toBe('session_state_changed');
    if (evt.kind !== 'session_state_changed') return;
    expect(evt.message).toContain('active → completed');
    expect(evt.sessionId).toBe('s1');
    expect(evt.fromState).toBe('active');
    expect(evt.toState).toBe('completed');
  });

  it('maps session_resumed and session_created with a stable default message', () => {
    const resumed = mapRawEvent('session_resumed', { session_id: 's1' }, 'evt_res');
    expect(resumed.kind).toBe('session_resumed');
    if (resumed.kind !== 'session_resumed') return;
    expect(resumed.message).toBe('Session resumed');

    const created = mapRawEvent('session_created', { session_id: 's2', title: 'Fix bug', mode: 'build' }, 'evt_cre');
    expect(created.kind).toBe('session_created');
  });

  it('maps the lifecycle statuses added with session duplication (C-F23 labels)', () => {
    for (const kind of ['session_duplicated', 'session_archived', 'session_deleted', 'session_restored'] as const) {
      const evt = mapRawEvent(kind, { session_id: 's9' }, `evt_${kind}`);
      expect(evt.kind).toBe(kind);
      if (evt.kind !== kind) return;
      expect((evt as { message: string }).message.toLowerCase()).not.toContain('unknown');
      expect((evt as { message: string }).message.length).toBeGreaterThan(0);
    }

    const dup = mapRawEvent(
      'session_duplicated',
      { session_id: 's-copy', title: 'Copy', original_id: 's-orig' },
      'evt_dup',
    );
    expect(dup.kind).toBe('session_duplicated');
    if (dup.kind !== 'session_duplicated') return;
    expect(dup.message).toContain('s-orig');
    expect(dup.originalId).toBe('s-orig');
  });

  it('maps session_renamed and session_error with their fields', () => {
    const renamed = mapRawEvent('session_renamed', { title: 'New Name' }, 'evt_ren');
    expect(renamed.kind).toBe('session_renamed');
    if (renamed.kind !== 'session_renamed') return;
    expect(renamed.message).toContain('New Name');

    const err = mapRawEvent('session_error', { error: 'boom', error_count: 2 }, 'evt_serr');
    expect(err.kind).toBe('session_error');
    if (err.kind !== 'session_error') return;
    expect(err.error).toBe('boom');
    expect(err.message).toContain('boom');
  });

  it('maps context_updated to a typed occupancy snapshot', () => {
    const evt = mapRawEvent(
      'context_updated',
      { session_id: 's1', context_used: 50_000, context_window: 128_000, context_percent: 0.390625 },
      'evt_ctx',
    );

    expect(evt.kind).toBe('context_updated');
    if (evt.kind !== 'context_updated') return;
    expect(evt.used).toBe(50_000);
    expect(evt.total).toBe(128_000);
    expect(evt.percent).toBe(0.390625);
  });

  it('drops a malformed context_updated to the unknown default (no total)', () => {
    const evt = mapRawEvent('context_updated', { session_id: 's1', context_used: 5 }, 'evt_badctx');
    expect(evt.kind).toBe('warning');
    if (evt.kind !== 'warning') return;
    expect(evt.code).toBe('UNKNOWN_EVENT');
  });

  it('maps token_usage_recorded to provider-billed telemetry only', () => {
    const evt = mapRawEvent(
      'token_usage_recorded',
      { session_id: 's1', total_tokens: 52_316, total_cost: 0.05, added_tokens: 1_821 },
      'evt_toks',
    );

    expect(evt.kind).toBe('token_usage_recorded');
    if (evt.kind !== 'token_usage_recorded') return;
    expect(evt.totalTokens).toBe(52_316);
    expect(evt.totalCost).toBe(0.05);
    expect(evt.addedTokens).toBe(1_821);
  });

  it('keeps truly-unmapped kinds on the UNKNOWN_EVENT fallback', () => {
    // `agent_status` used to be the canonical unmapped specimen; it is now a
    // mapped sub-agent lifecycle kind (see agentOrchestrationMapper.test.ts).
    const evt = mapRawEvent('definitely_not_a_real_kind', { status: 'working' }, 'evt_unk');
    expect(evt.kind).toBe('warning');
    if (evt.kind !== 'warning') return;
    expect(evt.code).toBe('UNKNOWN_EVENT');
  });
});

describe('rawEventMapper session_status / session_summarized (QA-9.1)', () => {
  it('maps session_status to a typed status line with the run status', () => {
    const evt = mapRawEvent('session_status', { session_id: 's1', status: 'completed' }, 'evt_stat');

    expect(evt.kind).toBe('session_status');
    if (evt.kind !== 'session_status') return;
    expect(evt.message).toContain('completed');
    expect(evt.sessionId).toBe('s1');
    expect(evt.status).toBe('completed');
  });

  it('maps session_status without a status to the default label', () => {
    const evt = mapRawEvent('session_status', { session_id: 's1' }, 'evt_stat2');
    expect(evt.kind).toBe('session_status');
    if (evt.kind !== 'session_status') return;
    expect(evt.message).toBe('Session status');
  });

  it('maps session_summarized with a full run_state snapshot', () => {
    const evt = mapRawEvent(
      'session_summarized',
      {
        session_id: 's1',
        summary: 'Fixed the leak',
        run_state: {
          status: 'completed',
          mode: 'build',
          objective: 'Fix the leak',
          findings: ['Root cause was an unclosed cursor'],
          final: { kind: 'success', message: 'done', code: null },
          manifest: {
            created: ['src/fix.py'],
            modified: ['src/leak.py'],
            remaining: [],
            completed: true,
            stalled: false,
          },
          todo: [{ id: 't1', title: 'Write tests', status: 'in_progress', priority: 'high' }],
          progress: [{ label: 'Reading files', seq: 1, ts: 1.0 }],
          started_at: 1.0,
          updated_at: 2.0,
        },
        findings: ['Root cause was an unclosed cursor'],
      },
      'evt_sum',
    );

    expect(evt.kind).toBe('session_summarized');
    if (evt.kind !== 'session_summarized') return;
    expect(evt.sessionId).toBe('s1');
    expect(evt.summary).toBe('Fixed the leak');
    expect(evt.findings).toEqual(['Root cause was an unclosed cursor']);
    expect(evt.runState?.status).toBe('completed');
    expect(evt.runState?.objective).toBe('Fix the leak');
    expect(evt.runState?.final?.message).toBe('done');
    expect(evt.runState?.manifest?.created).toEqual(['src/fix.py']);
    expect(evt.runState?.manifest?.modified).toEqual(['src/leak.py']);
    expect(evt.runState?.manifest?.completed).toBe(true);
    expect(evt.runState?.todo).toEqual([{ id: 't1', title: 'Write tests', status: 'in_progress', priority: 'high' }]);
    expect(evt.runState?.progress?.[0]?.label).toBe('Reading files');
    expect(evt.runState?.startedAt).toBe(1.0);
    expect(evt.runState?.updatedAt).toBe(2.0);
  });

  it('mirrors findings from run_state when the top-level field is absent', () => {
    const evt = mapRawEvent(
      'session_summarized',
      {
        run_state: {
          status: 'failed',
          findings: ['DB locked'],
          final: { kind: 'error', message: 'boom', code: 'LOCKED' },
        },
      },
      'evt_sum2',
    );

    expect(evt.kind).toBe('session_summarized');
    if (evt.kind !== 'session_summarized') return;
    expect(evt.findings).toEqual(['DB locked']);
    expect(evt.runState?.final?.code).toBe('LOCKED');
  });

  it('maps session_summarized with only a summary (no run_state)', () => {
    const evt = mapRawEvent('session_summarized', { summary: 'plain text' }, 'evt_sum3');
    expect(evt.kind).toBe('session_summarized');
    if (evt.kind !== 'session_summarized') return;
    expect(evt.summary).toBe('plain text');
    expect(evt.runState).toBeUndefined();
  });

  it('drops an empty session_summarized payload to the unknown default', () => {
    const evt = mapRawEvent('session_summarized', { session_id: 's1' }, 'evt_sum4');
    expect(evt.kind).toBe('warning');
    if (evt.kind !== 'warning') return;
    expect(evt.code).toBe('UNKNOWN_EVENT');
  });

  it('ignores malformed run_state fields additively (no crash, no fabrication)', () => {
    const evt = mapRawEvent(
      'session_summarized',
      {
        run_state: {
          status: 'blocked',
          findings: 'not-a-list',
          manifest: { created: 'nope' },
          todo: [{ id: 't1', title: 42 }],
        },
      },
      'evt_sum5',
    );

    expect(evt.kind).toBe('session_summarized');
    if (evt.kind !== 'session_summarized') return;
    expect(evt.runState?.status).toBe('blocked');
    expect(evt.runState?.findings).toBeUndefined();
    expect(evt.runState?.manifest?.created).toBeUndefined();
    expect(evt.runState?.todo).toEqual([{ id: 't1', title: '42', status: 'todo', priority: undefined }]);
  });
});
