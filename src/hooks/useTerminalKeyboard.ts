import { useInput } from 'ink';
import { useEffect } from 'react';
import { savePlanToFile } from '../services/export/markdownExport';
import type { ConversationTurn } from './useConversation';
import type { OverlayState } from './useModeSelector';

interface UseTerminalKeyboardOptions {
  turns: ConversationTurn[];
  isRunning: boolean;
  events: import('../types/scenario').ScenarioEvent[];
  overlay: OverlayState;
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
  closeOverlay,
  abort,
  abortActiveTurn,
  markTurnSaved,
}: UseTerminalKeyboardOptions): void {
  useEffect(() => {
    try {
      process.stdout.write('\x1B[?1000h\x1B[?1002h\x1B[?1006h\x1B[?1015h');
    } catch (_e) {}

    return () => {
      try {
        process.stdout.write('\x1B[?1000l\x1B[?1002l\x1B[?1006l\x1B[?1015l');
      } catch (_e) {}
    };
  }, []);

  useInput(
    (char, key) => {
      if ((key.ctrl || key.meta) && (char === 's' || char === 'S')) {
        const targetTurn = turns[turns.length - 1];
        const targetEvents = isRunning ? events : targetTurn?.events || [];

        if (targetEvents.length > 0) {
          savePlanToFile(targetEvents, targetTurn?.prompt || 'Plan Request', process.cwd(), 'implementation-plan.md');
          markTurnSaved(targetTurn.id);
        }
        return;
      }

      if (overlay === 'mode') {
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
