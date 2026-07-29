import { useCallback, useState } from 'react';
export function useOverlayManager(initialMode = 'build') {
    const [selectedMode, setSelectedMode] = useState(initialMode);
    const [overlayStack, setOverlayStack] = useState([]);
    const overlay = overlayStack.length > 0 ? overlayStack[overlayStack.length - 1] : 'none';
    const isOverlayOpen = overlayStack.length > 0;
    const openOverlay = useCallback((type) => {
        setOverlayStack((prev) => {
            if (prev[prev.length - 1] === type)
                return prev;
            if (type === 'none')
                return [];
            return [...prev, type];
        });
    }, []);
    const closeOverlay = useCallback(() => {
        setOverlayStack((prev) => prev.slice(0, -1));
    }, []);
    const closeAllOverlays = useCallback(() => {
        setOverlayStack([]);
    }, []);
    const handleModeSelect = useCallback((mode) => {
        setSelectedMode(mode);
        setOverlayStack((prev) => prev.filter((o) => o !== 'mode'));
    }, []);
    return {
        selectedMode,
        overlay,
        overlayStack,
        isOverlayOpen,
        openOverlay,
        closeOverlay,
        closeAllOverlays,
        handleModeSelect,
    };
}
