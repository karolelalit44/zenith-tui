import React, { createContext, useContext, useMemo } from 'react';
import type { ConversationTurn } from '../hooks/useConversation';
import type { OverlayType } from '../hooks/useOverlayManager';
import type { ConfirmationRequestEvent, ScenarioEvent, ScenarioMode } from '../types/scenario';

export interface AppState {
  conversation: {
    turns: ConversationTurn[];
    activeTurn: ConversationTurn | null;
    totalTokens: number;
  };
  scenario: {
    events: ScenarioEvent[];
    isRunning: boolean;
  };
  overlay: {
    type: OverlayType;
    isOpen: boolean;
    mode: ScenarioMode;
  };
  preferences: {
    thinkingCollapsed: boolean;
  };
  confirmation: {
    active: ConfirmationRequestEvent | null;
  };
}

const AppContext = createContext<AppState | null>(null);

export function useAppState(): AppState {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useAppState must be used within AppProvider');
  return ctx;
}

interface AppProviderProps {
  children: React.ReactNode;
  turns: ConversationTurn[];
  activeTurn: ConversationTurn | null;
  totalTokens: number;
  events: ScenarioEvent[];
  isRunning: boolean;
  overlay: OverlayType;
  isOverlayOpen: boolean;
  selectedMode: ScenarioMode;
  thinkingCollapsed: boolean;
  activeConfirmation: ConfirmationRequestEvent | null;
}

export const AppProvider: React.FC<AppProviderProps> = React.memo(
  ({
    children,
    turns,
    activeTurn,
    totalTokens,
    events,
    isRunning,
    overlay,
    isOverlayOpen,
    selectedMode,
    thinkingCollapsed,
    activeConfirmation,
  }) => {
    const value = useMemo<AppState>(
      () => ({
        conversation: { turns, activeTurn, totalTokens },
        scenario: { events, isRunning },
        overlay: { type: overlay, isOpen: isOverlayOpen, mode: selectedMode },
        preferences: { thinkingCollapsed },
        confirmation: { active: activeConfirmation },
      }),
      [
        turns,
        activeTurn,
        totalTokens,
        events,
        isRunning,
        overlay,
        isOverlayOpen,
        selectedMode,
        thinkingCollapsed,
        activeConfirmation,
      ],
    );

    return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
  },
);

AppProvider.displayName = 'AppProvider';
