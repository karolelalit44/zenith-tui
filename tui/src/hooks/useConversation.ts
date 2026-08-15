import { useCallback, useMemo, useState } from 'react';
import { estimateTokensForEvents } from '../services/api/tokenEstimationService';
import type { ScenarioEvent, ScenarioMode, SuccessEvent } from '../types/scenario';

export interface ConversationTurn {
  id: string;
  prompt: string;
  mode: ScenarioMode;
  model?: string;
  events: ScenarioEvent[];
  isComplete: boolean;
  /** Short timestamp frozen at turn creation: "HH:MM" (e.g. "12:08") */
  timestamp: string;
  /** Long timestamp frozen at turn creation: "HH:MM, DD Mon" (e.g. "12:08, 12 Aug") */
  timestampLong: string;
  startedAt: number;
}

export interface UseConversationReturn {
  turns: ConversationTurn[];
  completedTurns: ConversationTurn[];
  activeTurn: ConversationTurn | null;
  totalTokens: number;
  staticKey: number;
  addTurn: (prompt: string, mode: ScenarioMode, model?: string) => string;
  completeActiveTurn: (events: ScenarioEvent[]) => void;
  abortActiveTurn: (events?: ScenarioEvent[]) => void;
  clearTurns: () => void;
  remountStatic: () => void;
}

export function useConversation(): UseConversationReturn {
  const [turns, setTurns] = useState<ConversationTurn[]>([]);
  const [staticKey, setStaticKey] = useState(0);

  const remountStatic = useCallback(() => {
    setStaticKey((k) => k + 1);
  }, []);

  const activeTurn = turns.length > 0 && !turns[turns.length - 1].isComplete ? turns[turns.length - 1] : null;
  const completedTurns = activeTurn ? turns.filter((t) => t.isComplete) : turns;

  const totalTokens = useMemo(() => {
    return turns.reduce((sum, t) => {
      if (!t.isComplete) return sum;

      const successEvent = t.events.find(
        (e): e is SuccessEvent => e.kind === 'success' && 'tokenInfo' in e && Boolean((e as SuccessEvent).tokenInfo),
      );
      if (successEvent?.tokenInfo) {
        return sum + successEvent.tokenInfo.used;
      }

      return sum + estimateTokensForEvents(t.events);
    }, 0);
  }, [turns]);

  const addTurn = useCallback((prompt: string, mode: ScenarioMode, model?: string): string => {
    // Freeze both formats at the exact moment the turn is created.
    // The display component must never call new Date() — these values are immutable.
    const now = new Date();
    const timeShort = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
    const timeLong = `${timeShort}, ${now.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}`;
    const turnId = `turn_${Date.now()}`;

    setTurns((prev) => [
      ...prev,
      {
        id: turnId,
        prompt,
        mode,
        model,
        events: [],
        isComplete: false,
        timestamp: timeShort,
        timestampLong: timeLong,
        startedAt: Date.now(),
      },
    ]);

    return turnId;
  }, []);

  const completeActiveTurn = useCallback((events: ScenarioEvent[]) => {
    setTurns((prev) => {
      const lastIdx = prev.length - 1;
      const last = prev[lastIdx];
      const elapsedMs = last ? Math.max(1000, Date.now() - last.startedAt) : undefined;

      const stampedEvents =
        elapsedMs !== undefined
          ? events.map((e) => (e.kind === 'success' ? { ...e, elapsedMs: e.elapsedMs ?? elapsedMs } : e))
          : events;

      // Ensure a success event always exists so the unified status row renders
      const hasSuccess = stampedEvents.some((e) => e.kind === 'success');
      const finalEvents = hasSuccess
        ? stampedEvents
        : [
            ...stampedEvents,
            {
              kind: 'success',
              id: `evt_success_complete_${Date.now()}`,
              message: 'done',
              elapsedMs: elapsedMs ?? 1000,
            } as ScenarioEvent,
          ];

      return prev.map((t, i) => (i === lastIdx ? { ...t, events: finalEvents, isComplete: true } : t));
    });
  }, []);

  const abortActiveTurn = useCallback((currentEvents: ScenarioEvent[] = []) => {
    setTurns((prev) => {
      const lastIdx = prev.length - 1;
      const last = prev[lastIdx];
      if (last && !last.isComplete) {
        const elapsedMs = Math.max(1000, Date.now() - last.startedAt);
        const sourceEvents = currentEvents && currentEvents.length > 0 ? currentEvents : last.events;

        // Preserve all generated content and resolve pending tool steps cleanly
        const stampedEvents = sourceEvents.map((e) => {
          const updated = { ...e };
          if (updated.kind === 'tool_step' && updated.pending) {
            updated.pending = false;
            updated.success = updated.success ?? true;
          }
          if (updated.kind === 'success') {
            updated.elapsedMs = updated.elapsedMs ?? elapsedMs;
          }
          return updated;
        });

        // Ensure a success metrics event exists so the frozen status row stays visible
        const hasSuccess = stampedEvents.some((e) => e.kind === 'success');
        const finalEvents = hasSuccess
          ? stampedEvents
          : [
              ...stampedEvents,
              {
                kind: 'success',
                id: `evt_success_abort_${Date.now()}`,
                message: 'Turn stopped',
                elapsedMs,
              } as ScenarioEvent,
            ];

        // Mark turn complete — the unified SuccessCard row freezes its timer in place
        return prev.map((t, i) => (i === lastIdx ? { ...t, events: finalEvents, isComplete: true } : t));
      }
      return prev;
    });
  }, []);

  const clearTurns = useCallback(() => {
    setTurns([]);
    setStaticKey((k) => k + 1);
    process.stdout.write('\x1B[2J\x1B[H');
  }, []);

  return {
    turns,
    completedTurns,
    activeTurn,
    totalTokens,
    staticKey,
    addTurn,
    completeActiveTurn,
    abortActiveTurn,
    clearTurns,
    remountStatic,
  };
}
