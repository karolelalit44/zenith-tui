import { useCallback, useMemo, useState } from 'react';
import { estimateTokensForEvents } from '../services/data/tokenEstimationService';
import type { ScenarioEvent, ScenarioMode, SuccessEvent } from '../types/scenario';

export interface ConversationTurn {
  id: string;
  prompt: string;
  mode: ScenarioMode;
  events: ScenarioEvent[];
  isComplete: boolean;
  timestamp: string;
}

export interface UseConversationReturn {
  turns: ConversationTurn[];
  completedTurns: ConversationTurn[];
  activeTurn: ConversationTurn | null;
  totalTokens: number;
  staticKey: number;
  addTurn: (prompt: string, mode: ScenarioMode) => string;
  completeActiveTurn: (events: ScenarioEvent[]) => void;
  abortActiveTurn: () => void;
  markTurnSaved: (turnId: string) => void;
  clearTurns: () => void;
  compactTurns: () => void;
}

export function useConversation(): UseConversationReturn {
  const [turns, setTurns] = useState<ConversationTurn[]>([]);
  const [staticKey, setStaticKey] = useState(0);

  const activeTurn = turns.length > 0 && !turns[turns.length - 1].isComplete
    ? turns[turns.length - 1]
    : null;
  const completedTurns = activeTurn
    ? turns.filter((t) => t.isComplete)
    : turns;

  const totalTokens = useMemo(() => {
    return turns.reduce((sum, t) => {
      if (!t.isComplete) return sum;
      // Prefer real token data from backend success event if available
      const successEvent = t.events.find(
        (e): e is SuccessEvent => e.kind === 'success' && 'tokenInfo' in e && Boolean((e as SuccessEvent).tokenInfo),
      );
      if (successEvent?.tokenInfo) {
        return sum + successEvent.tokenInfo.used;
      }
      // Fall back to char÷4 estimation
      return sum + estimateTokensForEvents(t.events);
    }, 0);
  }, [turns]);

  const addTurn = useCallback((prompt: string, mode: ScenarioMode): string => {
    const now = new Date();
    const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
    const turnId = `turn_${Date.now()}`;

    setTurns((prev) => [
      ...prev,
      {
        id: turnId,
        prompt,
        mode,
        events: [],
        isComplete: false,
        timestamp: timeStr,
      },
    ]);

    return turnId;
  }, []);

  const completeActiveTurn = useCallback((events: ScenarioEvent[]) => {
    setTurns((prev) => {
      const lastIdx = prev.length - 1;
      return prev.map((t, i) => (i === lastIdx ? { ...t, events: [...events], isComplete: true } : t));
    });
  }, []);

  const abortActiveTurn = useCallback(() => {
    setTurns((prev) => {
      const last = prev[prev.length - 1];
      if (last && !last.isComplete) {
        const abortEvent: ScenarioEvent = {
          kind: 'warning',
          id: `evt_abort_${Date.now()}`,
          message: 'Scenario cancelled by user',
          code: 'USER_ABORT',
        };
        return prev.map((t, i) =>
          i === prev.length - 1 ? { ...t, events: [...t.events, abortEvent], isComplete: true } : t,
        );
      }
      return prev;
    });
  }, []);

  const markTurnSaved = useCallback((_turnId: string) => {
  }, []);

  const clearTurns = useCallback(() => {
    setTurns([]);
    setStaticKey((k) => k + 1);
  }, []);

  const compactTurns = useCallback(() => {
    setTurns((prev) => {
      if (prev.length === 0) return prev;
      const now = new Date();
      const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
      const summaryTurn: ConversationTurn = {
        id: `turn_compact_${Date.now()}`,
        prompt: `Compact Context (${prev.length} previous turns compressed)`,
        mode: prev[prev.length - 1].mode,
        isComplete: true,
        timestamp: timeStr,
        events: [
          {
            kind: 'message',
            id: `evt_summary_${Date.now()}`,
            text: `Context Compacted: Compressed ${prev.length} turns into high-level architectural memory. Key decisions and modified file structures retained.`,
            partial: false,
          } as ScenarioEvent,
        ],
      };
      return [summaryTurn];
    });
    setStaticKey((k) => k + 1);
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
    markTurnSaved,
    clearTurns,
    compactTurns,
  };
}
