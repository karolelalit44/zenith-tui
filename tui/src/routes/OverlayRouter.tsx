import { Box } from 'ink';
import React from 'react';
import type { ContextInfoSnapshot } from '../hooks/useConversation';
import type { OverlayType } from '../hooks/useOverlayManager';
import { CompactionModal } from '../screens/Context/CompactionModal';
import { ContextModal } from '../screens/Context/ContextModal';
import { HelpModal } from '../screens/Help/HelpModal';
import { ModeSelectScreen } from '../screens/ModeSelect';
import { ProviderFlow } from '../screens/Provider/ProviderFlow';
import { SessionBrowserModal } from '../screens/Session/SessionBrowserModal';
import { SettingsModal } from '../screens/Settings/SettingsModal';
import UsageModal from '../screens/Usage/UsageModal';
import type { TokenUsageStats } from '../services/api/TokenUsageService';
import type { SessionSummary } from '../services/transport/WebSocketClient';
import type { ScenarioEvent, ScenarioMode } from '../types/scenario';

interface OverlayRouterProps {
  overlay: OverlayType;
  isOverlayOpen: boolean;
  selectedMode: ScenarioMode;
  totalTokens: number;
  events: ScenarioEvent[];
  tokenUsageStats?: TokenUsageStats | null;
  /** Cumulative run/API token usage (telemetry). */
  runTokens?: number;
  runPrompt?: number;
  runCompletion?: number;
  runEstimated?: boolean;
  /** Latest composed-context occupancy snapshot. */
  contextInfo?: ContextInfoSnapshot | null;
  onSelectMode: (mode: ScenarioMode) => void;
  onClose: () => void;
  onComplete: () => void;
  onOpenProvider?: () => void;
  onResumeSession?: (sessionId: string, summary: SessionSummary, messages?: Record<string, unknown>[]) => void;
  onCompactNow?: () => void;
}

export const OverlayRouter: React.FC<OverlayRouterProps> = ({
  overlay,
  isOverlayOpen,
  selectedMode,
  totalTokens,
  events,
  runTokens,
  runPrompt,
  runCompletion,
  runEstimated,
  contextInfo,
  onSelectMode,
  onClose,
  onComplete,
  onOpenProvider,
  onResumeSession,
  onCompactNow,
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
          <ContextModal
            totalTokens={totalTokens}
            runningEvents={events}
            onClose={onClose}
            runTokens={runTokens}
            runPrompt={runPrompt}
            runCompletion={runCompletion}
            runEstimated={runEstimated}
            contextInfo={contextInfo}
          />
        </Box>
      )}
      {overlay === 'compaction' && (
        <Box flexDirection="column" marginTop={1} width="100%">
          <CompactionModal
            events={events}
            totalTokens={totalTokens}
            onCompactNow={onCompactNow ?? (() => {})}
            onClose={onClose}
          />
        </Box>
      )}
      {overlay === 'provider' && (
        <Box flexDirection="column" marginTop={1} width="100%">
          <ProviderFlow onClose={onClose} onComplete={() => onComplete()} />
        </Box>
      )}
      {overlay === 'usage' && (
        <Box flexDirection="column" marginTop={1} width="100%">
          <UsageModal onClose={onClose} />
        </Box>
      )}
      {overlay === 'session' && (
        <Box flexDirection="column" marginTop={1} width="100%">
          <SessionBrowserModal
            onClose={onClose}
            onResume={(id, summary, messages) => {
              onResumeSession?.(id, summary, messages);
              onClose();
            }}
          />
        </Box>
      )}
    </>
  );
};
