import type { Scenario, ScenarioMode } from '../../types/scenario';
import { wsClient } from './WebSocketClient';
import { mapEvent } from './EventMapper';
import type { ScenarioProvider, ScenarioListener, ScenarioRunner } from '../scenario/types';

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
    let partialMessageId: string | null = null;
    let accumulatedText = '';

    const unsubscribe = wsClient.onEvent((rpcEvent) => {
      if (this.abortFlag) return;

      const { kind, data } = rpcEvent.params;

      if (kind === 'message' && data?.partial === true) {
        const token = String(data.text || '');
        accumulatedText += token;

        if (partialMessageIndex === null) {
          partialMessageIndex = eventIndex;
          partialMessageId = `evt_stream_${Date.now()}`;
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
        partialMessageId = null;
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
        partialMessageId = null;
        accumulatedText = '';
        return;
      }

      const mapped = mapEvent(rpcEvent);
      onEvent(mapped, eventIndex);
      eventIndex++;

      if (kind === 'success' || kind === 'error') {
        onComplete();
      }
    });

    const statusUnsub = wsClient.onStatusChange((status) => {
      if (status === 'disconnected') {
        onEvent({
          kind: 'error',
          id: `evt_ws_error_${Date.now()}`,
          message: 'Connection to backend lost. Check that zenith serve is running.',
        }, eventIndex++);
        onComplete();
      }
    });

    const handle = setTimeout(() => {
      if (eventIndex === 0) {
        const waitingId = `evt_wait_${Date.now()}`;
        onEvent({
          kind: 'waiting',
          id: waitingId,
          message: 'Waiting for backend response...',
          duration: 2000,
        }, eventIndex++);
      }
    }, 2000);

    return {
      abort: () => {
        this.abortFlag = true;
        clearTimeout(handle);
        unsubscribe();
        statusUnsub();
      },
    };
  }
}

export const backendScenarioProvider = new BackendScenarioProvider();
