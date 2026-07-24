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
        borderStyle="single"
        borderColor={theme.colors.status.error}
        paddingX={1}
        paddingY={0}
      >
        <Box flexDirection="row" alignItems="center" marginBottom={0} flexWrap="wrap">
          <Text color={theme.colors.status.error} bold>
            [ERROR]{' '}
          </Text>
          <Text color={theme.colors.text.bright} bold wrap="wrap">
            {event.message}
          </Text>
        </Box>

        {event.command && (
          <Box flexDirection="row" marginTop={0}>
            <Text color={theme.colors.text.muted}>Command: </Text>
            <Text color={theme.colors.status.warning} wrap="wrap">{event.command}</Text>
          </Box>
        )}

        {event.stack && (
          <Box flexDirection="column" marginTop={0} paddingX={1} backgroundColor={theme.colors.bg.card}>
            <Text color={theme.colors.status.error} dimColor wrap="wrap">
              {event.stack}
            </Text>
          </Box>
        )}

        <Box flexDirection="row" alignItems="center" justifyContent="space-between" flexWrap="wrap" marginTop={0}>
          <Text color={theme.colors.text.muted}>
            Status: Execution halted due to error.
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
