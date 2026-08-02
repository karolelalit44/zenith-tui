import { Box } from 'ink';
import React from 'react';
import type { OverlayType } from '../hooks/useOverlayManager';
import { ContextModal } from '../screens/Context/ContextModal';
import { HelpModal } from '../screens/Help/HelpModal';
import { ModeSelectScreen } from '../screens/ModeSelect';
import { ModelPicker } from '../screens/Provider/ModelPicker';
import { ProviderFlow } from '../screens/Provider/ProviderFlow';
import { SettingsModal } from '../screens/Settings/SettingsModal';
import UsageModal from '../screens/Usage/UsageModal';
import type { TokenUsageStats } from '../services/api/TokenUsageService';
import { modelStore } from '../services/providers/ModelStore';
import { providerRepository } from '../services/providers/ProviderRepository';
import { providerService } from '../services/providers/ProviderService';
import type { ScenarioEvent, ScenarioMode } from '../types/scenario';

interface OverlayRouterProps {
  overlay: OverlayType;
  isOverlayOpen: boolean;
  selectedMode: ScenarioMode;
  totalTokens: number;
  events: ScenarioEvent[];
  tokenUsageStats?: TokenUsageStats | null;
  onSelectMode: (mode: ScenarioMode) => void;
  onClose: () => void;
  onComplete: () => void;
}

export const OverlayRouter: React.FC<OverlayRouterProps> = ({
  overlay,
  isOverlayOpen,
  selectedMode,
  totalTokens,
  events,
  onSelectMode,
  onClose,
  onComplete,
}) => {
  if (!isOverlayOpen) return null;

  return (
    <>
      {overlay === 'mode' && (
        <Box flexDirection="column" marginTop={1} width="100%">
          <ModeSelectScreen currentMode={selectedMode} onSelect={onSelectMode} onClose={onClose} />
        </Box>
      )}
      {overlay === 'help' && (
        <Box flexDirection="column" marginTop={1} width="100%">
          <HelpModal onClose={onClose} />
        </Box>
      )}
      {overlay === 'settings' && (
        <Box flexDirection="column" marginTop={1} width="100%">
          <SettingsModal onClose={onClose} />
        </Box>
      )}
      {overlay === 'context' && (
        <Box flexDirection="column" marginTop={1} width="100%">
          <ContextModal totalTokens={totalTokens} runningEvents={events} onClose={onClose} />
        </Box>
      )}
      {overlay === 'provider' && (
        <Box flexDirection="column" marginTop={1} width="100%">
          <ProviderFlow onClose={onClose} onComplete={() => onComplete()} />
        </Box>
      )}
      {overlay === 'models' && (
        <Box flexDirection="column" marginTop={1} width="100%">
          <ModelPicker
            onSelect={(sel) => {
              void providerRepository.setModel(sel.providerID, sel.modelID).then(() => {
                modelStore.set(sel);
                providerService.notifyChange();
              });
              onClose();
            }}
            onClose={onClose}
          />
        </Box>
      )}
      {overlay === 'usage' && (
        <Box flexDirection="column" marginTop={1} width="100%">
          <UsageModal onClose={onClose} />
        </Box>
      )}
    </>
  );
};
