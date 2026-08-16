import type {
  CompactionPhase,
  ContextPreservation,
  ScenarioEvent,
  SubtaskItem,
  TodoBoardAction,
  TodoBoardChange,
  TodoItem,
  TodoLifecyclePhase,
  TodoPriority,
  TodoStatus,
} from '../../types/scenario';

/**
 * Shared mapping from the raw JSON-RPC wire event (kind + data) to a typed
 * ScenarioEvent. Used by BOTH the live backend stream and the local JSON
 * fixture playback, so a replayed fixture renders byte-for-byte like real
 * model output.
 */

let idCounter = 0;
export const uid = () => `evt_${Date.now()}_${++idCounter}`;

export function formatContextEventMessage(kind: string, d: Record<string, unknown>): string {
  const reason = d.reason ? String(d.reason) : 'context pressure';
  const tokensSaved = typeof d.tokensSaved === 'number' ? d.tokensSaved : 0;
  if (kind === 'context_compacted') {
    const charsRemoved = typeof d.charsRemoved === 'number' ? d.charsRemoved : 0;
    const tool = d.tool ? String(d.tool) : 'output';
    return `Compacted ${tool} output: removed ${charsRemoved} chars, saved ~${tokensSaved} tokens — ${reason}`;
  }
  const used = typeof d.used === 'number' ? d.used : 0;
  const total = typeof d.total === 'number' ? d.total : 0;
  const pct = total > 0 ? ` (${Math.round((used / total) * 100)}%)` : '';
  const verb = kind === 'context_compaction_started' ? 'started' : 'finished';
  const saved = tokensSaved > 0 ? `, saved ~${tokensSaved} tokens` : '';
  return `Context compaction ${verb}: ${used}/${total} tokens${pct}${saved} — ${reason}`;
}

export function mapRawEvent(kind: string, data: Record<string, unknown> | undefined, rpcId?: string): ScenarioEvent {
  const d = data || {};
  const id = rpcId || uid();

  switch (kind) {
    case 'thinking':
      return {
        kind: 'thinking',
        id,
        thoughts: d.text ? [String(d.text)] : [],
        duration: typeof d.duration === 'number' ? d.duration : 500,
      };

    case 'message':
      return {
        kind: 'message',
        id,
        text: String(d.text || ''),
        partial: d.partial === true,
        iteration: typeof d.iteration === 'number' ? d.iteration : undefined,
      };

    case 'tool_call':
      return {
        kind: 'tool_call',
        id,
        tool: String(d.tool || ''),
        params: (d.params && typeof d.params === 'object' ? d.params : {}) as Record<string, unknown>,
        text: d.text ? String(d.text) : undefined,
      };

    case 'tool_result':
      return {
        kind: 'tool_result',
        id,
        tool: String(d.tool || ''),
        success: Boolean(d.success),
        output: String(d.output || ''),
        error: String(d.error || ''),
        truncated: d.truncated === true,
        metadata: (d.metadata && typeof d.metadata === 'object' ? d.metadata : {}) as Record<string, unknown>,
      };

    case 'error':
      return {
        kind: 'error',
        id,
        message: String(d.message || 'An error occurred'),
        code: d.code ? String(d.code) : undefined,
        recoverable: typeof d.recoverable === 'boolean' ? d.recoverable : undefined,
        provider: d.provider ? String(d.provider) : undefined,
        action: d.action ? String(d.action) : undefined,
        hint: d.hint ? String(d.hint) : undefined,
      };

    case 'warning':
      return {
        kind: 'warning',
        id,
        message: String(d.message || ''),
        code: d.code ? String(d.code) : undefined,
      };

    case 'success':
      return {
        kind: 'success',
        id,
        message: String(d.message || 'Completed'),
        iterations:
          typeof d.iterations === 'number' ? d.iterations : typeof d.iteration === 'number' ? d.iteration : undefined,
        elapsedMs:
          typeof d.elapsedMs === 'number' ? d.elapsedMs : typeof d.duration === 'number' ? d.duration : undefined,
        tokenInfo:
          d.tokenInfo && typeof d.tokenInfo === 'object'
            ? {
                used: Number((d.tokenInfo as Record<string, unknown>).used) || 0,
                remaining: Number((d.tokenInfo as Record<string, unknown>).remaining) || 0,
                total: Number((d.tokenInfo as Record<string, unknown>).total) || 0,
                percent: Number((d.tokenInfo as Record<string, unknown>).percent) || 0,
                estimated: (d.tokenInfo as Record<string, unknown>).estimated === true,
              }
            : undefined,
      };

    case 'progress':
      return {
        kind: 'progress',
        id,
        label: String(d.label || d.status || 'Progress'),
        percent: typeof d.percent === 'number' ? d.percent : undefined,
        iteration: typeof d.iteration === 'number' ? d.iteration : undefined,
        steps: Array.isArray(d.steps)
          ? (d.steps as { label: string; status: 'pending' | 'active' | 'done' | 'error' }[])
          : [],
      };

    case 'plan_ready':
      return {
        kind: 'plan_ready',
        id,
        plan: String(d.plan || ''),
        sessionId: String(d.session_id || ''),
      };

    case 'agent_orchestration':
      return {
        kind: 'agent_orchestration',
        id,
        stage: (d.stage as any) || 'working',
        captainMessage: String(d.captainMessage || d.message || ''),
        plan: Array.isArray(d.plan) ? (d.plan as any) : undefined,
        crewmates: Array.isArray(d.crewmates) ? (d.crewmates as any) : undefined,
        timeline: Array.isArray(d.timeline) ? (d.timeline as any) : undefined,
        activeStep: d.activeStep ? String(d.activeStep) : undefined,
      };

    case 'context_compacted':
      return {
        kind: 'context_compacted',
        id,
        message: formatContextEventMessage('context_compacted', d),
        tool: d.tool ? String(d.tool) : undefined,
        tokensSaved: typeof d.tokensSaved === 'number' ? d.tokensSaved : undefined,
      };

    case 'context_compaction_started':
      return {
        kind: 'context_compaction_started',
        id,
        message: formatContextEventMessage('context_compaction_started', d),
        used: typeof d.used === 'number' ? d.used : undefined,
        total: typeof d.total === 'number' ? d.total : undefined,
      };

    case 'context_compaction_ended':
      return {
        kind: 'context_compaction_ended',
        id,
        message: formatContextEventMessage('context_compaction_ended', d),
        tokensSaved: typeof d.tokensSaved === 'number' ? d.tokensSaved : undefined,
        summaryChars: typeof d.summaryChars === 'number' ? d.summaryChars : undefined,
        used: typeof d.used === 'number' ? d.used : undefined,
        total: typeof d.total === 'number' ? d.total : undefined,
        preserved: d.preserved && typeof d.preserved === 'object' ? (d.preserved as ContextPreservation) : undefined,
        summary: d.summary ? String(d.summary) : undefined,
        failed: typeof d.failed === 'boolean' ? d.failed : undefined,
      };

    case 'context_compaction_phase':
      return {
        kind: 'context_compaction_phase',
        id,
        phase: String(d.phase || 'preparing') as CompactionPhase,
        label: d.label ? String(d.label) : undefined,
        beforeTokens: typeof d.beforeTokens === 'number' ? d.beforeTokens : undefined,
        afterTokens: typeof d.afterTokens === 'number' ? d.afterTokens : undefined,
      };

    case 'turn_manifest':
      return {
        kind: 'turn_manifest',
        id,
        created: Array.isArray(d.created) ? d.created.map(String) : [],
        modified: Array.isArray(d.modified) ? d.modified.map(String) : [],
        remaining: Array.isArray(d.remaining) ? d.remaining.map(String) : [],
        completed: d.completed === true,
        stalled: d.stalled === true,
        files: Array.isArray(d.files)
          ? d.files.map((f: Record<string, unknown>) => ({
              path: String(f.path || ''),
              exists: f.exists === true,
              size: typeof f.size === 'number' ? f.size : 0,
            }))
          : [],
      };

    case 'todo_board':
      return {
        kind: 'todo_board',
        id,
        action: (d.action as TodoBoardAction) || 'snapshot',
        board: Array.isArray(d.board)
          ? d.board.map(
              (item: Record<string, unknown>): TodoItem => ({
                id: String(item.id || ''),
                title: String(item.title || ''),
                status: (item.status as TodoStatus) || 'todo',
                priority: (item.priority as TodoPriority) || 'medium',
                assignee: item.assignee ? String(item.assignee) : undefined,
                labels: Array.isArray(item.labels) ? item.labels.map(String) : undefined,
                dueDate: item.dueDate ? String(item.dueDate) : undefined,
                createdAt: typeof item.createdAt === 'number' ? item.createdAt : Date.now(),
                updatedAt: typeof item.updatedAt === 'number' ? item.updatedAt : Date.now(),
                subtasks: Array.isArray(item.subtasks)
                  ? item.subtasks.map(
                      (st: Record<string, unknown>): SubtaskItem => ({
                        id: String(st.id || ''),
                        title: String(st.title || ''),
                        status: (st.status as TodoStatus) || 'todo',
                        assignee: st.assignee ? String(st.assignee) : undefined,
                        note: st.note ? String(st.note) : undefined,
                      }),
                    )
                  : [],
              }),
            )
          : [],
        change: d.change && typeof d.change === 'object' ? (d.change as TodoBoardChange) : undefined,
        message: d.message ? String(d.message) : undefined,
      };

    case 'todo_test':
      return {
        kind: 'todo_test',
        id,
        phase: String(d.phase || 'create') as TodoLifecyclePhase,
        scenario: String(d.scenario || 'Scenario'),
        passed: d.passed === true,
        assertions: Array.isArray(d.assertions)
          ? d.assertions.map((a: Record<string, unknown>) => ({
              label: String(a.label || ''),
              passed: a.passed === true,
              detail: a.detail ? String(a.detail) : undefined,
            }))
          : [],
        rejectedOps: Array.isArray(d.rejectedOps)
          ? d.rejectedOps.map((r: Record<string, unknown>) => ({
              op: String(r.op || ''),
              reason: String(r.reason || ''),
            }))
          : undefined,
        elapsedMs: typeof d.elapsedMs === 'number' ? d.elapsedMs : undefined,
      };

    default:
      return {
        kind: 'warning',
        id,
        message: `[Unknown event: ${kind}]`,
        code: 'UNKNOWN_EVENT',
      } as ScenarioEvent;
  }
}
