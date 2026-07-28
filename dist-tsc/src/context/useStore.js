import React, { createContext, useContext, useMemo, useRef, useState } from 'react';
const StoreContext = createContext(null);
export function useStore() {
    const ctx = useContext(StoreContext);
    if (!ctx)
        throw new Error('useStore must be used within StoreProvider');
    return ctx;
}
export function useStoreSelector(selector) {
    const { state } = useStore();
    return selector(state);
}
export function useStoreAction(action) {
    const { actions } = useStore();
    return actions[action];
}
export const StoreProvider = React.memo(({ children, initial }) => {
    const [turns, setTurns] = useState(initial.conversation.turns);
    const [activeTurn, setActiveTurn] = useState(initial.conversation.activeTurn);
    const [totalTokens, setTotalTokens] = useState(initial.conversation.totalTokens);
    const [events, setEvents] = useState(initial.scenario.events);
    const [isRunning, setIsRunning] = useState(initial.scenario.isRunning);
    const [overlay, setOverlay] = useState(initial.overlay.type);
    const [isOverlayOpen, setIsOverlayOpen] = useState(initial.overlay.isOpen);
    const [mode, setMode] = useState(initial.overlay.mode);
    const [thinkingCollapsed, setThinkingCollapsed] = useState(initial.preferences.thinkingCollapsed);
    const [activeConfirmation, setActiveConfirmation] = useState(initial.confirmation.active);
    const state = useMemo(() => ({
        conversation: { turns, activeTurn, totalTokens },
        scenario: { events, isRunning },
        overlay: { type: overlay, isOpen: isOverlayOpen, mode },
        preferences: { thinkingCollapsed },
        confirmation: { active: activeConfirmation },
    }), [
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
    ]);
    const actions = useMemo(() => ({
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
    }), []);
    const storeRef = useRef({ state, actions });
    storeRef.current = { state, actions };
    const value = useMemo(() => storeRef.current, []);
    return React.createElement(StoreContext.Provider, { value: value }, children);
});
StoreProvider.displayName = 'StoreProvider';
