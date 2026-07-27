import { useCallback, useState } from 'react';
import type { ScenarioMode } from '../types/scenario';

export type OverlayType = 'none' | 'mode' | 'help' | 'settings' | 'context' | 'provider';

export interface UseOverlayManagerReturn {
  selectedMode: ScenarioMode;
  overlay: OverlayType;
  overlayStack: OverlayType[];
  isOverlayOpen: boolean;
  openOverlay: (type: OverlayType) => void;
  closeOverlay: () => void;
  closeAllOverlays: () => void;
  handleModeSelect: (mode: ScenarioMode) => void;
}

export function useOverlayManager(initialMode: ScenarioMode = 'build'): UseOverlayManagerReturn {
  const [selectedMode, setSelectedMode] = useState<ScenarioMode>(initialMode);
  const [overlayStack, setOverlayStack] = useState<OverlayType[]>([]);

  const overlay = overlayStack.length > 0 ? overlayStack[overlayStack.length - 1] : 'none';
  const isOverlayOpen = overlayStack.length > 0;

  const openOverlay = useCallback((type: OverlayType) => {
    setOverlayStack((prev) => {
      if (prev[prev.length - 1] === type) return prev;
      if (type === 'none') return [];
      return [...prev, type];
    });
  }, []);

  const closeOverlay = useCallback(() => {
    setOverlayStack((prev) => prev.slice(0, -1));
  }, []);

  const closeAllOverlays = useCallback(() => {
    setOverlayStack([]);
  }, []);

  const handleModeSelect = useCallback((mode: ScenarioMode) => {
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
