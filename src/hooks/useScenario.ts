import { useCallback, useEffect, useRef, useState } from 'react';
import { backendScenarioProvider } from '../services/backend/BackendScenarioProvider';
import { wsClient } from '../services/backend/WebSocketClient';
import type { ScenarioProvider, ScenarioRunner } from '../services/scenario/types';
import type { ScenarioEvent, ScenarioMode } from '../types/scenario';

export interface UseScenarioReturn {
  events: ScenarioEvent[];
  isRunning: boolean;
  startScenario: (prompt: string, mode: ScenarioMode) => void;
  abort: () => void;
}

export function useScenario(provider?: ScenarioProvider): UseScenarioReturn {
  const resolvedProvider = provider ?? backendScenarioProvider;
  const [events, setEvents] = useState<ScenarioEvent[]>([]);
  const [isRunning, setIsRunning] = useState(false);
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
        const _reason = err instanceof Error ? err.message : String(err);
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
        },
        () => {
          setIsRunning(false);
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
  }, []);

  return {
    events,
    isRunning,
    startScenario,
    abort,
  };
}
