import { Box, Text } from 'ink';
import React from 'react';
import { SESSION_STATUS_DEFAULTS } from '../../constants/statusDefaults';
import { useProvider } from '../../hooks/useProvider';
import { getStatusBarLabels } from '../../services/data/StaticContentRepository';
import { formatTokenCount } from '../../services/data/tokenEstimationService';
import { isAutoApproveEnabled } from '../../services/data/toolApprovalService';
import { getActiveGitBranch } from '../../services/gitService';
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
  maxTokens = SESSION_STATUS_DEFAULTS.maxTokens,
  isRunning = false,
  modelName,
  workspaceName = SESSION_STATUS_DEFAULTS.workspaceName,
  gitBranch,
}) => {
  const { theme } = useTheme();
  const { activeProvider } = useProvider();
  const activeBranch = gitBranch || getActiveGitBranch();
  const statusLabels = getStatusBarLabels();

  const displayModel =
    modelName ||
    `Provider: ${activeProvider.meta.name} | Model: ${activeProvider.config.model || activeProvider.meta.defaultModel}`;

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
  const contextGauge = '█'.repeat(filledBlocks) + '░'.repeat(totalBlocks - filledBlocks);

  return (
    <Box flexDirection="column" width="100%" marginTop={1}>
      <Box width="100%">
        <Text color={theme.colors.border.muted}>{'─'.repeat(Math.min(process.stdout.columns ?? 80, 80))}</Text>
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
            {displayModel}
          </Text>
          <Text color={theme.colors.text.muted}> · </Text>

          <Text color={theme.colors.text.muted}>{formatTokenCount(totalTokens)} tokens</Text>
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
          <Text color={theme.colors.status.success}>{activeBranch}</Text>
          <Text color={theme.colors.text.muted}>)</Text>
        </Box>

        <Box flexDirection="row" alignItems="center">
          <Text color={theme.colors.text.muted} dimColor>
            {isAutoApproveEnabled() ? (
              <Text color={theme.colors.status.success}>auto-approve:on</Text>
            ) : (
              <Text color={theme.colors.text.muted}>auto-approve:off</Text>
            )}
            {' · '}
            {statusLabels.cancelHint} · {statusLabels.commandsHint} · {statusLabels.modeHint}
          </Text>
        </Box>
      </Box>
    </Box>
  );
};
