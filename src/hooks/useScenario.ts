import { useCallback, useEffect, useRef, useState } from 'react';
import { backendScenarioProvider } from '../services/backend/BackendScenarioProvider';
import { wsClient } from '../services/backend/WebSocketClient';
import { eventBus } from '../services/eventBus';
import type { ScenarioRunner } from '../services/scenario/types';
import type { ConfirmationRequestEvent, ScenarioEvent, ScenarioMode } from '../types/scenario';

const SESSION_STORAGE_KEY = 'zenith_session_id';

export interface UseScenarioReturn {
  events: ScenarioEvent[];
  isRunning: boolean;
  startScenario: (prompt: string, mode: ScenarioMode, provider?: string) => void;
  abort: () => void;
  activeConfirmation: ConfirmationRequestEvent | null;
  respondConfirmation: (approved: boolean) => void;
  lastSessionId: string | null;
}

export function useScenario(): UseScenarioReturn {
  const [events, setEvents] = useState<ScenarioEvent[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [activeConfirmation, setActiveConfirmation] = useState<ConfirmationRequestEvent | null>(null);
  const [lastSessionId, setLastSessionId] = useState<string | null>(null);
  const runnerRef = useRef<ScenarioRunner | null>(null);
  const sessionIdRef = useRef<string | null>(null);

  // Restore session ID from localStorage on mount
  useEffect(() => {
    try {
      const savedId = localStorage.getItem(SESSION_STORAGE_KEY);
      if (savedId) {
        sessionIdRef.current = savedId;
        setLastSessionId(savedId);
      }
    } catch {
      // localStorage not available (test environment)
    }
  }, []);

  useEffect(() => {
    wsClient.connect().catch(() => {});
  }, []);

  const handleEvent = useCallback((event: ScenarioEvent, index: number) => {
    console.log(`[SCENARIO EVENT] kind=${event.kind} id=${event.id} index=${index}`);
    setEvents((prev) => {
      if (typeof index === 'number' && index < prev.length) {
        console.log(`[SCENARIO UPDATE] replacing event at index ${index} (prev_kind=${prev[index]?.kind})`);
        const updated = [...prev];
        updated[index] = event;
        return updated;
      }
      console.log(`[SCENARIO APPEND] adding new event (total=${prev.length + 1})`);
      return [...prev, event];
    });
    if (event.kind === 'confirmation_request') {
      const conf = event as ConfirmationRequestEvent;
      setActiveConfirmation(conf.answered ? null : conf);
    }
  }, []);

  const handleComplete = useCallback(() => {
    setIsRunning(false);
    setActiveConfirmation(null);
  }, []);

  const createSession = useCallback(async (prompt: string) => {
    const session = await wsClient.createSession(prompt.slice(0, 50));
    const id = (session as { id: string }).id;
    sessionIdRef.current = id;
    setLastSessionId(id);
    try {
      localStorage.setItem(SESSION_STORAGE_KEY, id);
    } catch {
      /* noop */
    }
    return id;
  }, []);

  const connectToBackend = useCallback(async () => {
    await wsClient.connect();
  }, []);

  const reportError = useCallback((id: string, message: string) => {
    setEvents([{ kind: 'error', id: `evt_${id}_${Date.now()}`, message }]);
    setIsRunning(false);
  }, []);

  const startScenario = useCallback(
    async (prompt: string, selectedMode: ScenarioMode, provider?: string) => {
      setEvents([]);
      setIsRunning(true);

      try {
        await connectToBackend();
      } catch {
        reportError('conn', 'Cannot connect to backend. Run: zenith serve');
        return;
      }

      try {
        if (sessionIdRef.current) {
          // Verify saved session still exists on backend
          try {
            await wsClient.send('session.resume', { session_id: sessionIdRef.current });
          } catch {
            // Session no longer exists — create a new one
            sessionIdRef.current = null;
            try {
              localStorage.removeItem(SESSION_STORAGE_KEY);
            } catch {
              /* noop */
            }
          }
        }
        if (!sessionIdRef.current) await createSession(prompt);
      } catch {
        reportError('sess', 'Failed to create session');
        return;
      }

      const scenario = backendScenarioProvider.resolve(prompt, selectedMode);
      runnerRef.current = backendScenarioProvider.execute(scenario, handleEvent, handleComplete);

      wsClient.sendPrompt(prompt, selectedMode, sessionIdRef.current ?? undefined, provider).catch((err) => {
        const message = err instanceof Error ? err.message : String(err);
        reportError('prompt_err', `Backend prompt error: ${message}`);
      });
    },
    [connectToBackend, createSession, handleEvent, handleComplete, reportError],
  );

  const abort = useCallback(() => {
    runnerRef.current?.abort();
    setIsRunning(false);
    setActiveConfirmation(null);
  }, []);

  const respondConfirmation = useCallback(
    async (approved: boolean) => {
      const conf = activeConfirmation;
      if (!conf?.confirmationId) return;

      wsClient.sendConfirmation(conf.confirmationId, approved).catch(() => {});
      eventBus.emit('confirmation:response', { confirmationId: conf.confirmationId, approved });

      setEvents((prev) =>
        prev.map((e) =>
          e.kind === 'confirmation_request' && (e as ConfirmationRequestEvent).confirmationId === conf.confirmationId
            ? ({ ...e, answered: true, approved } as ConfirmationRequestEvent)
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
    lastSessionId,
  };
}
