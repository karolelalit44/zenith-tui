import React, { useCallback, useEffect, useRef, useState } from 'react';
import { eventBus } from '../services/eventBus';
import type { ScenarioRunner } from '../services/scenario/types';
import { backendScenarioProvider } from '../services/transport/BackendScenarioProvider';
import { wsClient } from '../services/transport/WebSocketClient';
import type { ConfirmationRequestEvent, Scenario, ScenarioEvent, ScenarioMode } from '../types/scenario';

export interface UseScenarioReturn {
  events: ScenarioEvent[];
  eventsRef: React.MutableRefObject<ScenarioEvent[]>;
  isRunning: boolean;
  startScenario: (prompt: string, mode: ScenarioMode, provider?: string) => void;
  abort: () => void;
  activeConfirmation: ConfirmationRequestEvent | null;
  respondConfirmation: (approved: boolean) => void;
  lastSessionId: string | null;
}

export function useScenario(): UseScenarioReturn {
  const [events, setEvents] = useState<ScenarioEvent[]>([]);
  const eventsRef = useRef<ScenarioEvent[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [activeConfirmation, setActiveConfirmation] = useState<ConfirmationRequestEvent | null>(null);
  const [lastSessionId, setLastSessionId] = useState<string | null>(null);
  const runnerRef = useRef<ScenarioRunner | null>(null);
  const sessionIdRef = useRef<string | null>(null);

  useEffect(() => {
    wsClient.connect().catch(() => {});
  }, []);

  const batchQueueRef = useRef<{ event: ScenarioEvent; index: number }[]>([]);
  const batchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const flushBatch = useCallback(() => {
    if (batchQueueRef.current.length === 0) return;
    const queue = [...batchQueueRef.current];
    batchQueueRef.current = [];

    setEvents((prev) => {
      const next = [...prev];
      const existingIds = new Set(prev.map((e) => e.id));

      for (const { event, index } of queue) {
        // Deduplication: skip if event with same ID already exists
        if (event.id && existingIds.has(event.id)) {
          continue;
        }

        if (typeof index === 'number' && index < next.length) {
          next[index] = event;
        } else {
          next.push(event);
        }
        if (event.id) {
          existingIds.add(event.id);
        }
      }
      eventsRef.current = next;
      return next;
    });
  }, []);

  const handleEvent = useCallback(
    (event: ScenarioEvent, index: number) => {
      // Immediate handling for interactive events
      if (event.kind === 'confirmation_request') {
        const conf = event as ConfirmationRequestEvent;
        setActiveConfirmation(conf.answered ? null : conf);
      }

      // Batch rapid streaming events (message and thinking chunks) into 16ms frame windows (60Hz)
      if (event.kind === 'message' || event.kind === 'thinking') {
        batchQueueRef.current.push({ event, index });
        if (!batchTimerRef.current) {
          batchTimerRef.current = setTimeout(() => {
            batchTimerRef.current = null;
            flushBatch();
          }, 16);
        }
      } else {
        // Immediate flush for tool calls, errors, tool results
        flushBatch();
        setEvents((prev) => {
          // Deduplication: skip if event with same ID already exists
          const existingIds = new Set(prev.map((e) => e.id));
          if (event.id && existingIds.has(event.id)) {
            return prev;
          }

          let next: ScenarioEvent[];
          if (typeof index === 'number' && index < prev.length) {
            next = [...prev];
            next[index] = event;
          } else {
            next = [...prev, event];
          }
          eventsRef.current = next;
          return next;
        });
      }
    },
    [flushBatch],
  );

  const handleComplete = useCallback(() => {
    flushBatch();
    setIsRunning(false);
    setActiveConfirmation(null);
  }, [flushBatch]);

  const connectToBackend = useCallback(async () => {
    await wsClient.connect();
  }, []);

  const reportError = useCallback((id: string, message: string) => {
    setEvents((prev) => {
      const next = [...prev, { kind: 'error', id: `evt_${id}_${Date.now()}`, message } as ScenarioEvent];
      eventsRef.current = next;
      return next;
    });
    setIsRunning(false);
  }, []);

  const startScenario = useCallback(
    async (prompt: string, selectedMode: ScenarioMode, provider?: string) => {
      setEvents([]);
      eventsRef.current = [];
      setIsRunning(true);

      try {
        await connectToBackend();
      } catch {
        reportError('conn', 'Cannot connect to backend. Run: zenith serve');
        return;
      }

      try {
        if (sessionIdRef.current) {
          try {
            const result = await wsClient.resumeSession(sessionIdRef.current);
            const resumed = result.session as { id?: string };
            if (resumed?.id && resumed.id !== sessionIdRef.current) {
              sessionIdRef.current = resumed.id;
            }
          } catch {
            sessionIdRef.current = null;
          }
        }
        if (!sessionIdRef.current) {
          try {
            const session = await wsClient.createSession(prompt.slice(0, 50));
            sessionIdRef.current = session.id;
            setLastSessionId(session.id);
          } catch {
            await connectToBackend();
            const session = await wsClient.createSession(prompt.slice(0, 50));
            sessionIdRef.current = session.id;
            setLastSessionId(session.id);
          }
        }
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : String(err);
        reportError('sess', `Failed to create session: ${message}`);
        return;
      }

      const scenario: Scenario = {
        ...backendScenarioProvider.resolve(prompt, selectedMode),
        sessionId: sessionIdRef.current ?? undefined,
      };
      runnerRef.current = backendScenarioProvider.execute(scenario, handleEvent, handleComplete);

      wsClient.sendPrompt(prompt, selectedMode, sessionIdRef.current ?? undefined, provider).catch((err) => {
        const message = err instanceof Error ? err.message : String(err);
        reportError('prompt_err', `Backend prompt error: ${message}`);
      });
    },
    [connectToBackend, handleEvent, handleComplete, reportError],
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
    eventsRef,
    isRunning,
    startScenario,
    abort,
    activeConfirmation,
    respondConfirmation,
    lastSessionId,
  };
}
