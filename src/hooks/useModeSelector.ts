import { useCallback, useState } from 'react';
import type { ScenarioMode } from '../types/scenario';

export type OverlayState = 'none' | 'mode';

export interface UseModeSelectorReturn {
  selectedMode: ScenarioMode;
  overlay: OverlayState;
  isOverlayOpen: boolean;
  openModeSelector: () => void;
  closeOverlay: () => void;
  handleModeSelect: (mode: ScenarioMode) => void;
}

export function useModeSelector(initialMode: ScenarioMode = 'build'): UseModeSelectorReturn {
  const [selectedMode, setSelectedMode] = useState<ScenarioMode>(initialMode);
  const [overlay, setOverlay] = useState<OverlayState>('none');

  const isOverlayOpen = overlay !== 'none';

  const openModeSelector = useCallback(() => {
    setOverlay('mode');
  }, []);

  const closeOverlay = useCallback(() => {
    setOverlay('none');
  }, []);

  const handleModeSelect = useCallback((mode: ScenarioMode) => {
    setSelectedMode(mode);
    setOverlay('none');
  }, []);

  return {
    selectedMode,
    overlay,
    isOverlayOpen,
    openModeSelector,
    closeOverlay,
    handleModeSelect,
  };
}
