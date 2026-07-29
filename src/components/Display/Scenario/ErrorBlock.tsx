import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { ErrorEvent } from '../../../types/scenario';
import type { EventRenderContext } from './componentRegistry';

interface ErrorBlockProps {
  event: ErrorEvent;
  context?: EventRenderContext;
}

const _MAX_MESSAGE_LENGTH = 200;

export const ErrorBlock: React.FC<ErrorBlockProps> = React.memo(({ event, context }) => {
  const { theme } = useTheme();

  const displayMessage = event.message.trim();

  const badge = event.recoverable ? '[ERROR]' : '[FAILED]';

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box
        flexDirection="column"
        width="100%"
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
            {displayMessage}
          </Text>
        </Box>

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

        <Box flexDirection="row" alignItems="center" flexWrap="wrap" marginTop={0}>
          <Text color={theme.colors.text.muted}>{event.recoverable ? 'Recoverable' : 'Execution halted'}</Text>
        </Box>

        {event.recoverable && (context?.onRetry || context?.onDismiss) && (
          <Box flexDirection="row" marginTop={1} paddingX={1}>
            {context?.onRetry && (
              <Box marginRight={2}>
                <Text color={theme.colors.status.success} bold>
                  [R] Retry
                </Text>
              </Box>
            )}
            {context?.onDismiss && (
              <Box>
                <Text color={theme.colors.text.muted} bold>
                  [D] Dismiss
                </Text>
              </Box>
            )}
          </Box>
        )}
      </Box>
    </Box>
  );
});
