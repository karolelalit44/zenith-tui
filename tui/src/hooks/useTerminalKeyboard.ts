import { useInput } from 'ink';
import { useEffect, useRef } from 'react';
import { matchKeypress } from '../config/keybind';
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
  abortActiveTurn: (events?: ScenarioEvent[]) => void;
  markTurnSaved: (turnId: string) => void;
  clearTurns?: () => void;
  onToggleThinking?: () => void;
  activeConfirmation: ConfirmationRequestEvent | null;
  respondConfirmation: (approved: boolean) => void;
  scrollUp?: (lines?: number) => void;
  scrollDown?: (lines?: number) => void;
  scrollToTop?: () => void;
  scrollToBottom?: () => void;
  showPalette?: boolean;
  setShowPalette?: (show: boolean) => void;
  openModelPicker?: () => void;
  composerRunning?: boolean;
  /** True while the inline slash-command menu is open (it owns the keys). */
  slashMenuOpen?: boolean;
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
  showPalette,
  setShowPalette,
  openModelPicker,
  composerRunning,
  slashMenuOpen,
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
    showPalette,
    setShowPalette,
    openModelPicker,
    composerRunning,
    slashMenuOpen,
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
      showPalette,
      setShowPalette,
      openModelPicker,
      composerRunning,
      slashMenuOpen,
    };
  });

  useInput(
    (input, key) => {
      const opts = optionsRef.current;

      if (opts.activeConfirmation && !opts.activeConfirmation.answered && opts.overlay === 'none') {
        if (input === 'y' || input === 'Y') {
          opts.respondConfirmation(true);
          return;
        }
        if (input === 'n' || input === 'N' || key.escape) {
          opts.respondConfirmation(false);
          return;
        }
        return;
      }

      const pressed = matchKeypress(input, key);
      const paletteOpen = opts.showPalette ?? false;

      // The inline slash menu owns the input while it is open: up/down/enter/
      // tab/esc are handled by the dropdown and the composer, so global keys
      // (including esc which would otherwise cancel a running turn) are idle.
      if (opts.slashMenuOpen) {
        return;
      }

      // Command palette owns the input while open — only close/toggle here.
      if (paletteOpen) {
        if (pressed.includes('palette') || key.escape) {
          if (opts.setShowPalette) opts.setShowPalette(false);
        }
        return;
      }

      // interrupt: escape closes overlays / cancels the running turn. The
      // models overlay is exempt — ModelPickerFlow owns esc for stage back/close.
      if (key.escape) {
        if (opts.overlay === 'models') {
          return;
        }
        if (opts.overlay !== 'none') {
          if (opts.closeAllOverlays) opts.closeAllOverlays();
          else if (opts.closeOverlay) opts.closeOverlay();
          return;
        }
        if (opts.isRunning || opts.composerRunning) {
          opts.abort();
          opts.abortActiveTurn(opts.events);
        }
        return;
      }

      // Overlays own their own input while open.
      if (opts.overlay !== 'none') return;

      if (pressed.includes('palette')) {
        if (opts.setShowPalette) opts.setShowPalette(!paletteOpen);
        return;
      }

      if (pressed.includes('model_picker')) {
        if (opts.openModelPicker) opts.openModelPicker();
        else if (opts.openOverlay) opts.openOverlay('models');
        return;
      }

      if (pressed.includes('thinking')) {
        if (opts.onToggleThinking) opts.onToggleThinking();
        return;
      }

      if (pressed.includes('save_plan')) {
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

      if (pressed.includes('clear_turns')) {
        if (opts.clearTurns) opts.clearTurns();
        return;
      }

      // ctrl+c while running cancels the turn; when idle the composer's
      // onSpecial clears the input (single handler, no double-fire).
      if (pressed.includes('clear_input')) {
        if (opts.isRunning || opts.composerRunning) {
          opts.abort();
          opts.abortActiveTurn(opts.events);
        }
        return;
      }

      if (!opts.activeConfirmation) {
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

        if (input === 'g' && key.shift) {
          if (opts.scrollToTop) opts.scrollToTop();
          return;
        }

        if (input === 'G' && key.shift) {
          if (opts.scrollToBottom) opts.scrollToBottom();
          return;
        }
      }
    },
    { isActive: true },
  );
}
