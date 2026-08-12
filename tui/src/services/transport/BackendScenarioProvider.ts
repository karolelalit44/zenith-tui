import type { Scenario, ScenarioMode } from '../../types/scenario';
import type { ScenarioListener, ScenarioProvider, ScenarioRunner } from '../scenario/types';
import { wsClient } from './WebSocketClient';

const STALE_TIMEOUT_MS = 600_000;
const RECONNECT_WAIT_MS = 20_000;

let idCounter = 0;
const uid = () => `evt_${Date.now()}_${++idCounter}`;

export class BackendScenarioProvider implements ScenarioProvider {
  readonly name = 'backend';
  private abortFlag = false;

  resolve(prompt: string, mode: ScenarioMode): Scenario {
    return {
      id: `backend_${Date.now()}`,
      mode,
      prompt,
      events: [],
    };
  }

  execute(scenario: Scenario, onEvent: ScenarioListener, onComplete: () => void): ScenarioRunner {
    this.abortFlag = false;
    let eventIndex = 0;
    let partialMessageIndex: number | null = null;
    let lastPartialMessageIndex: number | null = null;
    let partialMessageId: string | null = null;
    let accumulatedText = '';
    let completed = false;
    let timerHandle: ReturnType<typeof setTimeout> | null = null;
    let staleTimer: ReturnType<typeof setTimeout> | null = null;
    let lastEventKind: string | null = null;
    let mergedThinkingThoughts: string[] = [];
    let mergedThinkingId: string | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let disconnectEventIndex: number | null = null;

    const resetStaleTimer = () => {
      if (staleTimer) clearTimeout(staleTimer);
      staleTimer = setTimeout(() => {
        if (!completed) {
          onEvent(
            {
              kind: 'error',
              id: uid(),
              message: 'Backend response timed out. The backend may have disconnected.',
              code: 'STALE_TIMEOUT',
              recoverable: true,
            },
            eventIndex++,
          );
          finalize();
          onComplete();
        }
      }, STALE_TIMEOUT_MS);
    };

    const finalize = () => {
      if (completed) return;
      completed = true;
      if (timerHandle) {
        clearTimeout(timerHandle);
        timerHandle = null;
      }
      if (staleTimer) {
        clearTimeout(staleTimer);
        staleTimer = null;
      }
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      unsubscribe();
      statusUnsub();
    };

    const tryResumeSession = async () => {
      if (completed || !scenario.sessionId) return false;
      try {
        await wsClient.send('session.resume', { session_id: scenario.sessionId });
        if (disconnectEventIndex !== null) {
          onEvent(
            {
              kind: 'warning',
              id: uid(),
              message: 'Connection re-established, continuing...',
              code: 'RECONNECTED',
            },
            disconnectEventIndex,
          );
          disconnectEventIndex = null;
        }
        return true;
      } catch {
        return false;
      }
    };

    const handleDisconnect = () => {
      if (completed) return;
      if (disconnectEventIndex !== null) return;
      disconnectEventIndex = eventIndex++;
      onEvent(
        {
          kind: 'warning',
          id: uid(),
          message: 'Connection lost — reconnecting...',
          code: 'RECONNECTING',
        },
        disconnectEventIndex,
      );
      if (reconnectTimer) clearTimeout(reconnectTimer);
      reconnectTimer = setTimeout(async () => {
        if (completed) return;

        onEvent(
          {
            kind: 'error',
            id: uid(),
            message: 'Connection to backend lost. Check that zenith serve is running.',
          },
          disconnectEventIndex ?? eventIndex++,
        );
        disconnectEventIndex = null;
        finalize();
        onComplete();
      }, RECONNECT_WAIT_MS);
    };

    const handleReconnect = async () => {
      if (completed) return;
      if (disconnectEventIndex === null) return;
      const resumed = await tryResumeSession();
      if (resumed) {
        if (reconnectTimer) {
          clearTimeout(reconnectTimer);
          reconnectTimer = null;
        }
        resetStaleTimer();
      }
    };

    resetStaleTimer();

    const unsubscribe = wsClient.onEvent((rpcEvent) => {
      if (this.abortFlag || completed) return;

      resetStaleTimer();

      const { kind, data, id: rpcId } = rpcEvent.params;

      if (kind === 'message' && data?.partial === true) {
        const token = String(data.text || '');
        accumulatedText += token;

        const eventId = partialMessageId ?? rpcId ?? uid();
        partialMessageId = eventId;

        if (partialMessageIndex === null) {
          partialMessageIndex = eventIndex;
          lastPartialMessageIndex = eventIndex;
          eventIndex++;
        }

        lastEventKind = 'message';
        onEvent(
          {
            kind: 'message',
            id: eventId,
            text: accumulatedText,
            partial: true,
          },
          partialMessageIndex,
        );
        return;
      }

      if (kind === 'message' && !data?.partial) {
        const fullText = String(data.text || accumulatedText);

        let targetIndex: number;
        if (partialMessageIndex !== null) {
          targetIndex = partialMessageIndex;
        } else if (lastPartialMessageIndex !== null) {
          targetIndex = lastPartialMessageIndex;
        } else {
          targetIndex = eventIndex++;
        }

        lastEventKind = 'message';
        onEvent(
          {
            kind: 'message',
            id: partialMessageId ?? rpcId ?? uid(),
            text: fullText,
            partial: false,
            iteration: typeof data.iteration === 'number' ? data.iteration : undefined,
          },
          targetIndex,
        );
        partialMessageIndex = null;
        lastPartialMessageIndex = null;
        partialMessageId = null;
        accumulatedText = '';
        return;
      }

      const isTerminalEvent = (kind === 'success' && typeof data?.iterations === 'number') || kind === 'error';

      if (isTerminalEvent && partialMessageIndex !== null) {
        onEvent(
          {
            kind: 'message',
            id: partialMessageId ?? uid(),
            text: accumulatedText,
            partial: false,
          },
          partialMessageIndex,
        );
        partialMessageIndex = null;
        partialMessageId = null;
        accumulatedText = '';
      }

      const mapped = mapRawEvent(kind, data, rpcId);

      if (kind === 'thinking' && lastEventKind === 'thinking' && eventIndex > 0) {
        const newThoughts = (mapped as import('../../types/scenario').ThinkingEvent).thoughts;
        for (const t of newThoughts) {
          const text = typeof t === 'string' ? t : t.text;
          if (text) mergedThinkingThoughts.push(text);
        }

        const mergedId = mergedThinkingId ?? (mapped as import('../../types/scenario').ThinkingEvent).id;
        mergedThinkingId = mergedId;

        onEvent(
          {
            kind: 'thinking',
            id: mergedId,
            thoughts: [...mergedThinkingThoughts],
            duration: 500,
          },
          eventIndex - 1,
        );
      } else {
        if (kind !== 'thinking') {
          mergedThinkingThoughts = [];
          mergedThinkingId = null;
        } else {
          const newThoughts = (mapped as import('../../types/scenario').ThinkingEvent).thoughts;
          mergedThinkingThoughts = newThoughts
            .map((t) => (typeof t === 'string' ? t : t.text))
            .filter(Boolean) as string[];
          mergedThinkingId = (mapped as import('../../types/scenario').ThinkingEvent).id;
        }
        onEvent(mapped, eventIndex);
        eventIndex++;
      }

      lastEventKind = kind;

      let isTerminal = false;
      if (kind === 'success') {
        const hasIterations = typeof data?.iterations === 'number';
        isTerminal = hasIterations;
      } else if (kind === 'error') {
        isTerminal = true;
      }

      if (isTerminal) {
        finalize();
        onComplete();
      }
    });

    const statusUnsub = wsClient.onStatusChange((status) => {
      if (completed) return;
      if (status === 'disconnected' && disconnectEventIndex === null) {
        handleDisconnect();
      } else if (status === 'connected' && disconnectEventIndex !== null) {
        handleReconnect();
      }
    });

    timerHandle = setTimeout(() => {
      timerHandle = null;
      if (eventIndex === 0 && !completed) {
        onEvent(
          {
            kind: 'message',
            id: uid(),
            text: 'Waiting for backend response...',
            partial: false,
          },
          eventIndex++,
        );
      }
    }, 2000);

    return {
      abort: () => {
        this.abortFlag = true;
        finalize();
      },
    };
  }
}

function formatContextEventMessage(kind: string, d: Record<string, unknown>): string {
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

function mapRawEvent(
  kind: string,
  data: Record<string, unknown> | undefined,
  rpcId?: string,
): import('../../types/scenario').ScenarioEvent {
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
        iterations: typeof d.iterations === 'number' ? d.iterations : undefined,
        tokenInfo:
          d.tokenInfo && typeof d.tokenInfo === 'object'
            ? {
                used: Number((d.tokenInfo as Record<string, unknown>).used) || 0,
                remaining: Number((d.tokenInfo as Record<string, unknown>).remaining) || 0,
                total: Number((d.tokenInfo as Record<string, unknown>).total) || 0,
                percent: Number((d.tokenInfo as Record<string, unknown>).percent) || 0,
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

    default:
      return {
        kind: 'warning',
        id,
        message: `[Unknown event: ${kind}]`,
        code: 'UNKNOWN_EVENT',
      } as import('../../types/scenario').ScenarioEvent;
  }
}

export const backendScenarioProvider = new BackendScenarioProvider();
