import { useCallback, useMemo, useState } from 'react';
import { estimateTokensForEvents } from '../services/data/tokenEstimationService';
import type { ScenarioEvent, ScenarioMode } from '../types/scenario';

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
    return turns.reduce((sum, t) => sum + (t.isComplete ? estimateTokensForEvents(t.events) : 0), 0);
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
          details: 'Execution was stopped before completion.',
        };
        return prev.map((t, i) =>
          i === prev.length - 1 ? { ...t, events: [...t.events, abortEvent], isComplete: true } : t,
        );
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
