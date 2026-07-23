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
  onToggleThinking?: () => void;
  onScrollUp?: () => void;
  onScrollDown?: () => void;
  onInsertNewline?: () => void;
}

export function useTerminalKeyboard({
  turns,
  isRunning,
  events,
  overlay,
  openOverlay,
  closeOverlay: _closeOverlay,
  abort,
  abortActiveTurn,
  markTurnSaved,
  onToggleThinking,
  onScrollUp,
  onScrollDown,
  onInsertNewline,
}: UseTerminalKeyboardOptions): void {
  useEffect(() => {
    // Native terminal scrolling enabled for touchpad & mouse wheel
  }, []);

  useInput(
    (char, key) => {
      if ((key.ctrl || key.meta) && (char === 's' || char === 'S')) {
        if (overlay !== 'none') return;
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

      if (key.shift && (char === 't' || char === 'T') && overlay === 'none' && onToggleThinking) {
        onToggleThinking();
        return;
      }

      if (key.pageUp && overlay === 'none' && onScrollUp) {
        onScrollUp();
        return;
      }

      if (key.pageDown && overlay === 'none' && onScrollDown) {
        onScrollDown();
        return;
      }

      if (key.shift && (char === 'm' || char === 'M') && overlay === 'none' && openOverlay) {
        openOverlay('mode');
        return;
      }

      if (key.return && key.shift && overlay === 'none' && onInsertNewline) {
        onInsertNewline();
        return;
      }

      if (overlay !== 'none') {
        // Active modal handles its own keyboard navigation & 1-step-back Esc key hierarchy
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
