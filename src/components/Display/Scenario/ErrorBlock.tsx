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
        <Box flexDirection="row" alignItems="center" marginBottom={1} flexWrap="wrap">
          <Text color={theme.colors.status.error} bold>
            [ERROR]{' '}
          </Text>
          <Text color={theme.colors.text.bright} bold>
            {event.message}
          </Text>
          {event.command && <Text color={theme.colors.text.muted}> (command: {event.command})</Text>}
        </Box>

        {event.stack && (
          <Box flexDirection="column" marginBottom={1} paddingLeft={1} backgroundColor={theme.colors.bg.modal}>
            <Text color={theme.colors.status.error} dimColor wrap="wrap">
              {event.stack}
            </Text>
          </Box>
        )}

        <Box flexDirection="row" alignItems="center" justifyContent="space-between" flexWrap="wrap" marginTop={1}>
          <Text color={theme.colors.text.muted}>
            Recommendation: Check credentials, permissions, or project config.
          </Text>
          <Box paddingX={1} backgroundColor={theme.colors.status.error}>
            <Text color={theme.colors.bg.app} bold>
              [RETRY AVAILABLE]
            </Text>
          </Box>
        </Box>
      </Box>
    </Box>
  );
});
