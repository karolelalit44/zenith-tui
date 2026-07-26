import { useInput } from 'ink';
import { savePlanToFile } from '../services/export/markdownExport';
import type { ConfirmationRequestEvent, ScenarioEvent } from '../types/scenario';
import type { ConversationTurn } from './useConversation';
import type { OverlayType } from './useOverlayManager';

interface UseTerminalKeyboardOptions {
  turns: ConversationTurn[];
  isRunning: boolean;
  events: ScenarioEvent[];
  overlay: OverlayType;
  openOverlay?: (type: OverlayType) => void;
  abort: () => void;
  abortActiveTurn: () => void;
  markTurnSaved: (turnId: string) => void;
  onToggleThinking?: () => void;
  activeConfirmation: ConfirmationRequestEvent | null;
  respondConfirmation: (approved: boolean) => void;
}

export function useTerminalKeyboard({
  turns,
  isRunning,
  events,
  overlay,
  openOverlay,
  abort,
  abortActiveTurn,
  markTurnSaved,
  onToggleThinking,
  activeConfirmation,
  respondConfirmation,
}: UseTerminalKeyboardOptions): void {
  useInput(
    (char, key) => {
      // Handle confirmation responses when a confirmation is pending
      if (activeConfirmation && !activeConfirmation.answered && overlay === 'none') {
        if (char === 'y' || char === 'Y') {
          respondConfirmation(true);
          return;
        }
        if (char === 'n' || char === 'N' || key.escape) {
          respondConfirmation(false);
          return;
        }
        // Ignore all other keys while confirmation is pending
        return;
      }

      // Ctrl/Cmd+S: Save plan
      if ((key.ctrl || key.meta) && (char === 's' || char === 'S')) {
        if (overlay !== 'none') return;
        const targetTurn = turns[turns.length - 1];
        const targetEvents = isRunning ? events : targetTurn?.events || [];
        if (targetEvents.length > 0) {
          savePlanToFile(targetEvents, targetTurn?.prompt || 'Plan Request', process.cwd(), 'implementation-plan.md');
          if (targetTurn) { markTurnSaved(targetTurn.id); }
        }
        return;
      }

      // Shift+T: Toggle thinking
      if (key.shift && (char === 't' || char === 'T') && overlay === 'none' && onToggleThinking) {
        onToggleThinking();
        return;
      }

      // Shift+M: Open mode selector
      if (key.shift && (char === 'm' || char === 'M') && overlay === 'none' && openOverlay) {
        openOverlay('mode');
        return;
      }

      // Escape: Abort running scenario
      if (overlay !== 'none') return;
      if (isRunning && key.escape) {
        abort();
        abortActiveTurn();
      }
    },
    { isActive: true },
  );
}
