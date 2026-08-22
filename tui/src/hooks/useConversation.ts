import { useCallback, useMemo, useState } from 'react';
import { estimateTokensForEvents } from '../services/api/tokenEstimationService';
import type { ScenarioEvent, ScenarioMode, SuccessEvent, TokenInfo } from '../types/scenario';

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

/**
 * Composed-context occupancy snapshot reported by the backend success event.
 *
 * This is the ONLY data that should ever drive the context gauge — it is NOT
 * cumulative run/API usage (see `runTokens`). `used` is the tokenizer estimate
 * of the composed messages currently in the context window.
 */
export interface ContextInfoSnapshot {
  /** Composed context tokens in use. */
  used: number;
  /** Tokens remaining before the window is exhausted. */
  remaining: number;
  /** Composed context window size. */
  total: number;
  /** Occupancy fraction (0–1) as reported by the backend. */
  percent: number;
  /** True when the backend could not resolve the real provider window. */
  windowEstimated: boolean;
}

/**
 * Return the success tokenInfo of a completed turn, or undefined when the turn
 * never reported one (legacy synthesized success / no usage data at all).
 */
function getSuccessTokenInfo(turn: ConversationTurn): TokenInfo | undefined {
  if (!turn.isComplete) return undefined;
  const successEvent = turn.events.find(
    (e): e is SuccessEvent => e.kind === 'success' && 'tokenInfo' in e && Boolean((e as SuccessEvent).tokenInfo),
  );
  return successEvent?.tokenInfo;
}

export interface UseConversationReturn {
  turns: ConversationTurn[];
  completedTurns: ConversationTurn[];
  activeTurn: ConversationTurn | null;
  totalTokens: number;
  /** Cumulative run/API usage (provider `runTotal` when available, else legacy estimate). */
  runTokens: number;
  /** Cumulative prompt tokens for the run (0 when the provider did not report them). */
  runPrompt: number;
  /** Cumulative completion tokens for the run (0 when the provider did not report them). */
  runCompletion: number;
  /** True when the latest run-usage figure is an estimate, not provider-reported. */
  runEstimated: boolean;
  /** Latest composed-context occupancy snapshot from a completed turn (undefined when unknown). */
  contextInfo: ContextInfoSnapshot | undefined;
  staticKey: number;
  addTurn: (prompt: string, mode: ScenarioMode, model?: string) => string;
  completeActiveTurn: (events: ScenarioEvent[]) => void;
  abortActiveTurn: (events?: ScenarioEvent[]) => void;
  clearTurns: () => void;
  loadTurns: (turns: ConversationTurn[]) => void;
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

      const reported = getSuccessTokenInfo(t);
      if (reported && !reported.estimated && reported.used > 0) {
        return sum + reported.used;
      }

      return sum + estimateTokensForEvents(t.events);
    }, 0);
  }, [turns]);

  // Cumulative run/API token telemetry. Prefer the provider-reported runTotal;
  // fall back to composed occupancy only when it was authoritative (legacy),
  // then to the frontend character estimate.
  const runTokens = useMemo(() => {
    return turns.reduce((sum, t) => {
      if (!t.isComplete) return sum;

      const reported = getSuccessTokenInfo(t);
      if (reported && typeof reported.runTotal === 'number' && reported.runTotal > 0) {
        return sum + reported.runTotal;
      }
      if (reported && !reported.estimated && reported.used > 0) {
        return sum + reported.used;
      }

      return sum + estimateTokensForEvents(t.events);
    }, 0);
  }, [turns]);

  const runPrompt = useMemo(() => {
    return turns.reduce((sum, t) => {
      const reported = getSuccessTokenInfo(t);
      if (reported && typeof reported.runTotal === 'number' && reported.runTotal > 0) {
        return sum + (typeof reported.runPrompt === 'number' ? reported.runPrompt : 0);
      }
      return sum;
    }, 0);
  }, [turns]);

  const runCompletion = useMemo(() => {
    return turns.reduce((sum, t) => {
      const reported = getSuccessTokenInfo(t);
      if (reported && typeof reported.runTotal === 'number' && reported.runTotal > 0) {
        return sum + (typeof reported.runCompletion === 'number' ? reported.runCompletion : 0);
      }
      return sum;
    }, 0);
  }, [turns]);

  // The `~` marker for cumulative usage: true when the most recent completed
  // turn either flagged `estimated` or could not report usage at all.
  const runEstimated = useMemo(() => {
    for (let i = turns.length - 1; i >= 0; i -= 1) {
      const t = turns[i];
      if (!t.isComplete) continue;
      const reported = getSuccessTokenInfo(t);
      if (reported) return reported.estimated === true;
      // Completed turn without any tokenInfo → usage came from the char estimator.
      return true;
    }
    return false;
  }, [turns]);

  // Latest composed-context snapshot across completed turns. Iterating forward
  // lets the newest valid snapshot win. Unknown windows (total 0) are skipped so
  // the UI falls back to the legacy estimate path.
  const contextInfo = useMemo<ContextInfoSnapshot | undefined>(() => {
    let snapshot: ContextInfoSnapshot | undefined;
    for (const t of turns) {
      const reported = getSuccessTokenInfo(t);
      if (reported && reported.total > 0) {
        snapshot = {
          used: reported.used,
          remaining: reported.remaining,
          total: reported.total,
          percent: reported.percent,
          windowEstimated: reported.windowEstimated === true,
        };
      }
    }
    return snapshot;
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

  const loadTurns = useCallback((newTurns: ConversationTurn[]) => {
    setTurns(newTurns);
    setStaticKey((k) => k + 1);
    process.stdout.write('\x1B[2J\x1B[3J\x1B[H');
  }, []);

  return {
    turns,
    completedTurns,
    activeTurn,
    totalTokens,
    runTokens,
    runPrompt,
    runCompletion,
    runEstimated,
    contextInfo,
    staticKey,
    addTurn,
    completeActiveTurn,
    abortActiveTurn,
    clearTurns,
    loadTurns,
    remountStatic,
  };
}
