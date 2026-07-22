import React from 'react';
import { Box, Text } from 'ink';
import { useTheme } from '../../theme/ThemeContext';
import { ScenarioMode } from '../../types';

interface SessionStatusBarProps {
  mode: ScenarioMode;
  totalTokens: number;
  maxTokens?: number;
  isRunning?: boolean;
  modelName?: string;
  workspaceName?: string;
  gitBranch?: string;
}

export const SessionStatusBar: React.FC<SessionStatusBarProps> = ({
  mode,
  totalTokens,
  maxTokens = 200000,
  isRunning = false,
  modelName = 'Zenith 3.7 Sonnet',
  workspaceName = 'zenith-frontend-tui',
  gitBranch = 'main',
}) => {
  const { theme } = useTheme();

  const contextPercent = Math.min(100, Math.round((totalTokens / maxTokens) * 100));

  // Mode styling
  const getModeBadge = (m: ScenarioMode) => {
    switch (m) {
      case 'plan':
        return { label: '[PLAN]', color: '#BD93F9' };
      case 'build':
      default:
        return { label: '[BUILD]', color: theme.colors.text.emerald };
    }
  };

  const modeBadge = getModeBadge(mode);

  // Render context bar: 10 chars wide
  const totalBlocks = 10;
  const filledBlocks = Math.max(0, Math.min(totalBlocks, Math.round((contextPercent / 100) * totalBlocks)));
  const emptyBlocks = totalBlocks - filledBlocks;
  const contextGauge = '█'.repeat(filledBlocks) + '░'.repeat(emptyBlocks);

  return (
    <Box flexDirection="column" width="100%" marginTop={1}>
      {/* Top subtle divider */}
      <Box width="100%">
        <Text color={theme.colors.border.muted}>─────────────────────────────────────────────────────────────</Text>
      </Box>

      {/* Main Status Bar Line 1: Primary session indicators */}
      <Box flexDirection="row" justifyContent="space-between" alignItems="center" flexWrap="wrap">
        <Box flexDirection="row" alignItems="center">
          {/* Mode Pill */}
          <Box paddingX={1} backgroundColor={modeBadge.color}>
            <Text color="#000000" bold>
              {modeBadge.label}
            </Text>
          </Box>
          <Text color={theme.colors.text.muted}> </Text>

          {/* Model Name */}
          <Text color={theme.colors.text.ethereal} bold>
            {modelName}
          </Text>
          <Text color={theme.colors.text.muted}> · </Text>

          {/* Tokens Used */}
          <Text color={theme.colors.text.muted}>
            {totalTokens.toLocaleString()} tokens
          </Text>
          <Text color={theme.colors.text.muted}> · </Text>

          {/* Context Meter */}
          <Text color={contextPercent > 80 ? theme.colors.text.warning : theme.colors.text.emerald}>
            [{contextGauge}] {contextPercent}%
          </Text>
        </Box>

        {/* Status Indicator */}
        <Box flexDirection="row" alignItems="center">
          {isRunning ? (
            <Text color={theme.colors.text.emerald} bold>
              Processing...
            </Text>
          ) : (
            <Text color={theme.colors.text.muted}>
              Idle
            </Text>
          )}
        </Box>
      </Box>

      {/* Line 2: Environment & Shortcuts Info */}
      <Box flexDirection="row" justifyContent="space-between" alignItems="center" marginTop={0} flexWrap="wrap">
        <Box flexDirection="row" alignItems="center">
          {/* Workspace */}
          <Text color={theme.colors.text.muted}>dir: </Text>
          <Text color={theme.colors.text.ethereal}>{workspaceName}</Text>
          <Text color={theme.colors.text.muted}> </Text>

          {/* Git branch */}
          <Text color={theme.colors.text.muted}>git:(</Text>
          <Text color={theme.colors.text.emerald}>{gitBranch}</Text>
          <Text color={theme.colors.text.muted}>)</Text>
        </Box>

        <Box flexDirection="row" alignItems="center">
          <Text color={theme.colors.text.muted} dimColor>
            esc cancel · / commands · shift+m mode
          </Text>
        </Box>
      </Box>
    </Box>
  );
};
