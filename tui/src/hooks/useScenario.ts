import React, { useCallback, useEffect, useRef, useState } from 'react';
import type { ScenarioRunner } from '../services/scenario/types';
import { backendScenarioProvider } from '../services/transport/BackendScenarioProvider';
import { wsClient } from '../services/transport/WebSocketClient';
import type {
  FileAttachment,
  Scenario,
  ScenarioEvent,
  ScenarioMode,
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

  useEffect(() => {
    wsClient.connect().catch(() => {});
  }, []);

  const batchQueueRef = useRef<{ event: ScenarioEvent; index: number }[]>([]);
  const batchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingToolSteps = useRef<
    Map<string, { index: number; tool: string; params: Record<string, unknown>; text?: string }>
  >(new Map());
  const lastWarningRef = useRef<string | null>(null);

  const flushBatch = useCallback(() => {
    if (batchQueueRef.current.length === 0) return;
    const queue = [...batchQueueRef.current];
    batchQueueRef.current = [];

    setEvents((prev) => {
      let next = [...prev];
      for (const { event, index } of queue) {
        next = upsertEvent(next, event, index);
      }
      eventsRef.current = next;
      return next;
    });
  }, []);

  const handleEvent = useCallback(
    (event: ScenarioEvent, index: number) => {
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

          let next: ScenarioEvent[];
          if (typeof index === 'number' && index < prev.length) {
            next = [...prev];
            next[index] = toolStep;
          } else {
            next = [...prev, toolStep];
          }
          pendingToolSteps.current.set(event.id, {
            index: typeof index === 'number' && index < next.length ? index : next.length - 1,
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
          const { step: pending } = matched;
          const toolStep: ToolStepEvent = {
            kind: 'tool_step',
            id: event.id,
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
            const next = upsertEvent(prev, toolStep, pending.index);
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
          const next = upsertEvent(prev, orphan, index);
          eventsRef.current = next;
          return next;
        });
        return;
      }

      if (event.kind === 'warning') {
        const message = String(event.message || '');
        if (message.includes('[System]')) {
          return;
        }
        if (lastWarningRef.current === message) {
          return;
        }
        lastWarningRef.current = message;
      } else {
        lastWarningRef.current = null;
      }

      if (event.kind === 'message' || event.kind === 'thinking') {
        batchQueueRef.current.push({ event, index });
        if (!batchTimerRef.current) {
          batchTimerRef.current = setTimeout(() => {
            batchTimerRef.current = null;
            flushBatch();
          }, 16);
        }
      } else {
        flushBatch();
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

      const promptAttachments =
        attachments && attachments.length > 0 ? attachments.map((a) => ({ path: a.path, name: a.name })) : undefined;

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
    runnerRef.current?.abort();
    if (sessionIdRef.current) {
      wsClient.cancelPrompt(sessionIdRef.current).catch(() => {});
    }
    setIsRunning(false);
  }, []);

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
    lastSessionId,
    setActiveSessionId,
    lastManifest,
  };
}
