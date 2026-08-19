import type {
  CompactionPhase,
  CompactionStatus,
  ContextPreservation,
  ContextUpdatedEvent,
  RunStateSnapshot,
  ScenarioEvent,
  SessionInfoEvent,
  SessionSummarizedEvent,
  SubtaskItem,
  TodoBoardAction,
  TodoBoardChange,
  TodoItem,
  TodoLifecyclePhase,
  TodoPriority,
  TodoStatus,
  TokenInfo,
  TokenUsageRecordedEvent,
} from '../../types/scenario';

/**
 * Shared mapping from the raw JSON-RPC wire event (kind + data) to a typed
 * ScenarioEvent. Used by BOTH the live backend stream and the local JSON
 * fixture playback, so a replayed fixture renders byte-for-byte like real
 * model output.
 */

let idCounter = 0;
export const uid = () => `evt_${Date.now()}_${++idCounter}`;

/**
 * Map the raw `success.tokenInfo` payload to the typed TokenInfo.
 *
 * Only finite numbers are accepted for the run/API telemetry fields and the
 * fields are omitted entirely when absent from the wire — legacy SUCCESS
 * events that predate `runTotal`/`windowEstimated` map to the exact same
 * shape they always did, with safe defaults for the required fields.
 */
function mapTokenInfo(value: unknown): TokenInfo | undefined {
  if (!value || typeof value !== 'object') return undefined;
  const ti = value as Record<string, unknown>;
  const finiteNumber = (v: unknown): number | undefined =>
    typeof v === 'number' && Number.isFinite(v) ? v : undefined;
  const runTotal = finiteNumber(ti.runTotal);
  const runPrompt = finiteNumber(ti.runPrompt);
  const runCompletion = finiteNumber(ti.runCompletion);
  return {
    // Context occupancy (composed messages) — drives the context gauge.
    used: Number(ti.used) || 0,
    remaining: Number(ti.remaining) || 0,
    total: Number(ti.total) || 0,
    percent: Number(ti.percent) || 0,
    // True when cumulative provider usage was unavailable (char-based estimate).
    estimated: ti.estimated === true,
    // Window/telemetry fields are optional: include only when actually present.
    ...(ti.windowEstimated === true ? { windowEstimated: true } : {}),
    ...(runTotal !== undefined ? { runTotal } : {}),
    ...(runPrompt !== undefined ? { runPrompt } : {}),
    ...(runCompletion !== undefined ? { runCompletion } : {}),
  };
}

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

const SESSION_STATUS_LABELS: Record<string, string> = {
  session_created: 'Session created',
  session_resumed: 'Session resumed',
  session_state_changed: 'Session state changed',
  session_paused: 'Session paused',
  session_renamed: 'Session renamed',
  session_error: 'Session error',
  session_status: 'Session status',
};

/**
 * Map a backend session lifecycle event into a lightweight status line. These
 * are operational signals (dim status lines), never cards. The message is
 * derived from kind + the fields the backend actually sent — never invented.
 */
export function mapSessionInfoEvent(
  kind: string,
  d: Record<string, unknown>,
  id: string,
): SessionInfoEvent | undefined {
  if (!(kind in SESSION_STATUS_LABELS)) return undefined;
  const baseLabel = SESSION_STATUS_LABELS[kind];
  const parts: string[] = [];
  if (kind === 'session_state_changed') {
    const from = d.from_state !== undefined && d.from_state !== null ? String(d.from_state) : '';
    const to = d.to_state !== undefined && d.to_state !== null ? String(d.to_state) : '';
    if (from && to) parts.push(`${from} → ${to}`);
    if (d.reason) parts.push(String(d.reason));
  } else if (kind === 'session_status' && d.status) {
    parts.push(String(d.status));
  } else if (kind === 'session_renamed' && d.title) {
    parts.push(`"${String(d.title)}"`);
  } else if (kind === 'session_error' && d.error) {
    parts.push(String(d.error));
  }
  const message = parts.length > 0 ? `${baseLabel}: ${parts.join(' · ')}` : baseLabel;
  return {
    kind: kind as SessionInfoEvent['kind'],
    id,
    sessionId: d.session_id !== undefined ? String(d.session_id) : undefined,
    message,
    fromState: d.from_state !== undefined ? String(d.from_state) : undefined,
    toState: d.to_state !== undefined ? String(d.to_state) : undefined,
    reason: d.reason !== undefined ? String(d.reason) : undefined,
    title: d.title !== undefined ? String(d.title) : undefined,
    error: d.error !== undefined ? String(d.error) : undefined,
    status: d.status !== undefined ? String(d.status) : undefined,
  };
}

function mapContextUpdatedEvent(d: Record<string, unknown>, id: string): ContextUpdatedEvent | undefined {
  const used = typeof d.context_used === 'number' ? d.context_used : undefined;
  const total = typeof d.context_window === 'number' ? d.context_window : undefined;
  if (used === undefined || total === undefined || total <= 0) return undefined;
  return {
    kind: 'context_updated',
    id,
    sessionId: d.session_id !== undefined ? String(d.session_id) : undefined,
    used,
    total,
    percent: typeof d.context_percent === 'number' ? d.context_percent : Math.round((used / total) * 100),
  };
}

function mapTokenUsageRecordedEvent(d: Record<string, unknown>, id: string): TokenUsageRecordedEvent | undefined {
  const totalTokens = typeof d.total_tokens === 'number' ? d.total_tokens : undefined;
  if (totalTokens === undefined) return undefined;
  return {
    kind: 'token_usage_recorded',
    id,
    sessionId: d.session_id !== undefined ? String(d.session_id) : undefined,
    totalTokens,
    totalCost: typeof d.total_cost === 'number' ? d.total_cost : undefined,
    addedTokens: typeof d.added_tokens === 'number' ? d.added_tokens : undefined,
    addedCost: typeof d.added_cost === 'number' ? d.added_cost : undefined,
  };
}

const _MAX_FINDINGS = 50;
const _MAX_TODO_ITEMS = 50;
const _MAX_PROGRESS = 24;

function _stringList(value: unknown, cap: number): string[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const items = value.filter((v): v is string => typeof v === 'string' && v.trim().length > 0).map((v) => v.trim());
  return items.length > 0 ? items.slice(0, cap) : undefined;
}

/**
 * Parse the backend's authoritative SessionRunState snapshot into the typed
 * shape. Only recognized fields are accepted and every field stays optional:
 * nothing is fabricated for wire payloads the backend did not produce.
 */
function mapRunState(value: unknown): RunStateSnapshot | undefined {
  if (!value || typeof value !== 'object') return undefined;
  const rs = value as Record<string, unknown>;
  const finalValue =
    rs.final && typeof rs.final === 'object'
      ? {
          kind:
            typeof (rs.final as Record<string, unknown>).kind === 'string'
              ? String((rs.final as Record<string, unknown>).kind)
              : undefined,
          message:
            typeof (rs.final as Record<string, unknown>).message === 'string'
              ? String((rs.final as Record<string, unknown>).message)
              : undefined,
          code: (rs.final as Record<string, unknown>).code,
        }
      : undefined;
  const manifestValue =
    rs.manifest && typeof rs.manifest === 'object'
      ? {
          created: _stringList((rs.manifest as Record<string, unknown>).created, 50),
          modified: _stringList((rs.manifest as Record<string, unknown>).modified, 50),
          remaining: _stringList((rs.manifest as Record<string, unknown>).remaining, 50),
          completed: (rs.manifest as Record<string, unknown>).completed === true,
          stalled: (rs.manifest as Record<string, unknown>).stalled === true,
        }
      : undefined;
  const todoValue = Array.isArray(rs.todo)
    ? rs.todo
        .filter((t): t is Record<string, unknown> => !!t && typeof t === 'object')
        .slice(0, _MAX_TODO_ITEMS)
        .map((t) => ({
          id: String(t.id || ''),
          title: String(t.title || ''),
          status: (t.status as TodoStatus) || 'todo',
          priority: typeof t.priority === 'string' ? t.priority : undefined,
        }))
    : undefined;
  const progressValue = Array.isArray(rs.progress)
    ? rs.progress
        .filter((p): p is Record<string, unknown> => !!p && typeof p === 'object')
        .slice(0, _MAX_PROGRESS)
        .map((p) => ({
          label: String(p.label || ''),
          seq: typeof p.seq === 'number' ? p.seq : undefined,
          ts: typeof p.ts === 'number' ? p.ts : undefined,
        }))
    : undefined;

  const snapshot: RunStateSnapshot = {};
  if (typeof rs.status === 'string') snapshot.status = rs.status;
  if (typeof rs.mode === 'string') snapshot.mode = rs.mode;
  if (typeof rs.objective === 'string') snapshot.objective = rs.objective;
  if (typeof rs.started_at === 'number') snapshot.startedAt = rs.started_at;
  if (typeof rs.updated_at === 'number') snapshot.updatedAt = rs.updated_at;
  if (finalValue && (finalValue.kind || finalValue.message)) snapshot.final = finalValue;
  if (manifestValue) snapshot.manifest = manifestValue;
  const findings = _stringList(rs.findings, _MAX_FINDINGS);
  if (findings) snapshot.findings = findings;
  if (todoValue && todoValue.length > 0) snapshot.todo = todoValue;
  if (progressValue && progressValue.length > 0) snapshot.progress = progressValue;
  return snapshot;
}

function mapSessionSummarizedEvent(d: Record<string, unknown>, id: string): SessionSummarizedEvent | undefined {
  const runState = mapRunState(d.run_state);
  const findings = _stringList(d.findings, _MAX_FINDINGS);
  const summary = typeof d.summary === 'string' && d.summary.trim().length > 0 ? d.summary.trim() : undefined;
  if (!runState && !findings && !summary) return undefined;
  return {
    kind: 'session_summarized',
    id,
    sessionId: d.session_id !== undefined ? String(d.session_id) : undefined,
    summary,
    findings: findings ?? runState?.findings,
    runState,
  };
}

function UnknownEvent(kind: string, id: string): ScenarioEvent {
  return {
    kind: 'warning',
    id,
    message: `[Unknown event: ${kind}]`,
    code: 'UNKNOWN_EVENT',
  } as ScenarioEvent;
}

export function mapRawEvent(kind: string, data: Record<string, unknown> | undefined, rpcId?: string): ScenarioEvent {
  const d = data || {};
  const id = rpcId || uid();

  const sessionEvent = mapSessionInfoEvent(kind, d, id);
  if (sessionEvent) return sessionEvent;

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
        tokenInfo: mapTokenInfo(d.tokenInfo),
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
        trigger: d.trigger === 'automatic' || d.trigger === 'manual' ? d.trigger : undefined,
        status: typeof d.status === 'string' ? (d.status as CompactionStatus) : undefined,
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
        trigger: d.trigger === 'automatic' || d.trigger === 'manual' ? d.trigger : undefined,
        status: typeof d.status === 'string' ? (d.status as CompactionStatus) : undefined,
      };

    case 'context_compaction_phase':
      return {
        kind: 'context_compaction_phase',
        id,
        phase: String(d.phase || 'preparing') as CompactionPhase,
        label: d.label ? String(d.label) : undefined,
        beforeTokens: typeof d.beforeTokens === 'number' ? d.beforeTokens : undefined,
        afterTokens: typeof d.afterTokens === 'number' ? d.afterTokens : undefined,
        trigger: d.trigger === 'automatic' || d.trigger === 'manual' ? d.trigger : undefined,
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

    case 'context_updated': {
      const ctx = mapContextUpdatedEvent(d, id);
      if (ctx) return ctx;
      // Payload was not a usable occupancy snapshot — degrade gracefully.
      return UnknownEvent(kind, id);
    }

    case 'token_usage_recorded': {
      const tok = mapTokenUsageRecordedEvent(d, id);
      if (tok) return tok;
      return UnknownEvent(kind, id);
    }

    case 'session_summarized': {
      const sum = mapSessionSummarizedEvent(d, id);
      if (sum) return sum;
      return UnknownEvent(kind, id);
    }

    default:
      return UnknownEvent(kind, id);
  }
}
