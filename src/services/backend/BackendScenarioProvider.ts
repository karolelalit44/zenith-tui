import type { Scenario, ScenarioMode } from '../../types/scenario';
import type { ScenarioListener, ScenarioProvider, ScenarioRunner } from '../scenario/types';
import { wsClient } from './WebSocketClient';

const STALE_TIMEOUT_MS = 600_000;

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

  execute(_scenario: Scenario, onEvent: ScenarioListener, onComplete: () => void): ScenarioRunner {
    this.abortFlag = false;
    let eventIndex = 0;
    let partialMessageIndex: number | null = null;
    let lastPartialMessageIndex: number | null = null;
    let accumulatedText = '';
    let completed = false;
    let timerHandle: ReturnType<typeof setTimeout> | null = null;
    let staleTimer: ReturnType<typeof setTimeout> | null = null;
    let lastEventKind: string | null = null;
    let mergedThinkingThoughts: string[] = [];

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
      unsubscribe();
      statusUnsub();
    };

    resetStaleTimer();

    const unsubscribe = wsClient.onEvent((rpcEvent) => {
      if (this.abortFlag || completed) return;

      resetStaleTimer();

      const { kind, data, id: rpcId } = rpcEvent.params;
      console.log(`[WS EVENT] kind=${kind} id=${rpcId} data_keys=${Object.keys(data || {})} full=`, JSON.stringify(data).slice(0, 300));

      if (kind === 'message' && data?.partial === true) {
        const token = String(data.text || '');
        accumulatedText += token;
        console.log(`[WS PARTIAL] token_len=${token.length} accumulated_len=${accumulatedText.length} preview=${token.slice(0, 100)}`);

        if (partialMessageIndex === null) {
          partialMessageIndex = eventIndex;
          lastPartialMessageIndex = eventIndex;
          eventIndex++;
        }

        lastEventKind = 'message';
        onEvent(
          {
            kind: 'message',
            id: rpcId || uid(),
            text: accumulatedText,
            partial: true,
          },
          partialMessageIndex,
        );
        return;
      }

      // Non-message events: DON'T finalize partial here.
      // The partial stays active and will be finalized when:
      // (a) the final non-partial message arrives, or
      // (b) a terminal event (success/error) arrives.
      // This prevents duplicate messages when thinking events arrive mid-stream.

      if (kind === 'message' && !data?.partial) {
        const fullText = String(data.text || accumulatedText);
        console.log(`[WS FINAL MSG] fullText_len=${fullText.length} preview=${fullText.slice(0, 200)}`);

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
            id: rpcId || uid(),
            text: fullText,
            partial: false,
          },
          targetIndex,
        );
        partialMessageIndex = null;
        lastPartialMessageIndex = null;
        accumulatedText = '';
        return;
      }

      // Terminal events: finalize any pending partial before emitting
      const isTerminalEvent =
        (kind === 'success' && typeof data?.iterations === 'number') ||
        (kind === 'error' && !(data && typeof data === 'object' && data.recoverable === true));

      if (isTerminalEvent && partialMessageIndex !== null) {
        onEvent(
          {
            kind: 'message',
            id: uid(),
            text: accumulatedText,
            partial: false,
          },
          partialMessageIndex,
        );
        partialMessageIndex = null;
        accumulatedText = '';
      }

      const mapped = mapRawEvent(kind, data, rpcId);
      console.log(`[WS MAPPED] kind=${kind} mapped_kind=${mapped.kind} id=${mapped.id}`);

      // Merge consecutive thinking events into a single block
      if (kind === 'thinking' && lastEventKind === 'thinking' && eventIndex > 0) {
        // Accumulate thoughts from new event into the merged array
        const newThoughts = (mapped as import('../../types/scenario').ThinkingEvent).thoughts;
        for (const t of newThoughts) {
          const text = typeof t === 'string' ? t : t.text;
          if (text) mergedThinkingThoughts.push(text);
        }
        // Replace previous thinking event with merged version
        onEvent(
          {
            kind: 'thinking',
            id: uid(),
            thoughts: [...mergedThinkingThoughts],
            duration: 500,
          },
          eventIndex - 1, // Replace previous thinking event
        );
      } else {
        // Reset merge tracking when a non-thinking event arrives
        if (kind !== 'thinking') {
          mergedThinkingThoughts = [];
        } else {
          // First thinking event in a new sequence
          const newThoughts = (mapped as import('../../types/scenario').ThinkingEvent).thoughts;
          mergedThinkingThoughts = newThoughts
            .map((t) => (typeof t === 'string' ? t : t.text))
            .filter(Boolean) as string[];
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
        isTerminal = !(data && typeof data === 'object' && data.recoverable === true);
      }

      if (isTerminal) {
        console.log(`[WS TERMINAL] kind=${kind} - finalizing and calling onComplete`);
        finalize();
        onComplete();
      }
    });

    const statusUnsub = wsClient.onStatusChange((status) => {
      if (status === 'disconnected' && !completed) {
        onEvent(
          {
            kind: 'error',
            id: uid(),
            message: 'Connection to backend lost. Check that zenith serve is running.',
          },
          eventIndex++,
        );
        finalize();
        onComplete();
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

    case 'confirmation_request':
      return {
        kind: 'confirmation_request',
        id,
        confirmationId: String(d.confirmation_id || ''),
        tool: String(d.tool || ''),
        reason: String(d.reason || ''),
        riskLevel: String(d.risk_level || 'medium'),
        message: String(d.message || 'Operation requires confirmation'),
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
