import { appConfig } from '../../config/appConfig';
import { BACKEND_RESPONSE_PLACEHOLDER_DELAY_MS, BACKEND_RESPONSE_PLACEHOLDER_LABEL } from '../../constants/events';
import type { Scenario, ScenarioListener, ScenarioMode, ScenarioProvider, ScenarioRunner } from '../../types/scenario';
import { mapRawEvent, uid } from './rawEventMapper';
import { type WebSocketClient, wsClient } from './WebSocketClient';

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
      }, appConfig.ws.staleTimeoutMs);
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
      }, appConfig.ws.reconnectWaitMs);
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

      const isTerminalEvent = (kind === 'success' && !data?.tool) || kind === 'error';

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
        const thinkingEv = mapped as import('../../types/scenario').ThinkingEvent;
        const newThoughts = thinkingEv.thoughts;
        mergedThinkingThoughts = newThoughts
          .map((t) => (typeof t === 'string' ? t : t.text))
          .filter(Boolean) as string[];

        const mergedId = mergedThinkingId ?? thinkingEv.id;
        mergedThinkingId = mergedId;

        onEvent(
          {
            kind: 'thinking',
            id: mergedId,
            thoughts: [...mergedThinkingThoughts],
            duration: thinkingEv.duration || 0,
            partial: thinkingEv.partial,
          },
          eventIndex - 1,
        );
      } else {
        if (kind !== 'thinking') {
          mergedThinkingThoughts = [];
          mergedThinkingId = null;
        } else {
          const thinkingEv = mapped as import('../../types/scenario').ThinkingEvent;
          const newThoughts = thinkingEv.thoughts;
          mergedThinkingThoughts = newThoughts
            .map((t) => (typeof t === 'string' ? t : t.text))
            .filter(Boolean) as string[];
          mergedThinkingId = thinkingEv.id;
        }
        onEvent(mapped, eventIndex);
        eventIndex++;
      }

      lastEventKind = kind;

      const isTerminal = (kind === 'success' && !data?.tool) || kind === 'error';

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
        // Live-only progress row instead of a permanent message: progress
        // events are stripped from scrollback once the turn completes, so
        // this latency indicator never pollutes history.
        onEvent(
          {
            kind: 'progress',
            id: uid(),
            label: BACKEND_RESPONSE_PLACEHOLDER_LABEL,
            steps: [],
          },
          eventIndex++,
        );
      }
    }, BACKEND_RESPONSE_PLACEHOLDER_DELAY_MS);

    return {
      abort: () => {
        this.abortFlag = true;
        finalize();
      },
    };
  }

  executeCompaction(
    sessionId: string,
    onEvent: ScenarioListener,
    onComplete: () => void,
    client: WebSocketClient = wsClient,
  ): ScenarioRunner {
    const COMPACTION_EVENT_KINDS = new Set([
      'context_compaction_started',
      'context_compaction_phase',
      'context_compacted',
      'context_compaction_ended',
    ]);

    let eventIndex = 0;
    let completed = false;

    const unsubscribe = client.onEvent((rpcEvent) => {
      if (completed) return;
      const { kind, data, id: rpcId } = rpcEvent.params;
      if (COMPACTION_EVENT_KINDS.has(kind)) {
        onEvent(mapRawEvent(kind, data, rpcId), eventIndex++);
        if (kind === 'context_compaction_ended') {
          completed = true;
          unsubscribe();
          onComplete();
        }
      }
    });

    client.contextCompact(sessionId).then(
      () => {
        if (!completed) {
          completed = true;
          unsubscribe();
          onComplete();
        }
      },
      (err) => {
        if (completed) return;
        completed = true;
        unsubscribe();
        onEvent(
          {
            kind: 'error',
            id: uid(),
            message: err instanceof Error ? err.message : String(err),
          },
          eventIndex++,
        );
        onComplete();
      },
    );

    return {
      abort: () => {
        completed = true;
        unsubscribe();
      },
    };
  }
}

export const backendScenarioProvider = new BackendScenarioProvider();
