import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { ErrorEvent } from '../../../types/scenario';

interface ErrorBlockProps {
  event: ErrorEvent;
}

export const ErrorBlock: React.FC<ErrorBlockProps> = React.memo(({ event }) => {
  const { theme } = useTheme();

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box
        flexDirection="column"
        width="100%"
        borderStyle="round"
        borderColor={theme.colors.status.error}
        paddingX={1}
        paddingY={1}
      >
        <Box flexDirection="row" alignItems="center" marginBottom={0} flexWrap="wrap">
          <Text color={theme.colors.status.error} bold>
            [ERROR]{' '}
          </Text>
          <Text color={theme.colors.text.bright} bold wrap="wrap">
            {event.message}
          </Text>
        </Box>

        {event.code && (
          <Box flexDirection="row" marginTop={0}>
            <Text color={theme.colors.text.muted}>Code: </Text>
            <Text color={theme.colors.status.warning} wrap="wrap">
              {event.code}
            </Text>
          </Box>
        )}

        {event.provider && (
          <Box flexDirection="row" marginTop={0}>
            <Text color={theme.colors.text.muted}>Provider: </Text>
            <Text color={theme.colors.text.bright} wrap="wrap">
              {event.provider}
            </Text>
          </Box>
        )}

        <Box flexDirection="row" alignItems="center" justifyContent="space-between" flexWrap="wrap" marginTop={0}>
          <Text color={theme.colors.text.muted}>
            {event.recoverable ? 'Recoverable - ' : ''}Status: Execution halted due to error.
          </Text>
          <Box paddingX={1} backgroundColor={theme.colors.status.error}>
            <Text color={theme.colors.bg.app} bold>
              [FAILED]
            </Text>
          </Box>
        </Box>
      </Box>
    </Box>
  );
});
