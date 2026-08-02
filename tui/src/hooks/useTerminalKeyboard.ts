import { useInput } from 'ink';
import { useEffect, useRef } from 'react';
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
  closeOverlay?: () => void;
  closeAllOverlays?: () => void;
  abort: () => void;
  abortActiveTurn: () => void;
  markTurnSaved: (turnId: string) => void;
  clearTurns?: () => void;
  onToggleThinking?: () => void;
  activeConfirmation: ConfirmationRequestEvent | null;
  respondConfirmation: (approved: boolean) => void;
  scrollUp?: (lines?: number) => void;
  scrollDown?: (lines?: number) => void;
  scrollToTop?: () => void;
  scrollToBottom?: () => void;
}

export function useTerminalKeyboard({
  turns,
  isRunning,
  events,
  overlay,
  openOverlay,
  closeOverlay,
  closeAllOverlays,
  abort,
  abortActiveTurn,
  markTurnSaved,
  clearTurns,
  onToggleThinking,
  activeConfirmation,
  respondConfirmation,
  scrollUp,
  scrollDown,
  scrollToTop,
  scrollToBottom,
}: UseTerminalKeyboardOptions): void {
  const optionsRef = useRef({
    turns,
    isRunning,
    events,
    overlay,
    openOverlay,
    closeOverlay,
    closeAllOverlays,
    abort,
    abortActiveTurn,
    markTurnSaved,
    clearTurns,
    onToggleThinking,
    activeConfirmation,
    respondConfirmation,
    scrollUp,
    scrollDown,
    scrollToTop,
    scrollToBottom,
  });

  useEffect(() => {
    optionsRef.current = {
      turns,
      isRunning,
      events,
      overlay,
      openOverlay,
      closeOverlay,
      closeAllOverlays,
      abort,
      abortActiveTurn,
      markTurnSaved,
      clearTurns,
      onToggleThinking,
      activeConfirmation,
      respondConfirmation,
      scrollUp,
      scrollDown,
      scrollToTop,
      scrollToBottom,
    };
  });

  useInput(
    (_char, key) => {
      const opts = optionsRef.current;

      if (opts.activeConfirmation && !opts.activeConfirmation.answered && opts.overlay === 'none') {
        if (_char === 'y' || _char === 'Y') {
          opts.respondConfirmation(true);
          return;
        }
        if (_char === 'n' || _char === 'N' || key.escape) {
          opts.respondConfirmation(false);
          return;
        }
        return;
      }

      if (key.escape) {
        if (opts.overlay !== 'none') {
          if (opts.closeAllOverlays) opts.closeAllOverlays();
          else if (opts.closeOverlay) opts.closeOverlay();
          return;
        }
        if (opts.isRunning) {
          opts.abort();
          opts.abortActiveTurn();
        }
        return;
      }

      if ((key.ctrl || key.meta) && opts.overlay === 'none') {
        if (_char === 'c' || _char === 'C') {
          if (opts.isRunning) {
            opts.abort();
            opts.abortActiveTurn();
          }
          return;
        }

        if (_char === 'l' || _char === 'L') {
          if (opts.clearTurns) opts.clearTurns();
          return;
        }

        if (_char === 's' || _char === 'S') {
          const targetTurn = opts.turns[opts.turns.length - 1];
          const targetEvents = opts.isRunning ? opts.events : targetTurn?.events || [];
          if (targetEvents.length > 0) {
            savePlanToFile(targetEvents, targetTurn?.prompt || 'Plan Request', process.cwd(), 'implementation-plan.md');
            if (targetTurn) {
              opts.markTurnSaved(targetTurn.id);
            }
          }
          return;
        }

        if (_char === 'p' || _char === 'P') {
          if (opts.openOverlay) opts.openOverlay('help');
          return;
        }

        if (_char === 'e' || _char === 'E') {
          if (opts.openOverlay) opts.openOverlay('models');
          return;
        }

        if (_char === 'm' || _char === 'M') {
          if (opts.openOverlay) opts.openOverlay('mode');
          return;
        }

        if (_char === 't' || _char === 'T' || _char === '\x14') {
          if (opts.onToggleThinking) opts.onToggleThinking();
          return;
        }
      }

      if (
        (key.shift || key.ctrl) &&
        (_char === 't' || _char === 'T' || _char === '\x14') &&
        opts.overlay === 'none' &&
        opts.onToggleThinking
      ) {
        opts.onToggleThinking();
        return;
      }

      if (opts.overlay === 'none' && !opts.activeConfirmation) {
        if (key.upArrow && (key.ctrl || key.shift)) {
          if (opts.scrollUp) opts.scrollUp();
          return;
        }

        if (key.downArrow && (key.ctrl || key.shift)) {
          if (opts.scrollDown) opts.scrollDown();
          return;
        }

        if (key.pageUp) {
          if (opts.scrollUp) opts.scrollUp(10);
          return;
        }

        if (key.pageDown) {
          if (opts.scrollDown) opts.scrollDown(10);
          return;
        }

        if (_char === 'g' && key.shift) {
          if (opts.scrollToTop) opts.scrollToTop();
          return;
        }

        if (_char === 'G' && key.shift) {
          if (opts.scrollToBottom) opts.scrollToBottom();
          return;
        }

        if (key.return && key.shift) {
          if (opts.scrollToTop) opts.scrollToTop();
          return;
        }

        if (key.return && (key.ctrl || key.meta)) {
          if (opts.scrollToBottom) opts.scrollToBottom();
          return;
        }
      }
    },
    { isActive: true },
  );
}
