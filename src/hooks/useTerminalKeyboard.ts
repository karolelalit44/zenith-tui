import { useInput } from 'ink';
import { useEffect } from 'react';
import { savePlanToFile } from '../services/export/markdownExport';
import type { ConversationTurn } from './useConversation';
import type { OverlayType } from './useOverlayManager';

interface UseTerminalKeyboardOptions {
  turns: ConversationTurn[];
  isRunning: boolean;
  events: import('../types/scenario').ScenarioEvent[];
  overlay: OverlayType;
  openOverlay?: (type: OverlayType) => void;
  closeOverlay: () => void;
  abort: () => void;
  abortActiveTurn: () => void;
  markTurnSaved: (turnId: string) => void;
}

export function useTerminalKeyboard({
  turns,
  isRunning,
  events,
  overlay,
  openOverlay,
  closeOverlay,
  abort,
  abortActiveTurn,
  markTurnSaved,
}: UseTerminalKeyboardOptions): void {
  useEffect(() => {
    // Native terminal scrolling enabled for touchpad & mouse wheel
  }, []);

  useInput(
    (char, key) => {
      if ((key.ctrl || key.meta) && (char === 's' || char === 'S')) {
        const targetTurn = turns[turns.length - 1];
        const targetEvents = isRunning ? events : targetTurn?.events || [];

        if (targetEvents.length > 0) {
          savePlanToFile(targetEvents, targetTurn?.prompt || 'Plan Request', process.cwd(), 'implementation-plan.md');
          if (targetTurn) {
            markTurnSaved(targetTurn.id);
          }
        }
        return;
      }

      if (key.shift && (char === 'm' || char === 'M') && overlay === 'none' && openOverlay) {
        openOverlay('mode');
        return;
      }

      if (overlay !== 'none') {
        if (key.escape) {
          closeOverlay();
        }
        return;
      }

      if (isRunning && key.escape) {
        abort();
        abortActiveTurn();
      }
    },
    { isActive: true },
  );
}
