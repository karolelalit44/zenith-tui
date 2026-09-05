import React, { useCallback, useEffect, useRef, useState } from 'react';
import { LIVE_PROGRESS_EVENT_ID } from '../constants/events';
import { backendScenarioProvider } from '../services/transport/BackendScenarioProvider';
import { wsClient } from '../services/transport/WebSocketClient';
import type {
  FileAttachment,
  Scenario,
  ScenarioEvent,
  ScenarioMode,
  ScenarioRunner,
  ThinkingEvent,
  ToolStepEvent,
  TurnManifestEvent,
} from '../types/scenario';
import { resolvePendingToolStep, upsertEvent } from '../utils/eventUpsert';

export interface UseScenarioReturn {
  events: ScenarioEvent[];
  eventsRef: React.MutableRefObject<ScenarioEvent[]>;
  isRunning: boolean;
  startScenario: (
    prompt: string,
    mode: ScenarioMode,
    provider?: string,
    model?: string,
    attachments?: FileAttachment[],
  ) => void;
  continueFromManifest: (
    prompt: string,
    mode: ScenarioMode,
    manifest: TurnManifestEvent,
    provider?: string,
    model?: string,
  ) => void;
  abort: () => void;
  startCompaction: () => void;
  lastSessionId: string | null;
  setActiveSessionId: (id: string | null) => void;
  lastManifest: { manifest: TurnManifestEvent; originalPrompt: string } | null;
}

export function useScenario(): UseScenarioReturn {
  const [events, setEvents] = useState<ScenarioEvent[]>([]);
  const eventsRef = useRef<ScenarioEvent[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [lastSessionId, setLastSessionId] = useState<string | null>(null);
  const [lastManifest, setLastManifest] = useState<{ manifest: TurnManifestEvent; originalPrompt: string } | null>(
    null,
  );
  const runnerRef = useRef<ScenarioRunner | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const abortRequestedRef = useRef(false);

  useEffect(() => {
    wsClient.connect().catch(() => {});
  }, []);

  const batchQueueRef = useRef<{ event: ScenarioEvent; index: number }[]>([]);
  const batchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingToolSteps = useRef<
    Map<string, { callId?: string; index: number; tool: string; params: Record<string, unknown>; text?: string }>
  >(new Map());
  const lastWarningRef = useRef<string | null>(null);

  const applyQueueTo = useCallback(
    (base: ScenarioEvent[], queue: { event: ScenarioEvent; index: number }[]): ScenarioEvent[] => {
      let next = [...base];
      for (const { event, index } of queue) {
        // Reasoning streams as partial thinking events; they grow the LAST
        // block in place instead of stacking a new block per delta.
        if (event.kind === 'thinking' && next.length > 0) {
          const last = next[next.length - 1];
          const lastIsPartialThinking = last.kind === 'thinking' && (last as ThinkingEvent).partial === true;
          const incomingPartial = (event as ThinkingEvent).partial === true;
          if (lastIsPartialThinking && (incomingPartial || !(event as ThinkingEvent).partial)) {
            next = [...next.slice(0, -1), event];
            continue;
          }
        }
        next = upsertEvent(next, event, index);
      }
      return next;
    },
    [],
  );

  const flushBatch = useCallback(() => {
    if (batchTimerRef.current) {
      clearTimeout(batchTimerRef.current);
      batchTimerRef.current = null;
    }
    if (batchQueueRef.current.length === 0) return;
    const queue = [...batchQueueRef.current];
    batchQueueRef.current = [];

    const next = applyQueueTo(eventsRef.current, queue);
    eventsRef.current = next;
    setEvents(next);
  }, [applyQueueTo]);

  const commitPendingEvents = useCallback(() => {
    if (batchTimerRef.current) {
      clearTimeout(batchTimerRef.current);
      batchTimerRef.current = null;
    }
    if (batchQueueRef.current.length === 0) return;
    const queue = [...batchQueueRef.current];
    batchQueueRef.current = [];
    const next = applyQueueTo(eventsRef.current, queue);
    eventsRef.current = next;
    setEvents(next);
  }, [applyQueueTo]);

  const handleEvent = useCallback(
    (event: ScenarioEvent, index: number) => {
      if (event.kind === 'progress') {
        // Backend emits a fresh snapshot per tool step with a unique rpc id;
        // rewriting to one stable id collapses them into a single live card
        // that upsert replaces in place (no stacked duplicate cards).
        event = { ...event, id: LIVE_PROGRESS_EVENT_ID };
        const prev = eventsRef.current;
        const existing = prev.find((e) => e.id === LIVE_PROGRESS_EVENT_ID);
        if (existing && JSON.stringify(existing) === JSON.stringify(event)) {
          return; // identical snapshot — skip render entirely
        }
      }
      if (event.kind === 'turn_manifest') {
        const originalPrompt = eventsRef.current.find((e) => e.kind === 'message')?.text ?? '';
        setLastManifest({ manifest: event as unknown as TurnManifestEvent, originalPrompt });
        flushBatch();
        setEvents((prev) => {
          const next = upsertEvent(prev, event, index);
          eventsRef.current = next;
          return next;
        });
        return;
      }

      if (event.kind === 'tool_call') {
        flushBatch();
        const toolStep: ToolStepEvent = {
          kind: 'tool_step',
          id: event.id,
          tool: event.tool,
          params: event.params,
          success: false,
          output: '',
          error: '',
          metadata: {},
          text: event.text,
          pending: true,
        };

        setEvents((prev) => {
          const existingIds = new Set(prev.map((e) => e.id));
          if (event.id && existingIds.has(event.id)) {
            return prev;
          }

          const next = [...prev, toolStep];
          pendingToolSteps.current.set(event.id, {
            callId: event.id,
            index: next.length - 1,
            tool: event.tool,
            params: event.params,
            text: event.text,
          });
          eventsRef.current = next;
          return next;
        });
        return;
      }

      if (event.kind === 'tool_result') {
        flushBatch();
        const matched = resolvePendingToolStep(pendingToolSteps.current, event.id, event.tool);

        if (matched) {
          const { key: callId, step: pending } = matched;
          const toolStep: ToolStepEvent = {
            kind: 'tool_step',
            id: callId,
            tool: event.tool,
            params: pending.params,
            success: event.success,
            output: event.output,
            error: event.error,
            truncated: event.truncated,
            metadata: event.metadata,
            text: pending.text,
            pending: false,
          };

          setEvents((prev) => {
            const existingIdx = prev.findIndex((e) => e.id === callId);
            let next: ScenarioEvent[];
            if (existingIdx >= 0) {
              next = [...prev];
              next[existingIdx] = toolStep;
            } else {
              next = upsertEvent(prev, toolStep, pending.index);
            }
            eventsRef.current = next;
            return next;
          });
          return;
        }

        const orphan: ToolStepEvent = {
          kind: 'tool_step',
          id: event.id,
          tool: event.tool,
          params: (event.metadata.params as Record<string, unknown>) || {},
          success: event.success,
          output: event.output,
          error: event.error,
          truncated: event.truncated,
          metadata: event.metadata,
          pending: false,
        };

        setEvents((prev) => {
          const next = [...prev, orphan];
          eventsRef.current = next;
          return next;
        });
        return;
      }

      if (event.kind === 'warning') {
        const message = String(event.message || '');
        if (lastWarningRef.current === message) {
          return;
        }
        lastWarningRef.current = message;
      } else {
        lastWarningRef.current = null;
      }

      const isPartialStream =
        (event.kind === 'message' && (event as import('../types/scenario').MessageEvent).partial === true) ||
        (event.kind === 'thinking' && (event as import('../types/scenario').ThinkingEvent).partial === true);

      if (isPartialStream) {
        batchQueueRef.current.push({ event, index });
        if (!batchTimerRef.current) {
          batchTimerRef.current = setTimeout(() => {
            batchTimerRef.current = null;
            flushBatch();
          }, 16);
        }
      } else {
        flushBatch();
        eventsRef.current = upsertEvent(eventsRef.current, event, index);
        setEvents((prev) => {
          const next = upsertEvent(prev, event, index);
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
    async (
      prompt: string,
      selectedMode: ScenarioMode,
      provider?: string,
      model?: string,
      attachments?: FileAttachment[],
    ) => {
      setEvents([]);
      eventsRef.current = [];
      setIsRunning(true);
      abortRequestedRef.current = false;

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

      if (abortRequestedRef.current) {
        runnerRef.current?.abort();
        if (sessionIdRef.current) {
          wsClient.cancelPrompt(sessionIdRef.current).catch(() => {});
        }
        return;
      }

      const promptAttachments =
        attachments && attachments.length > 0
          ? attachments.map((a) => ({
              path: a.path,
              name: a.name,
              ...(a.kind ? { kind: a.kind } : {}),
              ...(typeof a.size === 'number' ? { size: a.size } : {}),
            }))
          : undefined;

      wsClient
        .sendPrompt(prompt, selectedMode, sessionIdRef.current ?? undefined, provider, {
          ...(model ? { model } : {}),
          ...(promptAttachments && promptAttachments.length > 0 ? { attachments: promptAttachments } : {}),
        })
        .catch((err) => {
          const message = err instanceof Error ? err.message : String(err);
          reportError('prompt_err', `Backend prompt error: ${message}`);
        });
    },
    [connectToBackend, handleEvent, handleComplete, reportError],
  );

  const abort = useCallback(() => {
    abortRequestedRef.current = true;
    commitPendingEvents();
    runnerRef.current?.abort();
    if (sessionIdRef.current) {
      wsClient.cancelPrompt(sessionIdRef.current).catch(() => {});
    }
    setIsRunning(false);
  }, [commitPendingEvents]);

  const startCompaction = useCallback(async () => {
    setEvents([]);
    eventsRef.current = [];
    setIsRunning(true);
    abortRequestedRef.current = false;

    try {
      await connectToBackend();
    } catch {
      reportError('conn', 'Cannot connect to backend. Run: zenith serve');
      return;
    }

    if (!sessionIdRef.current) {
      try {
        const session = await wsClient.createSession('Context compaction');
        sessionIdRef.current = session.id;
        setLastSessionId(session.id);
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : String(err);
        reportError('sess', `Failed to create session: ${message}`);
        return;
      }
    }

    // Real RPC: stream the backend's compaction events live.
    runnerRef.current = backendScenarioProvider.executeCompaction(sessionIdRef.current, handleEvent, handleComplete);

    if (abortRequestedRef.current) {
      runnerRef.current?.abort();
    }
  }, [connectToBackend, handleEvent, handleComplete, reportError]);

  const setActiveSessionId = useCallback((id: string | null) => {
    sessionIdRef.current = id;
    setLastSessionId(id);
  }, []);

  const continueFromManifest = useCallback(
    async (
      prompt: string,
      selectedMode: ScenarioMode,
      manifest: TurnManifestEvent,
      provider?: string,
      model?: string,
    ) => {
      setLastManifest(null);
      setIsRunning(true);
      abortRequestedRef.current = false;

      try {
        await connectToBackend();
      } catch {
        reportError('conn', 'Cannot connect to backend. Run: zenith serve');
        return;
      }

      const scenario: Scenario = {
        ...backendScenarioProvider.resolve(prompt, selectedMode),
        sessionId: sessionIdRef.current ?? undefined,
      };
      runnerRef.current = backendScenarioProvider.execute(scenario, handleEvent, handleComplete);

      if (abortRequestedRef.current) {
        runnerRef.current?.abort();
        if (sessionIdRef.current) {
          wsClient.cancelPrompt(sessionIdRef.current).catch(() => {});
        }
        return;
      }

      wsClient
        .continuePrompt(
          prompt,
          selectedMode,
          sessionIdRef.current ?? undefined,
          provider,
          manifest as TurnManifestEvent,
          {
            ...(model ? { model } : {}),
          },
        )
        .catch((err) => {
          const message = err instanceof Error ? err.message : String(err);
          reportError('prompt_err', `Backend prompt error: ${message}`);
        });
    },
    [connectToBackend, handleEvent, handleComplete, reportError],
  );

  return {
    events,
    eventsRef,
    isRunning,
    startScenario,
    continueFromManifest,
    abort,
    startCompaction,
    lastSessionId,
    setActiveSessionId,
    lastManifest,
  };
}
