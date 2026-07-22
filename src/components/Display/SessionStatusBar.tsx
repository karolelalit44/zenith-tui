import { Box, Text } from 'ink';
import React from 'react';
import { StaticContentRepository } from '../../services/data/StaticContentRepository';
import { useTheme } from '../../theme/ThemeContext';
import type { ScenarioMode } from '../../types';

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
  const statusLabels = StaticContentRepository.getStatusBarLabels();

  const contextPercent = Math.min(100, Math.round((totalTokens / maxTokens) * 100));

  const getModeBadge = (m: ScenarioMode) => {
    switch (m) {
      case 'plan':
        return { label: '[PLAN]', color: theme.colors.status.accent };
      default:
        return { label: '[BUILD]', color: theme.colors.status.success };
    }
  };

  const modeBadge = getModeBadge(mode);

  const totalBlocks = 10;
  const filledBlocks = Math.max(0, Math.min(totalBlocks, Math.round((contextPercent / 100) * totalBlocks)));
  const emptyBlocks = totalBlocks - filledBlocks;
  const contextGauge = '█'.repeat(filledBlocks) + '░'.repeat(emptyBlocks);

  return (
    <Box flexDirection="column" width="100%" marginTop={1}>
      <Box width="100%">
        <Text color={theme.colors.border.muted}>─────────────────────────────────────────────────────────────</Text>
      </Box>

      <Box flexDirection="row" justifyContent="space-between" alignItems="center" flexWrap="wrap">
        <Box flexDirection="row" alignItems="center">
          <Box paddingX={1} backgroundColor={modeBadge.color}>
            <Text color={theme.colors.bg.app} bold>
              {modeBadge.label}
            </Text>
          </Box>
          <Text color={theme.colors.text.muted}> </Text>

          <Text color={theme.colors.text.ethereal} bold>
            {modelName}
          </Text>
          <Text color={theme.colors.text.muted}> · </Text>

          <Text color={theme.colors.text.muted}>{totalTokens.toLocaleString()} tokens</Text>
          <Text color={theme.colors.text.muted}> · </Text>

          <Text color={contextPercent > 80 ? theme.colors.text.warning : theme.colors.status.success}>
            [{contextGauge}] {contextPercent}%
          </Text>
        </Box>

        <Box flexDirection="row" alignItems="center">
          {isRunning ? (
            <Text color={theme.colors.status.success} bold>
              {statusLabels.processingText}
            </Text>
          ) : (
            <Text color={theme.colors.text.muted}>{statusLabels.idleText}</Text>
          )}
        </Box>
      </Box>

      <Box flexDirection="row" justifyContent="space-between" alignItems="center" marginTop={0} flexWrap="wrap">
        <Box flexDirection="row" alignItems="center">
          <Text color={theme.colors.text.muted}>{statusLabels.dirPrefix} </Text>
          <Text color={theme.colors.text.ethereal}>{workspaceName}</Text>
          <Text color={theme.colors.text.muted}> </Text>

          <Text color={theme.colors.text.muted}>git:(</Text>
          <Text color={theme.colors.status.success}>{gitBranch}</Text>
          <Text color={theme.colors.text.muted}>)</Text>
        </Box>

        <Box flexDirection="row" alignItems="center">
          <Text color={theme.colors.text.muted} dimColor>
            {statusLabels.cancelHint} · {statusLabels.commandsHint} · {statusLabels.modeHint}
          </Text>
        </Box>
      </Box>
    </Box>
  );
};
