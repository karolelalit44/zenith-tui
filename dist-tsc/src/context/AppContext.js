import React, { createContext, useContext, useMemo } from 'react';
const AppContext = createContext(null);
export function useAppState() {
    const ctx = useContext(AppContext);
    if (!ctx)
        throw new Error('useAppState must be used within AppProvider');
    return ctx;
}
export const AppProvider = React.memo(({ children, turns, activeTurn, totalTokens, events, isRunning, overlay, isOverlayOpen, selectedMode, thinkingCollapsed, activeConfirmation, }) => {
    const value = useMemo(() => ({
        conversation: { turns, activeTurn, totalTokens },
        scenario: { events, isRunning },
        overlay: { type: overlay, isOpen: isOverlayOpen, mode: selectedMode },
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
        selectedMode,
        thinkingCollapsed,
        activeConfirmation,
    ]);
    return React.createElement(AppContext.Provider, { value: value }, children);
});
AppProvider.displayName = 'AppProvider';
