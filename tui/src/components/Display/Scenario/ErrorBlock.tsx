import { Box, Text, useInput } from 'ink';
import React, { useState } from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import { useTerminalDimensions } from '../../../hooks/useTerminalDimensions';
import type { ErrorEvent } from '../../../types/scenario';
import { MAX_MESSAGE_PREVIEW_LENGTH } from '../../../utils/text';

interface ErrorBlockProps {
  event: ErrorEvent;
}

const ACTION_LABELS: Record<string, string> = {
  retry: 'You can retry this prompt',
  change_model: 'Switch model/provider to continue',
};

export const ErrorBlock: React.FC<ErrorBlockProps> = React.memo(({ event }) => {
  const { theme } = useTheme();
  const [expanded, setExpanded] = useState(false);
  const { columns } = useTerminalDimensions();
  const termCols = columns || process.stdout.columns || 80;
  const contentWidth = Math.max(30, termCols - 2);

  const rawMessage = event.message.trim();
  const truncated = rawMessage.length > MAX_MESSAGE_PREVIEW_LENGTH;
  const shownMessage = expanded || !truncated ? rawMessage : `${rawMessage.slice(0, MAX_MESSAGE_PREVIEW_LENGTH)}…`;

  const badge = event.recoverable ? '[ERROR]' : '[FAILED]';
  const actionLabel = event.action ? ACTION_LABELS[event.action] : undefined;

  useInput(
    (input, key) => {
      if (key.ctrl && (input === 'd' || input === '\x04')) {
        setExpanded((value) => !value);
      }
    },
    { isActive: truncated },
  );

  return (
    <Box flexDirection="column" width={contentWidth} marginBottom={1} paddingX={1}>
      <Box
        flexDirection="column"
        width={contentWidth}
        borderStyle="single"
        borderTop={false}
        borderRight={false}
        borderBottom={false}
        borderColor={theme.colors.status.error}
        paddingLeft={1}
      >
        <Box flexDirection="row" alignItems="flex-start" marginBottom={0} flexWrap="wrap">
          <Text color={theme.colors.status.error} bold>
            {badge}{' '}
          </Text>
          <Text color={theme.colors.text.bright} wrap="wrap">
            {shownMessage}
          </Text>
        </Box>

        {truncated && (
          <Box flexDirection="row" marginTop={0}>
            <Text color={theme.colors.text.muted}>
              {expanded ? '(ctrl+d to hide full details)' : '… (ctrl+d to show full details)'}
            </Text>
          </Box>
        )}

        {event.code && (
          <Box flexDirection="row" marginTop={0}>
            <Text color={theme.colors.text.muted}>Code: </Text>
            <Text color={theme.colors.status.warning}>{event.code}</Text>
          </Box>
        )}

        {event.provider && (
          <Box flexDirection="row" marginTop={0}>
            <Text color={theme.colors.text.muted}>Provider: </Text>
            <Text color={theme.colors.text.bright}>{event.provider}</Text>
          </Box>
        )}

        {event.hint && (
          <Box flexDirection="row" marginTop={0}>
            <Text color={theme.colors.text.muted}>Hint: </Text>
            <Text color={theme.colors.text.bright} wrap="wrap">
              {event.hint}
            </Text>
          </Box>
        )}

        {actionLabel && (
          <Box flexDirection="row" marginTop={0}>
            <Text color={theme.colors.status.accent}>{actionLabel}</Text>
          </Box>
        )}

        <Box flexDirection="row" alignItems="center" flexWrap="wrap" marginTop={0}>
          <Text color={theme.colors.text.muted}>{event.recoverable ? 'Recoverable' : 'Execution halted'}</Text>
        </Box>
      </Box>
    </Box>
  );
});
