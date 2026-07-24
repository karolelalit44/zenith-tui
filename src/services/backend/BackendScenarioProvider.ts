import type { Scenario, ScenarioMode } from '../../types/scenario';
import type { ScenarioListener, ScenarioProvider, ScenarioRunner } from '../scenario/types';
import { mapEvent } from './EventMapper';
import { wsClient } from './WebSocketClient';

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
    let accumulatedText = '';
    let completed = false;
    let timerHandle: ReturnType<typeof setTimeout> | null = null;

    const finalize = () => {
      if (completed) return;
      completed = true;
      if (timerHandle) {
        clearTimeout(timerHandle);
        timerHandle = null;
      }
      unsubscribe();
      statusUnsub();
    };

    const unsubscribe = wsClient.onEvent((rpcEvent) => {
      if (this.abortFlag || completed) return;

      const { kind, data } = rpcEvent.params;

      if (kind === 'message' && data?.partial === true) {
        const token = String(data.text || '');
        accumulatedText += token;

        if (partialMessageIndex === null) {
          partialMessageIndex = eventIndex;
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
        const targetIndex = partialMessageIndex !== null ? partialMessageIndex : eventIndex++;
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
        accumulatedText = '';
        return;
      }

      const mapped = mapEvent(rpcEvent);
      onEvent(mapped, eventIndex);
      eventIndex++;

      // Only complete on terminal events: success, error, or thinking (stream start)
      if (kind === 'success' || kind === 'error') {
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
