import { Box, Text } from 'ink';
import React from 'react';
import { SESSION_STATUS_DEFAULTS } from '../../constants/statusDefaults';
import { useProvider } from '../../hooks/useProvider';
import type { TokenUsageStats } from '../../services/api/TokenUsageService';
import { formatTokenCount } from '../../services/api/tokenEstimationService';
import { getActiveGitBranch } from '../../services/git';
import { useTheme } from '../../theme/ThemeContext';
import type { ScenarioMode } from '../../types';
import type { FileAttachment } from '../../types/scenario';
import { MultiLineTextInput } from './MultiLineTextInput';

interface CommandInputProps {
  input: string;
  onInputChange: (value: string) => void;
  onSubmit: (value: string) => void;
  disabled?: boolean;
  attachments?: FileAttachment[];
  onRemoveAttachment?: (index: number) => void;
  historyUp?: () => string | undefined;
  historyDown?: () => string | undefined;
  mode?: ScenarioMode;
  totalTokens?: number;
  maxTokens?: number;
  isRunning?: boolean;
  tokenUsageStats?: TokenUsageStats | null;
  workspaceName?: string;
  gitBranch?: string;
}

export const CommandInput: React.FC<CommandInputProps> = React.memo(
  ({
    input,
    onInputChange,
    onSubmit,
    disabled = false,
    attachments,
    onRemoveAttachment: _onRemoveAttachment,
    historyUp,
    historyDown,
    mode = 'build',
    totalTokens = 0,
    maxTokens = SESSION_STATUS_DEFAULTS.maxTokens,
    isRunning = false,
    tokenUsageStats,
    workspaceName = SESSION_STATUS_DEFAULTS.workspaceName,
    gitBranch,
  }) => {
    const { theme } = useTheme();
    const { activeProvider } = useProvider();
    const activeBranch = gitBranch || getActiveGitBranch();
    const modelShort = activeProvider.config.model || activeProvider.meta.defaultModel || 'unknown';
    const providerName = activeProvider.meta.name || 'Unknown';

    const modeLabel = mode === 'plan' ? '[PLAN]' : '[BUILD]';
    const modeColor = theme.colors.text.emerald;

    const columns = process.stdout.columns ?? 80;
    const isSmall = columns < 65;
    const isMedium = columns < 100;

    const activeModelId = activeProvider.config.model || activeProvider.meta.defaultModel;
    const activeModelInfo = activeProvider.meta.availableModels?.find((m) => m.id === activeModelId);
    const effectiveMaxTokens =
      maxTokens && maxTokens !== SESSION_STATUS_DEFAULTS.maxTokens
        ? maxTokens
        : activeModelInfo?.context_window || SESSION_STATUS_DEFAULTS.maxTokens;

    const contextPercent = Math.min(100, Math.round((totalTokens / effectiveMaxTokens) * 100));
    const totalBlocks = 10;
    const filledBlocks = Math.max(0, Math.min(totalBlocks, Math.round((contextPercent / 100) * totalBlocks)));
    const contextGauge = '█'.repeat(filledBlocks) + '░'.repeat(totalBlocks - filledBlocks);

    const dirParts = workspaceName.replace(/\\/g, '/').split('/');
    const shortDir = dirParts.length > 2 ? `.../${dirParts.slice(-2).join('/')}` : workspaceName;

    const grandTotal = tokenUsageStats?.totals?.grand_total_tokens ?? 0;
    const requestCount = tokenUsageStats?.totals?.total_requests ?? 0;

    const dividerWidth = Math.max(0, columns - 6);

    return (
      <Box flexDirection="column" width="100%" marginTop={1}>
        {attachments && attachments.length > 0 && (
          <Box flexDirection="row" flexWrap="wrap" marginBottom={0}>
            {attachments.map((att, idx) => (
              <Box key={idx} flexDirection="row" marginRight={1}>
                <Text color={theme.colors.status.info}>[ATTACH]</Text>
                <Text color={theme.colors.text.ethereal}> {att.name}</Text>
                <Text color={theme.colors.text.muted}> </Text>
                <Text color={theme.colors.status.error}>(#{idx + 1})</Text>
              </Box>
            ))}
          </Box>
        )}

        {/* Single Unified Input Card */}
        <Box
          flexDirection="column"
          width="100%"
          borderStyle="round"
          borderColor={disabled ? theme.colors.border.muted : theme.colors.border.active}
          paddingX={1}
          paddingY={0}
        >
          {/* Primary Input Section */}
          <Box flexDirection="row" width="100%" alignItems="flex-start">
            <Text color={disabled ? theme.colors.text.muted : theme.colors.text.emerald} bold>
              {disabled ? '◌' : '❯'}{' '}
            </Text>
            <Box flexDirection="column" flexGrow={1}>
              {disabled ? (
                <Box flexDirection="row" alignItems="center" minHeight={1}>
                  <Text color={theme.colors.text.muted} italic>
                    Processing... (Esc to cancel)
                  </Text>
                </Box>
              ) : (
                <MultiLineTextInput
                  value={input}
                  onChange={onInputChange}
                  onSubmit={onSubmit}
                  placeholder="Ask anything..."
                  focus={!disabled}
                  historyUp={historyUp}
                  historyDown={historyDown}
                />
              )}
            </Box>
          </Box>

          {/* Seamless Horizontal Divider Line */}
          <Box width="100%" marginY={0}>
            <Text color={theme.colors.border.muted} wrap="truncate-end">
              {'─'.repeat(dividerWidth)}
            </Text>
          </Box>

          {/* Secondary Info Section */}
          <Box flexDirection="row" width="100%" justifyContent="space-between" alignItems="center">
            {/* Left side: Mode & Model */}
            <Box flexDirection="row" flexShrink={1}>
              <Text color={modeColor}>{modeLabel} </Text>
              <Text color={theme.colors.status.accent}>◇ </Text>
              <Text color={theme.colors.text.muted} wrap="truncate-end">
                {modelShort}
                {!isSmall ? ` · ${providerName}` : ''}
              </Text>
            </Box>

            {/* Right side: Repo / Branch | Tokens | Gauge | Reqs | State */}
            <Box flexDirection="row" flexShrink={0} alignItems="center">
              {!isMedium && <Text color={theme.colors.text.ethereal}>{shortDir}</Text>}
              {activeBranch ? (
                <>
                  {!isMedium && <Text color={theme.colors.text.muted}> </Text>}
                  <Text color={theme.colors.text.emerald}>({activeBranch})</Text>
                </>
              ) : null}
              <Text color={theme.colors.text.muted}> | </Text>
              <Text color={theme.colors.status.info}>{formatTokenCount(totalTokens)}</Text>
              <Text color={theme.colors.text.muted}>/</Text>
              <Text color={theme.colors.text.bright}>{formatTokenCount(effectiveMaxTokens)}</Text>
              <Text color={theme.colors.text.muted}> tokens </Text>
              <Text color={contextPercent > 80 ? theme.colors.status.warning : theme.colors.status.success}>
                [{contextGauge}] {contextPercent}%
              </Text>
              {grandTotal > 0 && (
                <>
                  <Text color={theme.colors.text.muted}> (Σ </Text>
                  <Text color={theme.colors.text.bright}>{formatTokenCount(grandTotal)}</Text>
                  <Text color={theme.colors.text.muted}> total)</Text>
                </>
              )}
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
      </Box>
    );
  },
);
