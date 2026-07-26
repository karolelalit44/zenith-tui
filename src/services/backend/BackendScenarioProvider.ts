import type { Scenario, ScenarioMode } from '../../types/scenario';
import type { ScenarioListener, ScenarioProvider, ScenarioRunner } from '../scenario/types';
import { mapEvent } from './EventMapper';
import { wsClient } from './WebSocketClient';

/** Timeout (ms) after which the frontend auto-finalizes if no events arrive. */
const STALE_TIMEOUT_MS = 300_000;


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
    /** Tracks the last slot used for a partial message — survives resets from non-message events. */
    let lastPartialMessageIndex: number | null = null;
    let accumulatedText = '';
    let completed = false;
    let timerHandle: ReturnType<typeof setTimeout> | null = null;
    let staleTimer: ReturnType<typeof setTimeout> | null = null;

    const resetStaleTimer = () => {
      if (staleTimer) clearTimeout(staleTimer);
      staleTimer = setTimeout(() => {
        if (!completed) {
          onEvent(
            {
              kind: 'error',
              id: `evt_stale_${Date.now()}`,
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

    // Start the stale-event safety net
    resetStaleTimer();

    const unsubscribe = wsClient.onEvent((rpcEvent) => {
      if (this.abortFlag || completed) return;

      // Any event resets the stale timer
      resetStaleTimer();

      const { kind, data } = rpcEvent.params;

      if (kind === 'message' && data?.partial === true) {
        const token = String(data.text || '');
        accumulatedText += token;

        if (partialMessageIndex === null) {
          partialMessageIndex = eventIndex;
          lastPartialMessageIndex = eventIndex;
          eventIndex++;
        }

        const partialEvent = mapEvent({
          ...rpcEvent,
          params: {
            ...rpcEvent.params,
            data: {
              ...data,
              text: accumulatedText,
            },
          },
        });

        onEvent(partialEvent, partialMessageIndex);
        return;
      }

      // If a non-message event arrives while streaming a partial message, finalize the message item first
      if (kind !== 'message' && partialMessageIndex !== null) {
        const finalEvent = mapEvent({
          jsonrpc: '2.0' as const,
          method: 'event' as const,
          params: {
            kind: 'message',
            id: `evt_final_${Date.now()}`,
            data: { text: accumulatedText, partial: false },
          },
        });
        onEvent(finalEvent, partialMessageIndex);
        partialMessageIndex = null;
        accumulatedText = '';
      }

      if (kind === 'message' && !data?.partial) {
        const fullText = String(data.text || accumulatedText);

        // Determine target index: prefer active partial, then the last known partial slot,
        // otherwise allocate a new slot.
        let targetIndex: number;
        if (partialMessageIndex !== null) {
          targetIndex = partialMessageIndex;
        } else if (lastPartialMessageIndex !== null && accumulatedText) {
          // The partial was already finalized by a non-message event,
          // but this is the cleaned replacement — reuse the same slot.
          targetIndex = lastPartialMessageIndex;
        } else {
          targetIndex = eventIndex++;
        }

        const finalEvent = mapEvent({
          ...rpcEvent,
          params: {
            ...rpcEvent.params,
            data: {
              ...data,
              text: fullText,
            },
          },
        });
        onEvent(finalEvent, targetIndex);
        partialMessageIndex = null;
        lastPartialMessageIndex = null;
        accumulatedText = '';
        return;
      }

      const mapped = mapEvent(rpcEvent);
      onEvent(mapped, eventIndex);
      eventIndex++;

      // Only complete on terminal events (final prompt success or fatal unrecoverable error)
      let isTerminal = false;
      if (kind === 'success') {
        // Intermediate tool results contain 'tool' and 'result' fields.
        // Final prompt success contains 'iterations', 'tokenInfo', or 'message'.
        const isToolResult = Boolean(data && typeof data === 'object' && data.tool && data.result);
        isTerminal = !isToolResult;
      } else if (kind === 'error') {
        // Recoverable tool errors (recoverable: true) are intermediate — the backend agent loop continues to next turn.
        const isRecoverable = Boolean(data && typeof data === 'object' && data.recoverable === true);
        isTerminal = !isRecoverable;
      }

      if (isTerminal) {
        finalize();
        onComplete();
      }
    });

    const statusUnsub = wsClient.onStatusChange((status) => {
      if (status === 'disconnected' && !completed) {
        onEvent(
          {
            kind: 'error',
            id: `evt_ws_error_${Date.now()}`,
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
        const waitingId = `evt_wait_${Date.now()}`;
        onEvent(
          {
            kind: 'waiting',
            id: waitingId,
            message: 'Waiting for backend response...',
            duration: 2000,
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

export const backendScenarioProvider = new BackendScenarioProvider();
