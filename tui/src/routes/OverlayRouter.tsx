import { Box } from 'ink';
import React from 'react';
import type { OverlayType } from '../hooks/useOverlayManager';
import { ContextModal } from '../screens/Context/ContextModal';
import { HelpModal } from '../screens/Help/HelpModal';
import { ModeSelectScreen } from '../screens/ModeSelect';
import { SettingsModal } from '../screens/Settings/SettingsModal';
import { SetupWizard } from '../screens/SetupWizard';
import UsageModal from '../screens/Usage/UsageModal';
import type { TokenUsageStats } from '../services/api/TokenUsageService';
import type { ScenarioEvent, ScenarioMode } from '../types/scenario';
import type { AppStartupState } from '../types/startup';

interface OverlayRouterProps {
  overlay: OverlayType;
  isOverlayOpen: boolean;
  selectedMode: ScenarioMode;
  totalTokens: number;
  events: ScenarioEvent[];
  startupState: AppStartupState;
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
  startupState,
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
          <SetupWizard startupState={startupState} onComplete={onComplete} mode="reconfigure" />
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
