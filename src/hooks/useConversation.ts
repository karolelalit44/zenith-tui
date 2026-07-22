import { useCallback, useMemo, useState } from 'react';
import type { ScenarioEvent, ScenarioMode } from '../types/scenario';

const MOCK_TOKENS_PER_TURN = 1247;

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
  activeTurn: ConversationTurn | null;
  totalTokens: number;
  addTurn: (prompt: string, mode: ScenarioMode) => string;
  completeActiveTurn: (events: ScenarioEvent[]) => void;
  abortActiveTurn: () => void;
  markTurnSaved: (turnId: string) => void;
  clearTurns: () => void;
  compactTurns: () => void;
}

export function useConversation(): UseConversationReturn {
  const [turns, setTurns] = useState<ConversationTurn[]>([]);

  const activeTurn = turns.length > 0 ? turns[turns.length - 1] : null;

  const totalTokens = useMemo(() => {
    return turns.filter((t) => t.isComplete).length * MOCK_TOKENS_PER_TURN;
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
        return prev.map((t, i) => (i === prev.length - 1 ? { ...t, isComplete: true } : t));
      }
      return prev;
    });
  }, []);

  const markTurnSaved = useCallback((turnId: string) => {
    setTurns((prev) => {
      const targetIdx = prev.findIndex((t) => t.id === turnId);
      if (targetIdx === -1) return prev;
      const updatedEvents = prev[targetIdx].events.map((ev) =>
        ev.kind === 'planner_action_panel' ? { ...ev, saved: true } : ev,
      );
      return prev.map((t, i) => (i === targetIdx ? { ...t, events: updatedEvents } : t));
    });
  }, []);

  const clearTurns = useCallback(() => {
    setTurns([]);
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
            kind: 'summary',
            id: `evt_summary_${Date.now()}`,
            title: 'Context Compacted',
            description: `Compressed ${prev.length} turns into high-level architectural memory. Key decisions and modified file structures retained.`,
            filesCreated: [],
            commandsExecuted: ['/compact'],
            verified: ['Conversation history summarized', 'Context window memory freed'],
          },
        ],
      };
      return [summaryTurn];
    });
  }, []);

  return {
    turns,
    activeTurn,
    totalTokens,
    addTurn,
    completeActiveTurn,
    abortActiveTurn,
    markTurnSaved,
    clearTurns,
    compactTurns,
  };
}
