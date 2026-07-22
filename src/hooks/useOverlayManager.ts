import { useCallback, useState } from 'react';
import type { ScenarioMode } from '../types/scenario';

export type OverlayType =
  | 'none'
  | 'mode'
  | 'help'
  | 'persona'
  | 'settings'
  | 'context'
  | 'add-dir'
  | 'agents'
  | 'plugin';

export interface UseOverlayManagerReturn {
  selectedMode: ScenarioMode;
  overlay: OverlayType;
  isOverlayOpen: boolean;
  openOverlay: (type: OverlayType) => void;
  closeOverlay: () => void;
  handleModeSelect: (mode: ScenarioMode) => void;
}

export function useOverlayManager(initialMode: ScenarioMode = 'build'): UseOverlayManagerReturn {
  const [selectedMode, setSelectedMode] = useState<ScenarioMode>(initialMode);
  const [overlay, setOverlay] = useState<OverlayType>('none');

  const isOverlayOpen = overlay !== 'none';

  const openOverlay = useCallback((type: OverlayType) => {
    setOverlay(type);
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
    openOverlay,
    closeOverlay,
    handleModeSelect,
  };
}
