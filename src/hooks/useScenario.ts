import { useCallback, useEffect, useRef, useState } from 'react';
import { backendScenarioProvider } from '../services/backend/BackendScenarioProvider';
import { wsClient } from '../services/backend/WebSocketClient';
import type { ScenarioRunner } from '../services/scenario/types';
import type { ConfirmationRequestEvent, ScenarioEvent, ScenarioMode } from '../types/scenario';

export interface UseScenarioReturn {
  events: ScenarioEvent[];
  isRunning: boolean;
  startScenario: (prompt: string, mode: ScenarioMode) => void;
  abort: () => void;
  activeConfirmation: ConfirmationRequestEvent | null;
  respondConfirmation: (approved: boolean) => void;
}

export function useScenario(): UseScenarioReturn {
  const resolvedProvider = backendScenarioProvider;
  const [events, setEvents] = useState<ScenarioEvent[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [activeConfirmation, setActiveConfirmation] = useState<ConfirmationRequestEvent | null>(null);
  const runnerRef = useRef<ScenarioRunner | null>(null);
  const sessionIdRef = useRef<string | null>(null);

  useEffect(() => {
    wsClient.connect().catch(() => {});
  }, []);

  const startScenario = useCallback(
    async (prompt: string, selectedMode: ScenarioMode) => {
      setEvents([]);
      setIsRunning(true);

      try {
        await wsClient.connect();
      } catch (err) {
        setEvents([
          {
            kind: 'error',
            id: `evt_conn_${Date.now()}`,
            message: 'Cannot connect to backend. Run: zenith serve',
            code: 'CONNECTION_FAILED',
          },
        ]);
        setIsRunning(false);
        return;
      }

      let sessionId = sessionIdRef.current;
      if (!sessionId) {
        try {
          const session = await wsClient.createSession(prompt.slice(0, 50));
          sessionId = (session as { id: string }).id;
          sessionIdRef.current = sessionId;
        } catch {
          setEvents([
            {
              kind: 'error',
              id: `evt_sess_${Date.now()}`,
              message: 'Failed to create session',
            },
          ]);
          setIsRunning(false);
          return;
        }
      }

      const scenario = resolvedProvider.resolve(prompt, selectedMode);

      runnerRef.current = resolvedProvider.execute(
        scenario,
        (event, index) => {
          setEvents((prev) => {
            if (typeof index === 'number' && index < prev.length) {
              const updated = [...prev];
              updated[index] = event;
              return updated;
            }
            return [...prev, event];
          });
          // Track active confirmation events
          if (event.kind === 'confirmation_request') {
            const conf = event as ConfirmationRequestEvent;
            if (!conf.answered) {
              setActiveConfirmation(conf);
            } else {
              setActiveConfirmation(null);
            }
          }
        },
        () => {
          setIsRunning(false);
          setActiveConfirmation(null);
        },
      );

      wsClient.sendPrompt(prompt, selectedMode, sessionId).catch((err) => {
        const message = err instanceof Error ? err.message : String(err);
        setEvents((prev) => [
          ...prev,
          {
            kind: 'error',
            id: `evt_prompt_err_${Date.now()}`,
            message: `Backend prompt error: ${message}`,
          },
        ]);
        setIsRunning(false);
      });
    },
    [resolvedProvider],
  );

  const abort = useCallback(() => {
    runnerRef.current?.abort();
    setIsRunning(false);
    setActiveConfirmation(null);
  }, []);

  const respondConfirmation = useCallback(
    async (approved: boolean) => {
      const conf = activeConfirmation;
      if (!conf || !conf.confirmationId) return;

      // Send response to backend
      wsClient.sendConfirmation(conf.confirmationId, approved).catch(() => {});

      // Update the event in the list to show answered state
      setEvents((prev) =>
        prev.map((e) =>
          e.kind === 'confirmation_request' &&
          (e as ConfirmationRequestEvent).confirmationId === conf.confirmationId
            ? { ...e, answered: true, approved } as ConfirmationRequestEvent
            : e,
        ),
      );

      setActiveConfirmation(null);
    },
    [activeConfirmation],
  );

  return {
    events,
    isRunning,
    startScenario,
    abort,
    activeConfirmation,
    respondConfirmation,
  };
}
