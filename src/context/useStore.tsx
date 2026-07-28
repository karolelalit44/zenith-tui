import React, { createContext, useContext, useMemo, useRef, useState } from 'react';
import type { ConversationTurn } from '../hooks/useConversation';
import type { OverlayType } from '../hooks/useOverlayManager';
import type { ConfirmationRequestEvent, ScenarioEvent, ScenarioMode } from '../types/scenario';

export interface StoreState {
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

export interface StoreActions {
  setEvents: React.Dispatch<React.SetStateAction<ScenarioEvent[]>>;
  setIsRunning: (v: boolean) => void;
  setActiveConfirmation: (v: ConfirmationRequestEvent | null) => void;
  setTurns: React.Dispatch<React.SetStateAction<ConversationTurn[]>>;
  setActiveTurn: (v: ConversationTurn | null) => void;
  setTotalTokens: (v: number) => void;
  setOverlay: (v: OverlayType) => void;
  setIsOverlayOpen: (v: boolean) => void;
  setMode: (v: ScenarioMode) => void;
  setThinkingCollapsed: (v: boolean) => void;
}

export interface Store {
  state: StoreState;
  actions: StoreActions;
}

const StoreContext = createContext<Store | null>(null);

export function useStore(): Store {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error('useStore must be used within StoreProvider');
  return ctx;
}

export function useStoreSelector<T>(selector: (state: StoreState) => T): T {
  const { state } = useStore();
  return selector(state);
}

export function useStoreAction<K extends keyof StoreActions>(action: K): StoreActions[K] {
  const { actions } = useStore();
  return actions[action];
}

interface StoreProviderProps {
  children: React.ReactNode;
  initial: StoreState;
}

export const StoreProvider: React.FC<StoreProviderProps> = React.memo(({ children, initial }) => {
  const [turns, setTurns] = useState<ConversationTurn[]>(initial.conversation.turns);
  const [activeTurn, setActiveTurn] = useState<ConversationTurn | null>(initial.conversation.activeTurn);
  const [totalTokens, setTotalTokens] = useState(initial.conversation.totalTokens);
  const [events, setEvents] = useState<ScenarioEvent[]>(initial.scenario.events);
  const [isRunning, setIsRunning] = useState(initial.scenario.isRunning);
  const [overlay, setOverlay] = useState<OverlayType>(initial.overlay.type);
  const [isOverlayOpen, setIsOverlayOpen] = useState(initial.overlay.isOpen);
  const [mode, setMode] = useState<ScenarioMode>(initial.overlay.mode);
  const [thinkingCollapsed, setThinkingCollapsed] = useState(initial.preferences.thinkingCollapsed);
  const [activeConfirmation, setActiveConfirmation] = useState<ConfirmationRequestEvent | null>(
    initial.confirmation.active,
  );

  const state: StoreState = useMemo(
    () => ({
      conversation: { turns, activeTurn, totalTokens },
      scenario: { events, isRunning },
      overlay: { type: overlay, isOpen: isOverlayOpen, mode },
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
      mode,
      thinkingCollapsed,
      activeConfirmation,
    ],
  );

  const actions: StoreActions = useMemo(
    () => ({
      setEvents,
      setIsRunning,
      setActiveConfirmation,
      setTurns,
      setActiveTurn,
      setTotalTokens,
      setOverlay,
      setIsOverlayOpen,
      setMode,
      setThinkingCollapsed,
    }),
    [],
  );

  const storeRef = useRef<Store>({ state, actions });
  storeRef.current = { state, actions };

  const value = useMemo<Store>(() => storeRef.current, []);

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
});

StoreProvider.displayName = 'StoreProvider';
