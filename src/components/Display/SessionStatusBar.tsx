import { Box, Text } from 'ink';
import React from 'react';
import { SESSION_STATUS_DEFAULTS } from '../../constants/statusDefaults';
import { useProvider } from '../../hooks/useProvider';
import type { TokenUsageStats } from '../../services/data/TokenUsageService';
import { formatTokenCount } from '../../services/data/tokenEstimationService';
import { getActiveGitBranch } from '../../services/gitService';
import { useTheme } from '../../theme/ThemeContext';
import type { ScenarioMode } from '../../types';

interface SessionStatusBarProps {
  mode: ScenarioMode;
  totalTokens: number;
  maxTokens?: number;
  isRunning?: boolean;
  isOverlayOpen?: boolean;
  hasEvents?: boolean;
  modelName?: string;
  workspaceName?: string;
  gitBranch?: string;
  tokenUsageStats?: TokenUsageStats | null;
}

export const SessionStatusBar: React.FC<SessionStatusBarProps> = ({
  mode,
  totalTokens,
  maxTokens = SESSION_STATUS_DEFAULTS.maxTokens,
  isRunning = false,
  isOverlayOpen = false,
  hasEvents = false,
  modelName,
  workspaceName = SESSION_STATUS_DEFAULTS.workspaceName,
  gitBranch,
  tokenUsageStats,
}) => {
  const { theme } = useTheme();
  const { activeProvider } = useProvider();
  const activeBranch = gitBranch || getActiveGitBranch();

  const _providerName = activeProvider.meta.name || 'Unknown';
  const _modelShort = modelName || activeProvider.config.model || activeProvider.meta.defaultModel || 'unknown';

  const contextPercent = Math.min(100, Math.round((totalTokens / maxTokens) * 100));

  const modeBadge =
    mode === 'plan'
      ? { label: '[PLAN]', color: theme.colors.text.emerald }
      : { label: '[BUILD]', color: theme.colors.text.emerald };

  const totalBlocks = 10;
  const filledBlocks = Math.max(0, Math.min(totalBlocks, Math.round((contextPercent / 100) * totalBlocks)));
  const contextGauge = '█'.repeat(filledBlocks) + '░'.repeat(totalBlocks - filledBlocks);

  const dirParts = workspaceName.replace(/\\/g, '/').split('/');
  const shortDir = dirParts.length > 2 ? `.../${dirParts.slice(-2).join('/')}` : workspaceName;

  const grandTotal = tokenUsageStats?.totals?.grand_total_tokens ?? 0;
  const grandTotalCost = tokenUsageStats?.totals?.grand_total_cost_usd ?? 0;
  const requestCount = tokenUsageStats?.totals?.total_requests ?? 0;

  const formatCost = (cost: number): string => {
    if (cost >= 1) return `$${cost.toFixed(2)}`;
    if (cost >= 0.01) return `$${cost.toFixed(4)}`;
    if (cost <= 0) return '';
    return `$${cost.toFixed(6)}`;
  };

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
          {isRunning ? (
            <Text color={theme.colors.text.dim}>Ctrl+C cancel · Shift+T thinking</Text>
          ) : isOverlayOpen ? (
            <Text color={theme.colors.text.dim}>Esc close</Text>
          ) : hasEvents ? (
            <Text color={theme.colors.text.dim}>Ctrl+S save · Ctrl+L clear · Ctrl+P help</Text>
          ) : (
            <Text color={theme.colors.text.dim}>Enter send · / commands</Text>
          )}
        </Box>

        <Box flexDirection="row" alignItems="center">
          <Text color={theme.colors.text.ethereal}>{shortDir}</Text>
          {activeBranch ? (
            <>
              <Text color={theme.colors.text.muted}> </Text>
              <Text color={theme.colors.text.emerald}>(</Text>
              <Text color={theme.colors.text.emerald}>{activeBranch}</Text>
              <Text color={theme.colors.text.emerald}>)</Text>
            </>
          ) : null}
          <Text color={theme.colors.text.muted}> | </Text>
          <Text color={theme.colors.status.info}>{formatTokenCount(totalTokens)}</Text>
          <Text color={theme.colors.text.muted}>/</Text>
          <Text color={grandTotal > 0 ? theme.colors.text.bright : theme.colors.text.muted}>
            {formatTokenCount(grandTotal)}
          </Text>
          <Text color={theme.colors.text.muted}> tokens</Text>
          {grandTotalCost > 0 && (
            <>
              <Text color={theme.colors.text.muted}> </Text>
              <Text color={theme.colors.status.info}>{formatCost(grandTotalCost)}</Text>
            </>
          )}
          <Text color={theme.colors.text.muted}> </Text>
          <Text color={contextPercent > 80 ? theme.colors.status.warning : theme.colors.status.success}>
            [{contextGauge}] {contextPercent}%
          </Text>
          {requestCount > 0 && (
            <>
              <Text color={theme.colors.text.muted}> | </Text>
              <Text color={theme.colors.text.muted}>{requestCount} req</Text>
            </>
          )}
          <Text color={theme.colors.text.muted}> | </Text>
          {isRunning ? (
            <Text color={theme.colors.status.success} bold>
              Running
            </Text>
          ) : (
            <Text color={theme.colors.text.muted}>Idle</Text>
          )}
        </Box>
      </Box>
    </Box>
  );
};
