import React from 'react';
import { Box, Text } from 'ink';
import { useTheme } from '../../../theme/ThemeContext';
import { ErrorEvent } from '../../../types/scenario';

interface ErrorBlockProps {
  event: ErrorEvent;
}

export const ErrorBlock: React.FC<ErrorBlockProps> = ({ event }) => {
  const { theme } = useTheme();

  return (
    <Box flexDirection="column" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center" marginBottom={1}>
        <Text color={theme.colors.text.error} bold>✗ Error</Text>
        {event.command && (
          <>
            <Text color={theme.colors.text.muted}> while executing </Text>
            <Text color={theme.colors.text.ethereal} bold>{event.command}</Text>
          </>
        )}
      </Box>

      <Box flexDirection="column" paddingLeft={2} borderStyle="round" borderColor={theme.colors.text.error} paddingX={1}>
        <Text color={theme.colors.text.error}>{event.message}</Text>
        {event.stack && (
          <Box marginTop={1}>
            <Text color={theme.colors.text.muted} dimColor>{event.stack}</Text>
          </Box>
        )}
      </Box>
    </Box>
  );
};
