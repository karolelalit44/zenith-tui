import { useInput } from 'ink';
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
  onInsertNewline?: () => void;
  onScrollUp?: () => void;
  onScrollDown?: () => void;
  onScrollToBottom?: () => void;
  onScrollToTop?: () => void;
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
  onInsertNewline,
  onScrollUp,
  onScrollDown,
  onScrollToBottom,
  onScrollToTop,
}: UseTerminalKeyboardOptions): void {
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

      if (key.pageUp || (key.shift && key.upArrow)) {
        if (overlay === 'none' && onScrollUp) {
          onScrollUp();
          return;
        }
      }

      if (key.pageDown || (key.shift && key.downArrow)) {
        if (overlay === 'none' && onScrollDown) {
          onScrollDown();
          return;
        }
      }

      if (key.shift && key.end) {
        if (overlay === 'none' && onScrollToBottom) {
          onScrollToBottom();
          return;
        }
      }

      if (key.shift && key.home) {
        if (overlay === 'none' && onScrollToTop) {
          onScrollToTop();
          return;
        }
      }

      if (key.shift && (char === 't' || char === 'T') && overlay === 'none' && onToggleThinking) {
        onToggleThinking();
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

