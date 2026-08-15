import { useInput } from 'ink';
import { useEffect, useRef } from 'react';
import { matchKeypress } from '../config/keybind';
import { savePlanToFile } from '../services/export/markdownExport';
import type { ScenarioEvent } from '../types/scenario';
import type { ConversationTurn } from './useConversation';
import type { OverlayType } from './useOverlayManager';

interface UseTerminalKeyboardOptions {
  turns: ConversationTurn[];
  isRunning: boolean;
  events: ScenarioEvent[];
  eventsRef?: { current: ScenarioEvent[] };
  overlay: OverlayType;
  openOverlay?: (type: OverlayType) => void;
  closeOverlay?: () => void;
  closeAllOverlays?: () => void;
  abort: () => void;
  abortActiveTurn: (events?: ScenarioEvent[]) => void;
  clearTurns?: () => void;
  onToggleThinking?: () => void;
  scrollUp?: (lines?: number) => void;
  scrollDown?: (lines?: number) => void;
  scrollToTop?: () => void;
  scrollToBottom?: () => void;
  showPalette?: boolean;
  setShowPalette?: (show: boolean) => void;
  openModelPicker?: () => void;
  composerRunning?: boolean;

  slashMenuOpen?: boolean;
  onToggleHistoryExpanded?: () => void;
}

export function useTerminalKeyboard({
  turns,
  isRunning,
  events,
  eventsRef,
  overlay,
  openOverlay,
  closeOverlay,
  closeAllOverlays,
  abort,
  abortActiveTurn,
  clearTurns,
  onToggleThinking,
  scrollUp,
  scrollDown,
  scrollToTop,
  scrollToBottom,
  showPalette,
  setShowPalette,
  openModelPicker,
  composerRunning,
  slashMenuOpen,
  onToggleHistoryExpanded,
}: UseTerminalKeyboardOptions): void {
  const optionsRef = useRef({
    turns,
    isRunning,
    events,
    eventsRef,
    overlay,
    openOverlay,
    closeOverlay,
    closeAllOverlays,
    abort,
    abortActiveTurn,
    clearTurns,
    onToggleThinking,
    scrollUp,
    scrollDown,
    scrollToTop,
    scrollToBottom,
    showPalette,
    setShowPalette,
    openModelPicker,
    composerRunning,
    slashMenuOpen,
    onToggleHistoryExpanded,
  });

  useEffect(() => {
    optionsRef.current = {
      turns,
      isRunning,
      events,
      eventsRef,
      overlay,
      openOverlay,
      closeOverlay,
      closeAllOverlays,
      abort,
      abortActiveTurn,
      clearTurns,
      onToggleThinking,
      scrollUp,
      scrollDown,
      scrollToTop,
      scrollToBottom,
      showPalette,
      setShowPalette,
      openModelPicker,
      composerRunning,
      slashMenuOpen,
      onToggleHistoryExpanded,
    };
  });

  useInput(
    (input, key) => {
      const opts = optionsRef.current;

      const pressed = matchKeypress(input, key);
      const paletteOpen = opts.showPalette ?? false;

      if (opts.slashMenuOpen) {
        return;
      }

      if (paletteOpen) {
        if (pressed.includes('palette') || key.escape) {
          if (opts.setShowPalette) opts.setShowPalette(false);
        }
        return;
      }

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
          opts.abortActiveTurn(opts.eventsRef?.current ?? opts.events);
        }
        return;
      }

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
        }
        return;
      }

      if (pressed.includes('clear_turns')) {
        if (opts.clearTurns) opts.clearTurns();
        return;
      }

      if (pressed.includes('clear_input')) {
        if (opts.isRunning || opts.composerRunning) {
          opts.abort();
          opts.abortActiveTurn(opts.eventsRef?.current ?? opts.events);
        }
        return;
      }

      if (pressed.includes('expand_history')) {
        if (opts.onToggleHistoryExpanded) opts.onToggleHistoryExpanded();
        return;
      }

      if (pressed.includes('compaction')) {
        if (opts.openOverlay) opts.openOverlay('compaction');
        return;
      }

      if (key.upArrow && (key.ctrl || key.shift)) {
        if (opts.scrollUp) opts.scrollUp();
        return;
      }

      if (key.downArrow && (key.ctrl || key.shift)) {
        if (opts.scrollDown) opts.scrollDown();
        return;
      }

      if (key.pageUp) {
        if (opts.scrollUp) opts.scrollUp(15);
        return;
      }

      if (key.pageDown) {
        if (opts.scrollDown) opts.scrollDown(15);
        return;
      }

      if (key.home) {
        if (opts.scrollToTop) opts.scrollToTop();
        return;
      }

      if (key.end) {
        if (opts.scrollToBottom) opts.scrollToBottom();
        return;
      }
    },
    { isActive: true },
  );
}
