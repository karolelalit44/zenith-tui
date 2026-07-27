import { Box, Text } from 'ink';
import React from 'react';
import { SESSION_STATUS_DEFAULTS } from '../../constants/statusDefaults';
import { useProvider } from '../../hooks/useProvider';
import { formatTokenCount } from '../../services/data/tokenEstimationService';
import { getActiveGitBranch } from '../../services/gitService';
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
  totalTokens?: number;
  maxTokens?: number;
  mode?: ScenarioMode;
}

export const CommandInput: React.FC<CommandInputProps> = React.memo(
  ({
    input,
    onInputChange,
    onSubmit,
    disabled = false,
    attachments,
    onRemoveAttachment,
    historyUp,
    historyDown,
    totalTokens = 0,
    maxTokens = SESSION_STATUS_DEFAULTS.maxTokens,
    mode = 'build',
  }) => {
    const { theme } = useTheme();
    const { activeProvider } = useProvider();
    const branch = getActiveGitBranch();
    const modelShort = activeProvider.config.model || activeProvider.meta.defaultModel || 'unknown';
    const providerName = activeProvider.meta.name || 'Unknown';
    const contextPercent = Math.min(100, Math.round((totalTokens / maxTokens) * 100));

    const cwd = process.cwd();
    const dirParts = cwd.replace(/\\/g, '/').split('/');
    const shortDir = dirParts.length > 2 ? `.../${dirParts.slice(-2).join('/')}` : cwd;

    const modeLabel = mode === 'plan' ? '[PLAN]' : '[BUILD]';
    const modeColor = theme.colors.text.emerald;

    const columns = process.stdout.columns ?? 80;
    const isSmall = columns < 65;
    const isMedium = columns < 90;

    return (
      <Box
        flexDirection="column"
        width="100%"
        borderStyle="round"
        borderColor={disabled ? theme.colors.border.muted : theme.colors.border.active}
        paddingX={1}
        paddingY={0}
        marginTop={1}
      >
        {attachments && attachments.length > 0 && (
          <Box flexDirection="row" flexWrap="wrap" marginBottom={0}>
            {attachments.map((att, idx) => (
              <Box key={idx} flexDirection="row" marginRight={1}>
                <Text color={theme.colors.status.info}>📎</Text>
                <Text color={theme.colors.text.ethereal}> {att.name}</Text>
                <Text color={theme.colors.text.muted}> </Text>
                <Text color={theme.colors.status.error}>(#{idx + 1})</Text>
              </Box>
            ))}
          </Box>
        )}
        <Box flexDirection="row" alignItems="flex-start">
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

            {/* Secondary status row — ALWAYS rendered to keep height stable */}
            <Box flexDirection="row" justifyContent="space-between" marginTop={1} width="100%">
              <Box flexDirection="row" flexShrink={1}>
                <Text color={modeColor}>{modeLabel} </Text>
                <Text color={theme.colors.status.accent}>◇ </Text>
                <Text color={theme.colors.text.muted} wrap="truncate-end">
                  {modelShort}
                  {!isSmall ? ` · ${providerName}` : ''}
                </Text>
              </Box>

              <Box flexDirection="row" flexShrink={0} paddingLeft={1}>
                <Text color={theme.colors.text.dim} wrap="truncate-end">
                  {!isMedium ? `${shortDir} ` : ''}
                  {branch && !isSmall ? (
                    <>
                      <Text color={theme.colors.text.emerald}>({branch})</Text>{' '}
                    </>
                  ) : null}
                  {formatTokenCount(totalTokens)} tok {contextPercent}%
                </Text>
              </Box>
            </Box>
          </Box>
        </Box>
      </Box>
    );
  },
);
